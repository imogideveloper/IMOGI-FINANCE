# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.budget_control import service, utils
from imogi_finance import budget_approval


class AdditionalBudgetRequest(Document):
	"""Request to top-up budget allocation with multi-level approval."""

	def validate(self):
		"""Validate document before save."""
		if not self.amount or float(self.amount) <= 0:
			frappe.throw(_("Amount must be greater than zero"))

	def before_submit(self):
		"""Resolve approval route before submission."""
		if not self.cost_center:
			frappe.throw(_("Cost Center is required"))
		
		# Get approval route based on cost_center
		route = budget_approval.get_budget_approval_route(self.cost_center)
		
		# Store approval route
		self.approval_setting = route["approval_setting"]
		self.level_1_user = route["level_1_user"]
		self.level_2_user = route.get("level_2_user")
		self.level_3_user = route.get("level_3_user")
		
		# Initialize at level 1
		self.current_approval_level = 1

	def before_workflow_action(self, workflow_state_name, action):
		"""Handle multi-level approval before workflow executes."""
		if action == "Approve":
			# Validate approver permission
			budget_approval.validate_approver_permission(self, "Approve")
			
			# Get current and next level
			current_level = self.current_approval_level or 1
			next_level = current_level + 1
			next_user = getattr(self, f"level_{next_level}_user", None)
			
			# Record approval timestamp
			budget_approval.record_approval_timestamp(self, current_level)
			
			if next_user:
				# More levels exist - advance to next level
				self.db_set("current_approval_level", next_level, update_modified=False)
				self.db_set("workflow_state", "Pending Approval", update_modified=False)
				self.reload()
				
				# Prevent workflow from proceeding
				frappe.throw(_("Approval Level {0} completed. Now waiting for Level {1} approval from {2}").format(
					current_level, next_level, next_user
				))
			else:
				# Final level - reset and allow workflow to proceed to Approved
				self.db_set("current_approval_level", 0, update_modified=False)
		
		elif action == "Reject":
			# Validate approver permission
			budget_approval.validate_approver_permission(self, "Reject")
			# Reset approval level
			self.db_set("current_approval_level", 0, update_modified=False)

	def on_update_after_submit(self):
		"""Execute budget supplement when approved."""
		if self.workflow_state == "Approved" and not self.get("_budget_executed"):
			self._execute_budget_supplement()
			self.db_set("_budget_executed", 1, update_modified=False)

	def _execute_budget_supplement(self):
		"""Execute budget supplement after approval."""
		settings = utils.get_settings()
		if not settings.get("enable_additional_budget"):
			return

		dims = service.resolve_dims(
			company=self.company,
			fiscal_year=self.fiscal_year,
			cost_center=self.cost_center,
			account=self.account,
			project=self.project,
			branch=self.branch,
		)
		
		service.record_supplement(
			dims=dims,
			amount=float(self.amount),
			ref_doctype="Additional Budget Request",
			ref_name=self.name,
		)
