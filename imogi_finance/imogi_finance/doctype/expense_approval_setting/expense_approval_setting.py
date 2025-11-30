# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ExpenseApprovalSetting(Document):
    """Defines approval routing rules per cost center."""

    def validate(self):
        self.ensure_unique_cost_center()
        self.validate_lines_present()

    def ensure_unique_cost_center(self):
        if not self.cost_center:
            return
        existing = frappe.db.exists(
            "Expense Approval Setting",
            {"name": ("!=", self.name), "cost_center": self.cost_center, "is_active": 1},
        )
        if existing:
            frappe.throw(
                frappe._("An active Expense Approval Setting already exists for cost center {0}").format(
                    frappe.bold(self.cost_center)
                )
            )

    def validate_lines_present(self):
        if not self.expense_approval_lines:
            frappe.throw("Please add at least one approval line to define the workflow route.")
