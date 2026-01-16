"""Event handlers for Budget Approval workflow (Budget Reclass Request & Additional Budget Request)."""

from __future__ import annotations

import frappe
from frappe import _


def sync_workflow_state_after_approval(doc, method=None):
	"""Handle multi-level approval workflow state synchronization.
	
	This runs on on_update_after_submit for Budget Reclass Request and Additional Budget Request.
	It ensures workflow state is correctly set based on approval level progression.
	"""
	# Only process submitted documents
	if doc.docstatus != 1:
		return
	
	# Only process documents with multi-level approval fields
	if not hasattr(doc, "current_approval_level"):
		return
	
	# Get current approval level
	current_level = doc.current_approval_level or 0
	
	# Determine correct workflow state based on approval level
	# Level 0 = all approvals complete → Approved
	# Level > 0 = waiting for approval → Pending Approval
	if current_level == 0:
		expected_state = "Approved"
	else:
		expected_state = "Pending Approval"
	
	# Check if state needs correction
	if doc.workflow_state != expected_state:
		doc.db_set({
			"workflow_state": expected_state,
			"status": expected_state
		}, update_modified=False)
		frappe.db.commit()

