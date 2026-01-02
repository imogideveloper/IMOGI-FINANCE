from __future__ import annotations

import frappe
from frappe.model.document import Document


DEFAULT_SETTINGS = {
	"enable_branch_expense_request": 1,
	"default_expense_account": None,
	"require_employee": 0,
}


class BranchExpenseRequestSettings(Document):
	pass


def get_settings():
	try:
		return frappe.get_cached_doc("Branch Expense Request Settings")
	except Exception:
		try:
			return frappe.get_single("Branch Expense Request Settings")
		except Exception:
			return frappe._dict(DEFAULT_SETTINGS)
