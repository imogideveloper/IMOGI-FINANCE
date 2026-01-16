"""Event handlers for Budget Approval workflow (Budget Reclass Request & Additional Budget Request)."""

from __future__ import annotations

import frappe


def sync_workflow_state_after_approval(doc, method=None):
    """
    Sync workflow state after approval action completes.
    
    This hook runs AFTER workflow save, ensuring state changes from advance_approval_level()
    are properly persisted and not overridden by workflow framework.
    
    Called via on_update_after_submit hook.
    """
    # Check if this was a workflow action (has _action flag set by workflow)
    if not getattr(doc.flags, "workflow_action", None):
        return
    
    # Reload from DB to get the actual persisted values from db_set()
    current_level = frappe.db.get_value(doc.doctype, doc.name, "current_approval_level")
    
    if not current_level:
        return
    
    # If level > 0, we're in multi-level approval - should be "Pending Approval"
    # If level == 0, final approval - should be "Approved"
    expected_state = "Pending Approval" if current_level > 0 else "Approved"
    current_state = getattr(doc, "workflow_state", None)
    
    if current_state != expected_state:
        frappe.logger().info(
            f"sync_workflow_state_after_approval: Correcting {doc.name} from {current_state} to {expected_state} (level={current_level})"
        )
        
        # Update in memory
        doc.workflow_state = expected_state
        doc.status = expected_state
        
        # Persist to DB
        frappe.db.set_value(
            doc.doctype,
            doc.name,
            {
                "workflow_state": expected_state,
                "status": expected_state,
            },
            update_modified=False
        )
