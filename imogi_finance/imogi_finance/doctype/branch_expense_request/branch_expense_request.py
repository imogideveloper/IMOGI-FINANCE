from __future__ import annotations

from typing import Iterable

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from imogi_finance.branching import apply_branch
from ..branch_expense_request_settings.branch_expense_request_settings import get_settings


class BranchExpenseRequest(Document):
	STATUS_DRAFT = "Draft"
	STATUS_PENDING = "Pending Approval"
	STATUS_APPROVED = "Approved"
	STATUS_REJECTED = "Rejected"
	STATUS_CANCELLED = "Cancelled"

	def validate(self):
		settings = get_settings()
		self._ensure_enabled(settings)
		self._set_requester()
		self._set_defaults_from_company()
		self._apply_employee_branch()
		self._validate_employee_requirement(settings)
		self._validate_items(settings)
		self._update_totals()
		self._sync_status_field()

	def before_submit(self):
		self._validate_items(get_settings())
		self._update_totals()
		if not getattr(self, "branch", None):
			frappe.throw(_("Branch is required before submission."))

		if not getattr(self, "workflow_state", None):
			self.workflow_state = self.STATUS_PENDING
		self.status = self.workflow_state

	def on_workflow_action(self, action, next_state=None):
		if action in {"Approve", "Reject"} and not getattr(self, "branch", None):
			frappe.throw(_("Branch is required before applying workflow actions."))

		if next_state:
			self.workflow_state = next_state
		self._sync_status_field()

	def on_cancel(self):
		self.status = self.STATUS_CANCELLED

	def _ensure_enabled(self, settings):
		if getattr(settings, "enable_branch_expense_request", 1):
			return
		frappe.throw(_("Branch Expense Request is disabled in settings."))

	def _set_requester(self):
		if getattr(self, "requester", None) in {None, "", "frappe.session.user"}:
			self.requester = getattr(getattr(frappe, "session", None), "user", None)
		if not getattr(self, "posting_date", None):
			self.posting_date = nowdate()

	def _set_defaults_from_company(self):
		if getattr(self, "company", None) and not getattr(self, "currency", None):
			default_currency = frappe.get_cached_value("Company", self.company, "default_currency")
			if default_currency:
				self.currency = default_currency

	def _apply_employee_branch(self):
		if getattr(self, "branch", None) or not getattr(self, "employee", None):
			return

		employee_branch = frappe.db.get_value("Employee", self.employee, "branch")
		if employee_branch:
			apply_branch(self, employee_branch)

	def _validate_employee_requirement(self, settings):
		if getattr(settings, "require_employee", 0) and not getattr(self, "employee", None):
			frappe.throw(_("Employee is required for Branch Expense Request."))

	def _validate_items(self, settings):
		items = self.get("items") or []
		if not items:
			frappe.throw(_("Please add at least one item."))

		default_account = getattr(settings, "default_expense_account", None)
		for item in items:
			apply_default_amounts(item)
			if getattr(item, "qty", 0) <= 0:
				frappe.throw(_("Qty must be greater than zero for each item."))
			if getattr(item, "rate", 0) < 0:
				frappe.throw(_("Rate cannot be negative for each item."))
			if not getattr(item, "cost_center", None):
				frappe.throw(_("Cost Center is required for each item."))
			if not getattr(item, "expense_account", None) and default_account:
				item.expense_account = default_account
			item.amount = flt(item.qty) * flt(item.rate)

	def _update_totals(self):
		items: Iterable[object] = self.get("items") or []
		self.total_amount = sum(flt(getattr(item, "amount", 0)) for item in items)

	def _sync_status_field(self):
		if getattr(self, "docstatus", 0) == 2:
			self.status = self.STATUS_CANCELLED
			return

		if getattr(self, "workflow_state", None):
			self.status = self.workflow_state
			return

		if getattr(self, "docstatus", 0) == 0:
			self.status = self.STATUS_DRAFT
			return

		if getattr(self, "docstatus", 0) == 1 and not getattr(self, "status", None):
			self.status = self.STATUS_PENDING


def apply_default_amounts(item):
	item.qty = flt(getattr(item, "qty", 0)) or 0
	item.rate = flt(getattr(item, "rate", 0)) or 0
	item.amount = flt(item.qty) * flt(item.rate)
