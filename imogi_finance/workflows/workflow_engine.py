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

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            frappe.throw(_("Workflow configuration file not found: {0}").format(self.config_path))
        try:
            with self.config_path.open() as handle:
                return json.load(handle)
        except Exception as exc:
            frappe.throw(_("Failed to load workflow configuration: {0}").format(exc))

    def get_states(self) -> set[str]:
        states = self.config.get("states", [])
        return {state.get("state") for state in states if state.get("state")}

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

        # Derive required roles/users from doc-level route fields
        level = self._current_level_from_state(current_state)
        role_field = f"level_{level}_role" if level else None
        user_field = f"level_{level}_user" if level else None
        expected_roles = {getattr(doc, role_field)} if role_field and getattr(doc, role_field, None) else set()
        expected_users = {getattr(doc, user_field)} if user_field and getattr(doc, user_field, None) else set()

        if expected_roles or expected_users:
            guard = AuthorizationGuard(roles=expected_roles, users=expected_users)
            guard.require(action=action, level=level)

        if action == "Approve" and next_state == "Approved":
            self._validate_not_skipping(doc, level)

    @staticmethod
    def _current_level_from_state(state: str | None) -> str | None:
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
