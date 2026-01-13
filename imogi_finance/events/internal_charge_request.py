"""Internal Charge Request event handlers for doc_events hooks."""
from __future__ import annotations


def sync_status_with_workflow(doc, method=None):
    """Sync status field with workflow_state after save.
    
    This ensures the 'status' field matches 'workflow_state' for display consistency
    when workflow actions are performed.
    """
    # Internal Charge Request has complex line-based status logic
    # So we only sync workflow_state to status when workflow_state is set
    workflow_state = getattr(doc, "workflow_state", None)
    current_status = getattr(doc, "status", None)
    
    if not workflow_state:
        return
    
    # Only sync if status doesn't match workflow_state
    # This preserves the line-based status logic while ensuring
    # workflow transitions are reflected
    if current_status != workflow_state:
        # Use db_set to update without triggering hooks again
        doc.db_set("status", workflow_state, update_modified=False)
