"""Branch Expense Request event handlers for doc_events hooks."""
from __future__ import annotations


def sync_status_with_workflow(doc, method=None):
    """Sync status field with workflow_state after save.
    
    This ensures the 'status' field matches 'workflow_state' for display consistency
    when workflow actions are performed.
    """
    workflow_state = getattr(doc, "workflow_state", None)
    current_status = getattr(doc, "status", None)
    
    if not workflow_state:
        return
    
    # Sync status with workflow_state if different
    if current_status != workflow_state:
        # Use db_set to update without triggering hooks again
        doc.db_set("status", workflow_state, update_modified=False)
