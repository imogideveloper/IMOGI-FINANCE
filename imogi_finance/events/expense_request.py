"""Expense Request event handlers for doc_events hooks."""
from __future__ import annotations

import frappe
from frappe import _


def validate_workflow_action(doc, method=None):
    """Validate approver authorization when workflow action is being applied.
    
    This is triggered via doc_events validate hook when Frappe's apply_workflow
    saves the document. We detect if a workflow transition is happening and
    validate that the current user is the authorized approver.
    """
    # Skip if not in workflow transition
    if not _is_workflow_transition(doc):
        return
    
    # Skip if not transitioning to/from Pending Review
    if not _is_approval_action(doc):
        return
    
    # Get current approval level - default to 1 if not set
    current_level = getattr(doc, "current_approval_level", None) or 1
    
    # Get expected approver for this level
    expected_user = getattr(doc, f"level_{current_level}_user", None)
    
    if not expected_user:
        # No approver configured for this level
        frappe.throw(
            _("No approver configured for level {0}.").format(current_level),
            title=_("Not Allowed"),
        )
    
    session_user = frappe.session.user
    
    if session_user != expected_user:
        frappe.throw(
            _("You are not authorized to approve at level {0}. Required: {1}.").format(
                current_level, expected_user
            ),
            title=_("Not Allowed"),
        )


def _is_workflow_transition(doc) -> bool:
    """Check if document is undergoing a workflow state transition."""
    # Check if there's a previous version to compare
    previous = getattr(doc, "_doc_before_save", None)
    if not previous:
        return False
    
    # Check if workflow_state is changing
    current_state = getattr(doc, "workflow_state", None)
    previous_state = getattr(previous, "workflow_state", None)
    
    return current_state != previous_state


def _is_approval_action(doc) -> bool:
    """Check if the transition involves approval (from or to Pending Review)."""
    previous = getattr(doc, "_doc_before_save", None)
    if not previous:
        return False
    
    current_state = getattr(doc, "workflow_state", None)
    previous_state = getattr(previous, "workflow_state", None)
    
    # Approval action: transitioning FROM Pending Review
    # This catches both Approve (to Pending Review or Approved) and Reject (to Rejected)
    if previous_state == "Pending Review":
        return True
    
    return False
