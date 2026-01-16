"""Budget approval helper functions - shared approval logic for budget requests."""

from __future__ import annotations

import frappe
from frappe import _


def get_budget_approval_route(cost_center: str) -> dict:
	"""Get approval route for budget request based on cost center.
	
	Args:
		cost_center: Cost Center name
		
	Returns:
		dict with level_1_user, level_2_user, level_3_user, approval_setting
	"""
	if not cost_center:
		frappe.throw(_("Cost Center is required for approval route resolution"))

	# Try to find specific setting for this cost center
	setting = frappe.db.get_value(
		"Budget Approval Setting",
		{"cost_center": cost_center, "is_active": 1},
		["name", "cost_center"],
		as_dict=True
	)
	
	# Fallback to system default (no cost center)
	if not setting:
		setting = frappe.db.get_value(
			"Budget Approval Setting",
			{"cost_center": ["in", ["", None]], "is_active": 1},
			["name", "cost_center"],
			as_dict=True
		)
	
	if not setting:
		frappe.throw(
			_("No active Budget Approval Setting found for Cost Center: {0} or System Default").format(cost_center)
		)

	# Get approval lines from setting
	lines = frappe.get_all(
		"Budget Approval Line",
		filters={"parent": setting.name},
		fields=["level_1_user", "level_2_user", "level_3_user"],
		limit=1
	)
	
	if not lines:
		frappe.throw(_("Budget Approval Setting {0} has no approval lines").format(setting.name))
	
	line = lines[0]
	
	return {
		"level_1_user": line.level_1_user,
		"level_2_user": line.level_2_user or None,
		"level_3_user": line.level_3_user or None,
		"approval_setting": setting.name
	}


def setup_workflow_override(doctype: str):
	"""Setup workflow override for multi-level approval.
	
	This hooks into Frappe's workflow system to handle multi-level approvals.
	Call this during app install/migrate for each doctype needing multi-level approval.
	"""
	from frappe.workflow.doctype.workflow.workflow import get_workflow_name
	
	workflow_name = get_workflow_name(doctype)
	if not workflow_name:
		return
	
	# Register workflow override hook
	frappe.workflow.set_workflow_state_on_action = override_workflow_state_on_action


def override_workflow_state_on_action(doc, workflow_state, action):
	"""Override workflow state changes for multi-level approval.
	
	This intercepts workflow actions to handle intermediate approval levels.
	"""
	# Only override for Approve action on multi-level approval doctypes
	if action != "Approve":
		return workflow_state
	
	# Check if document has multi-level approval
	if not hasattr(doc, "current_approval_level"):
		return workflow_state
	
	current_level = doc.current_approval_level or 1
	next_level = current_level + 1
	next_user = getattr(doc, f"level_{next_level}_user", None)
	
	if next_user:
		# Has more levels - stay in Pending Approval
		doc.db_set("current_approval_level", next_level, update_modified=False)
		record_approval_timestamp(doc, current_level)
		return "Pending Approval"
	else:
		# Final level - move to Approved
		doc.db_set("current_approval_level", 0, update_modified=False)
		record_approval_timestamp(doc, current_level)
		return "Approved"


def record_approval_timestamp(doc, level: int):
	"""Record approval timestamp for specific level."""
	user = frappe.session.user
	now = frappe.utils.now()
	
	approved_by_field = f"level_{level}_approved_by"
	approved_at_field = f"level_{level}_approved_at"
	
	doc.db_set(approved_by_field, user, update_modified=False)
	doc.db_set(approved_at_field, now, update_modified=False)


def validate_approver_permission(doc, action: str):
	"""Validate if current user can approve at current level."""
	if action not in ("Approve", "Reject"):
		return
	
	current_level = doc.current_approval_level or 1
	required_approver = getattr(doc, f"level_{current_level}_user", None)
	current_user = frappe.session.user
	
	# System Manager can always approve
	if "System Manager" in frappe.get_roles():
		return
	
	# Check if current user is the required approver
	if required_approver and current_user != required_approver:
		frappe.throw(
			_("Only {0} can {1} at Level {2}").format(
				required_approver, action, current_level
			)
		)
