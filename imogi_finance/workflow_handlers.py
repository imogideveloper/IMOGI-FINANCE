"""Workflow action handlers for multi-level budget approvals.

This module handles workflow transitions for documents with multi-level approval:
- Budget Reclass Request
- Additional Budget Request

The workflow is configured in workflow.json with:
- States: Draft, Pending Approval, Approved, Rejected
- Actions: Submit, Approve, Reject
- Override Status: 1 (workflow_state controls status field)
"""

from __future__ import annotations

import frappe
from frappe import _
from imogi_finance import budget_approval


def handle_approve_action(doc, workflow_action):
	"""Handle Approve action for multi-level approval documents.
	
	This function should be called from the document's `apply_workflow` method
	or as a before_workflow_action hook.
	
	Args:
		doc: Document being approved
		workflow_action: Action being performed (should be "Approve")
		
	Returns:
		None to allow normal workflow, or raise exception to prevent
	"""
	if workflow_action != "Approve":
		return
	
	# Validate approver has permission
	budget_approval.validate_approver_permission(doc, workflow_action)
	
	# Get current and next level info
	current_level = doc.current_approval_level or 1
	next_level = current_level + 1
	next_user = getattr(doc, f"level_{next_level}_user", None)
	
	# Record current level approval
	budget_approval.record_approval_timestamp(doc, current_level)
	
	if next_user:
		# Has more approval levels - advance to next level
		doc.db_set("current_approval_level", next_level, update_modified=False)
		doc.db_set("workflow_state", "Pending Approval", update_modified=False)
		doc.db_set("status", "Pending Approval", update_modified=False)
		doc.reload()
		
		# Prevent workflow from changing state
		frappe.throw(_("Moved to Level {0} approval. Waiting for {1}").format(
			next_level, next_user
		), frappe.ValidationError)
	else:
		# Final approval level - reset level and let workflow proceed to Approved
		doc.db_set("current_approval_level", 0, update_modified=False)
		# Workflow will handle state transition to Approved


def handle_reject_action(doc, workflow_action):
	"""Handle Reject action for multi-level approval documents.
	
	Args:
		doc: Document being rejected
		workflow_action: Action being performed (should be "Reject")
	"""
	if workflow_action != "Reject":
		return
	
	# Validate approver has permission
	budget_approval.validate_approver_permission(doc, workflow_action)
	
	# Reset approval level
	doc.db_set("current_approval_level", 0, update_modified=False)
	# Workflow will handle state transition to Rejected
