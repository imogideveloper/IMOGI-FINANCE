# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ExpenseApprovalSetting(Document):
    """Defines approval routing rules per cost center."""

    def validate(self):
        self.ensure_unique_cost_center()
        self.validate_lines_present()
        self.validate_default_lines()
        self.validate_amount_ranges()

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

    def validate_default_lines(self):
        defaults = [line for line in self.expense_approval_lines if getattr(line, "is_default", 0)]
        if not defaults:
            frappe.throw(
                "Add at least one Default approval line to cover new or infrequently used expense accounts."
            )

        for line in self.expense_approval_lines:
            if not getattr(line, "is_default", 0) and not getattr(line, "expense_account", None):
                frappe.throw("Expense Account is required for non-default approval lines.")

    def validate_amount_ranges(self):
        grouped = {}
        for line in self.expense_approval_lines:
            key = "__default__" if getattr(line, "is_default", 0) else getattr(line, "expense_account", None)
            if not key:
                continue

            min_amount = getattr(line, "min_amount", None)
            max_amount = getattr(line, "max_amount", None)
            if min_amount is None or max_amount is None:
                frappe.throw("Each approval line must define both Minimum Amount and Maximum Amount.")

            if min_amount > max_amount:
                frappe.throw(
                    f"Minimum Amount cannot exceed Maximum Amount for approval line {line.idx or ''} (Account: {key})."
                )

            grouped.setdefault(key, []).append(line)

        for account, lines in grouped.items():
            sorted_lines = sorted(lines, key=lambda line: (line.min_amount, line.max_amount))
            previous_max = None
            for line in sorted_lines:
                if previous_max is None:
                    if line.min_amount > 0:
                        frappe.throw(
                            f"Approval lines for {account if account != '__default__' else 'Default accounts'} must start at 0 to avoid routing gaps."
                        )
                elif line.min_amount > previous_max:
                    frappe.throw(
                        f"Approval amount ranges for {account if account != '__default__' else 'Default accounts'} cannot have gaps."
                    )

                previous_max = line.max_amount
