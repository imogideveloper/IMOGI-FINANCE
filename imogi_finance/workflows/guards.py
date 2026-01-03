from __future__ import annotations

from typing import Any, Iterable

import frappe
from frappe import _


class AuthorizationGuard:
    """Role and user based authorization guard."""

    def __init__(self, *, roles: Iterable[str] | None = None, users: Iterable[str] | None = None):
        self.roles = {role for role in roles or [] if role}
        self.users = {user for user in users or [] if user}

    def is_allowed(self) -> bool:
        role_allowed = bool(self.roles.intersection(set(frappe.get_roles())))
        user_allowed = getattr(getattr(frappe, "session", None), "user", None) in self.users
        return role_allowed or user_allowed

    def require(self, *, action: str | None = None, level: str | None = None):
        if self.is_allowed():
            return

        requirements = []
        if self.roles:
            requirements.append(_("role '{0}'").format(_(", ").join(sorted(self.roles))))
        if self.users:
            requirements.append(_("user '{0}'").format(_(", ").join(sorted(self.users))))
        target = _(" and ").join(requirements) if requirements else _("configured approver")

        details = {"action": action, "level": level, "session_user": getattr(getattr(frappe, "session", None), "user", None)}
        self._log_denial(details)

        frappe.throw(_("You must be {target} to perform this action.").format(target=target), title=_("Not Allowed"))

    @staticmethod
    def _log_denial(details: dict[str, Any]):
        logger = getattr(frappe, "logger", None)
        if not logger:
            return
        try:
            logger("imogi_finance").warning("Workflow action denied", extra=details)
        except Exception:
            pass


class WorkflowGuard:
    """Workflow guard for ensuring states only change through allowed actions."""

    FINAL_STATES = {"Approved", "Linked", "Closed"}

    @staticmethod
    def require_session_user():
        if getattr(frappe, "session", None) is None or getattr(getattr(frappe, "session", None), "user", None) is None:
            frappe.throw(_("Session invalid, backflow not permitted."))

    def __init__(self, *, status_field: str = "status", workflow_field: str = "workflow_state"):
        self.status_field = status_field
        self.workflow_field = workflow_field

    def sync_status(self, doc: Any, valid_states: Iterable[str]):
        workflow_state = getattr(doc, self.workflow_field, None)
        if not workflow_state or workflow_state not in set(valid_states):
            return
        current_status = getattr(doc, self.status_field, None)
        if current_status == workflow_state:
            return
        setattr(doc, self.status_field, workflow_state)
        self._mark_workflow_allowed(doc)

    def guard_status_changes(self, doc: Any):
        flags_obj = getattr(doc, "flags", None)
        if flags_obj and getattr(flags_obj, "workflow_action_allowed", False):
            return
        flags = getattr(frappe, "flags", None)
        if getattr(flags, "in_patch", False) or getattr(flags, "in_install", False):
            return
        previous = getattr(doc, "_doc_before_save", None)
        if not previous or getattr(previous, "docstatus", None) != getattr(doc, "docstatus", None):
            return
        if getattr(previous, self.status_field, None) == getattr(doc, self.status_field, None):
            return
        previous_state = getattr(previous, self.workflow_field, None)
        current_state = getattr(doc, self.workflow_field, None)
        if previous_state != current_state and current_state == getattr(doc, self.status_field, None):
            return
        frappe.throw(_("Status changes must be performed via workflow actions."), title=_("Not Allowed"))

    @staticmethod
    def _mark_workflow_allowed(doc: Any):
        flags = getattr(doc, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            doc.flags = flags
        doc.flags.workflow_action_allowed = True
