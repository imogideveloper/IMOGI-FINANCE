from __future__ import annotations

from typing import Any, Callable, Iterable

import frappe
from frappe import _


class WorkflowService:
    """Generic helpers for workflow state management and guards."""

    def __init__(self, *, state_field: str = "workflow_state", status_field: str = "status"):
        self.state_field = state_field
        self.status_field = status_field

    def sync_status(self, doc: Any, valid_states: Iterable[str]):
        workflow_state = getattr(doc, self.state_field, None)
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
        frappe.throw(_("Status changes must be performed via workflow actions."), title=_("Not Allowed"))

    def set_status(self, doc: Any, status: str | None):
        if status is not None:
            setattr(doc, self.status_field, status)

    @staticmethod
    def require_permission(check: Callable[[], bool], message: str):
        if not check():
            frappe.throw(message, title=_("Not Allowed"))

    @staticmethod
    def _mark_workflow_allowed(doc: Any):
        flags = getattr(doc, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            doc.flags = flags
        doc.flags.workflow_action_allowed = True
