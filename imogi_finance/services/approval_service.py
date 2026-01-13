"""Multi-level approval state machine - reusable for any doctype with approval workflow."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import frappe
from frappe import _
from frappe.utils import now_datetime

if TYPE_CHECKING:
    from frappe.model.document import Document


class ApprovalService:
    """Handle multi-level approval state transitions following Frappe workflow conventions.
    
    Usage:
        service = ApprovalService(doctype="Expense Request", state_field="workflow_state")
        service.before_submit(doc, route=approval_route)
        service.before_workflow_action(doc, action="Approve", next_state="Pending Review")
        service.on_workflow_action(doc, action="Approve", next_state="Approved")
    
    Reusable for: Expense Request, Internal Charge Request, Branch Expense Request, etc.
    """

    def __init__(self, doctype: str = "Expense Request", state_field: str = "workflow_state"):
        self.doctype = doctype
        self.state_field = state_field
        self.status_field = "status"
        self.level_field_prefix = "level_{level}_user"
        self.current_level_field = "current_approval_level"

    def before_submit(
        self,
        doc: Document,
        route: dict | None = None,
        auto_approve: bool = False,
        skip_approval: bool = False,
    ) -> None:
        """Initialize approval state on submit.
        
        Args:
            doc: Document to process
            route: Approval route dict with level_1/2/3 users
            auto_approve: If True, set state to "Approved" immediately
            skip_approval: If True, set state to "Approved" (deprecated, use auto_approve)
        """
        route = route or self._get_route_snapshot(doc)

        if auto_approve or skip_approval or not self._has_approver(route):
            self._set_state(doc, "Approved", level=0)
            return

        initial_level = self._get_initial_level(route)
        self._set_state(doc, "Pending Review", level=initial_level)
        self._set_flags(doc, workflow_allowed=True)

    def before_workflow_action(
        self, doc: Document, action: str, next_state: str | None = None, route: dict | None = None
    ) -> None:
        """Guard workflow action - validate approver authorization.
        
        Args:
            doc: Document being transitioned
            action: Workflow action name (Submit, Approve, Reject, etc.)
            next_state: Target workflow state
            route: Approval route (loaded from doc if not provided)
        """
        route = route or self._get_route_snapshot(doc)

        # Submit action: set up initial state
        if action == "Submit":
            self.before_submit(doc, route=route)
            return

        # Approve/Reject: check authorization
        if action in ("Approve", "Reject"):
            if not self._is_pending_review(doc):
                return
            self._check_approver_authorization(doc, route)

        # Set flag to allow status changes
        self._set_flags(doc, workflow_allowed=True)

    def on_workflow_action(self, doc: Document, action: str, next_state: str | None = None) -> None:
        """Update state after workflow action succeeds.
        
        Args:
            doc: Document being transitioned
            action: Workflow action name
            next_state: Target workflow state
        """
        if not next_state:
            return

        if action == "Approve":
            if self._is_pending_review(doc):
                # Check if more levels exist
                if self._has_next_level(doc):
                    # Stay in Pending Review, advance level
                    self._advance_level(doc)
                else:
                    # All levels approved, move to Approved
                    self._set_state(doc, "Approved", level=0)
                    self._set_audit_timestamp(doc, "approved_on")
            return

        if action == "Reject":
            self._set_state(doc, "Rejected", level=0)
            self._set_audit_timestamp(doc, "rejected_on")
            return

        if action == "Reopen":
            # Recalculate route (should happen before this hook)
            route = self._get_route_snapshot(doc)
            if not self._has_approver(route):
                self._set_state(doc, "Approved", level=0)
            else:
                initial_level = self._get_initial_level(route)
                self._set_state(doc, "Pending Review", level=initial_level)
            return

        # Generic: set state to next_state
        if next_state:
            self._set_state(doc, next_state)

    def sync_state_to_status(self, doc: Document) -> None:
        """Keep status field in sync with workflow_state (for display consistency)."""
        state = getattr(doc, self.state_field, None)
        if state:
            setattr(doc, self.status_field, state)
            self._set_flags(doc, workflow_allowed=True)

    def guard_status_changes(self, doc: Document) -> None:
        """Prevent status changes outside of workflow (detect and block manual bypass)."""
        if self._workflow_allowed(doc):
            return

        flags = getattr(frappe, "flags", None)
        if getattr(flags, "in_patch", False) or getattr(flags, "in_install", False):
            return

        previous = getattr(doc, "_doc_before_save", None)
        if not previous:
            return

        # Same docstatus = submitted document being edited
        if getattr(previous, "docstatus", None) != getattr(doc, "docstatus", None):
            return

        # Status didn't change = no issue
        if getattr(previous, self.status_field, None) == getattr(doc, self.status_field, None):
            return

        frappe.throw(_("Status changes must be performed via workflow actions."), title=_("Not Allowed"))

    # ===================== Private Helpers =====================

    def _check_approver_authorization(self, doc: Document, route: dict | None = None) -> None:
        """Validate current user is the approver for current level."""
        route = route or self._get_route_snapshot(doc)
        if not self._is_pending_review(doc):
            return

        # Get current level - default to 1 if not set (first approval after submit)
        current_level = self._get_current_level(doc) or 1

        user_field = self.level_field_prefix.format(level=current_level)
        expected_user = doc.get(user_field)

        if not expected_user:
            frappe.throw(
                _("No approver configured for level {0}.").format(current_level),
                title=_("Not Allowed"),
            )

        session_user = frappe.session.user
        if session_user != expected_user:
            frappe.throw(
                _("You are not authorized to approve at level {0}. Required: {1}.").format(current_level, expected_user),
                title=_("Not Allowed"),
            )

    def _is_pending_review(self, doc: Document) -> bool:
        """Check if document is in Pending Review state."""
        state = getattr(doc, self.state_field, None)
        return state == "Pending Review"

    def _has_approver(self, route: dict | None) -> bool:
        """Check if route has at least one approver."""
        # Import here to avoid circular dependency
        try:
            from imogi_finance.approval import has_approver_in_route
            return has_approver_in_route(route)
        except ImportError:
            # Fallback for testing or edge cases
            if not route:
                return False
            return any(route.get(f"level_{level}", {}).get("user") for level in (1, 2, 3))

    def _get_initial_level(self, route: dict | None) -> int:
        """Get first configured approval level."""
        if not route:
            return 1
        for level in (1, 2, 3):
            if route.get(f"level_{level}", {}).get("user"):
                return level
        return 1

    def _get_current_level(self, doc: Document) -> int | None:
        """Get current approval level."""
        level = getattr(doc, self.current_level_field, None) or 0
        return int(level) if level else None

    def _has_next_level(self, doc: Document) -> bool:
        """Check if there are more approval levels after current."""
        current = self._get_current_level(doc) or 1
        for level in range(current + 1, 4):
            user_field = self.level_field_prefix.format(level=level)
            if doc.get(user_field):
                return True
        return False

    def _advance_level(self, doc: Document) -> None:
        """Move to next approval level."""
        current = self._get_current_level(doc) or 1
        for level in range(current + 1, 4):
            user_field = self.level_field_prefix.format(level=level)
            if doc.get(user_field):
                setattr(doc, self.current_level_field, level)
                return
        setattr(doc, self.current_level_field, current)

    def _set_state(self, doc: Document, state: str, level: int = 0) -> None:
        """Set workflow state and sync status field."""
        setattr(doc, self.state_field, state)
        setattr(doc, self.status_field, state)
        setattr(doc, self.current_level_field, level)
        self._set_flags(doc, workflow_allowed=True)

    def _set_audit_timestamp(self, doc: Document, field: str) -> None:
        """Set audit timestamp (approved_on, rejected_on, etc.)."""
        timestamp = now_datetime()
        try:
            setattr(doc, field, timestamp)
            if getattr(doc, "docstatus", 0) == 1 and hasattr(doc, "db_set"):
                doc.db_set(field, timestamp, update_modified=False)
        except Exception:
            pass

    def _set_flags(self, doc: Document, workflow_allowed: bool = False) -> None:
        """Set flags to allow status changes."""
        flags = getattr(doc, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            doc.flags = flags
        if workflow_allowed:
            flags.workflow_action_allowed = True

    def _workflow_allowed(self, doc: Document) -> bool:
        """Check if workflow_action_allowed flag is set."""
        flags = getattr(doc, "flags", None)
        return bool(flags and getattr(flags, "workflow_action_allowed", False))

    def _get_route_snapshot(self, doc: Document) -> dict:
        """Get stored approval route from document."""
        try:
            from imogi_finance.approval import parse_route_snapshot
            snapshot = getattr(doc, "approval_route_snapshot", None)
            parsed = parse_route_snapshot(snapshot)
            if parsed:
                return parsed
        except ImportError:
            pass

        # Fallback: build from document fields
        return {
            f"level_{level}": {"user": doc.get(self.level_field_prefix.format(level=level))}
            for level in (1, 2, 3)
        }
