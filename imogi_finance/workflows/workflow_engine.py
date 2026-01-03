from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import frappe
from frappe import _

from .guards import AuthorizationGuard


class WorkflowEngine:
    """Config-driven workflow engine for IMOGI Finance doctypes."""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._validate_config()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            frappe.throw(_("Workflow configuration file not found: {0}").format(self.config_path))
        try:
            with self.config_path.open() as handle:
                return json.load(handle)
        except Exception as exc:
            frappe.throw(_("Failed to load workflow configuration: {0}").format(exc))

    def _validate_config(self):
        states = self.config.get("states") or []
        actions = self.config.get("actions") or []
        transitions = self.config.get("transitions") or []

        if not isinstance(states, list) or not states:
            frappe.throw(_("Workflow configuration must include at least one state."))

        if not isinstance(actions, list) or not actions:
            frappe.throw(_("Workflow configuration must include at least one action."))

        state_names = {state.get("state") for state in states if state.get("state")}
        action_names = {action.get("action") for action in actions if action.get("action")}

        if len(state_names) != len(states):
            frappe.throw(_("Workflow states must be unique."))
        if len(action_names) != len(actions):
            frappe.throw(_("Workflow actions must be unique."))

        for state in states:
            if "backflow_allowed" not in state:
                state["backflow_allowed"] = False
            if "acl" not in state or state["acl"] is None:
                state["acl"] = {"roles": [], "users": []}

        for transition in transitions:
            state = transition.get("state")
            next_state = transition.get("next_state")
            action = transition.get("action")
            if state not in state_names or next_state not in state_names:
                frappe.throw(_("Transition {0} -> {1} references an unknown state.").format(state, next_state))
            if action not in action_names:
                frappe.throw(_("Transition uses undefined action: {0}").format(action))

    def get_states(self) -> set[str]:
        states = self.config.get("states", [])
        return {state.get("state") for state in states if state.get("state")}

    def get_state_config(self, state: str | None) -> dict[str, Any]:
        for item in self.config.get("states", []):
            if item.get("state") == state:
                return item
        return {}

    def get_actions(self) -> Iterable[dict[str, Any]]:
        return self.config.get("actions", [])

    def get_transitions(self) -> Iterable[dict[str, Any]]:
        return self.config.get("transitions", [])

    def guard_action(self, *, doc: Any, action: str, current_state: str | None, next_state: str | None = None):
        """Validate that a workflow action is allowed for the routed user."""
        if not action or current_state is None:
            return
        transitions = [t for t in self.get_transitions() if t.get("action") == action and t.get("state") == current_state]
        if not transitions:
            frappe.throw(_("Action {0} is not allowed from state {1}.").format(action, current_state))

        self._validate_state_acl(current_state)
        if action in {"Reopen", "Backflow"}:
            self._guard_elevated_action(doc=doc, action=action, current_state=current_state, next_state=next_state)

        # Derive required roles/users from doc-level route fields
        level = self._current_level_from_state(doc, current_state)
        role_field = f"level_{level}_role" if level else None
        user_field = f"level_{level}_user" if level else None
        expected_roles = {getattr(doc, role_field)} if role_field and getattr(doc, role_field, None) else set()
        expected_users = {getattr(doc, user_field)} if user_field and getattr(doc, user_field, None) else set()

        if expected_roles or expected_users:
            guard = AuthorizationGuard(roles=expected_roles, users=expected_users)
            guard.require(action=action, level=level)

        if action == "Approve" and next_state == "Approved":
            self._validate_not_skipping(doc, level)
        if action == "Backflow":
            self._validate_backflow_allowed(current_state, next_state, doc)

    @staticmethod
    def _current_level_from_state(doc: Any, state: str | None) -> str | None:
        if state == "Pending Review":
            level = getattr(doc, "current_approval_level", None)
            return str(level) if level else None
        mapping = {
            "Pending Level 1": "1",
            "Pending Level 2": "2",
            "Pending Level 3": "3",
        }
        return mapping.get(state)

    @staticmethod
    def _validate_not_skipping(doc: Any, level: str | None):
        if level == "1" and (getattr(doc, "level_2_role", None) or getattr(doc, "level_2_user", None) or getattr(doc, "level_3_role", None) or getattr(doc, "level_3_user", None)):
            frappe.throw(_("Cannot approve directly when further levels are configured."))
        if level == "2" and (getattr(doc, "level_3_role", None) or getattr(doc, "level_3_user", None)):
            frappe.throw(_("Cannot approve directly when further levels are configured."))

    def _validate_state_acl(self, state: str):
        config = self.get_state_config(state)
        acl = config.get("acl") or {}
        roles = set(acl.get("roles") or [])
        users = set(acl.get("users") or [])
        if not roles and not users:
            return
        guard = AuthorizationGuard(roles=roles, users=users)
        guard.require(action="state_access", level=state)

    def _guard_elevated_action(self, *, doc: Any, action: str, current_state: str, next_state: str | None):
        session = getattr(frappe, "session", None)
        if session is None or getattr(session, "user", None) is None:
            frappe.throw(_("Session invalid, backflow not permitted."))

        state_config = self.get_state_config(current_state)
        if action == "Backflow" and not state_config.get("backflow_allowed"):
            frappe.throw(_("Backflow is not permitted from state {0}.").format(current_state))

        if action == "Backflow":
            self._log_backflow(doc, current_state, next_state)

    def _validate_backflow_allowed(self, current_state: str, next_state: str | None, doc: Any):
        if next_state not in {"Pending Review", "Reopened"}:
            return
        reason = getattr(doc, "backflow_reason", None) or getattr(getattr(doc, "flags", None), "backflow_reason", None)
        if not reason:
            frappe.throw(_("Backflow reason is required to move from {0} to {1}.").format(current_state, next_state))

    @staticmethod
    def _log_backflow(doc: Any, from_state: str, to_state: str | None):
        logger = getattr(frappe, "logger", None)
        user = getattr(getattr(frappe, "session", None), "user", None)
        timestamp_getter = getattr(getattr(frappe, "utils", None), "now_datetime", None)
        now = timestamp_getter() if callable(timestamp_getter) else None
        reason = getattr(doc, "backflow_reason", None) or getattr(getattr(doc, "flags", None), "backflow_reason", None)
        details = {
            "document": getattr(doc, "name", None),
            "doctype": getattr(doc, "doctype", None),
            "from_state": from_state,
            "to_state": to_state,
            "user": user,
            "timestamp": now,
            "reason": reason,
        }
        if logger:
            try:
                logger("imogi_finance").info("Workflow backflow executed", extra=details)
            except Exception:
                pass
