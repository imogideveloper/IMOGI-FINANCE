# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ExpenseApprovalSetting(Document):
    """Defines approval routing rules per cost center."""

    def validate(self):
        self.ensure_unique_cost_center()
        self.validate_lines_present()


        self.validate_default_line()
        self.validate_no_duplicate_accounts()

    def ensure_unique_cost_center(self):
        """Ensure only one active setting per cost center."""
        if not self.cost_center:
            return

        existing = frappe.db.exists(
            "Expense Approval Setting",
            {"name": ("!=", self.name), "cost_center": self.cost_center, "is_active": 1},
        )
        if existing:
            frappe.throw(

                _("An active Expense Approval Setting already exists for Cost Center {0}").format(
                    frappe.bold(self.cost_center)
                )
            )

    def validate_lines_present(self):
        """Ensure at least one approval line exists."""
        if not self.expense_approval_lines:

            frappe.throw(_("Please add at least one approval line."))


    def validate_default_line(self):
        """Ensure at least one default line exists for fallback."""
        defaults = [line for line in self.expense_approval_lines if getattr(line, "is_default", 0)]

        if not defaults:
            frappe.throw(

                _("Add at least one Default approval line (Apply to All Accounts) as fallback.")
            )

        # Non-default lines must have expense_account
        for line in self.expense_approval_lines:
            if not getattr(line, "is_default", 0) and not getattr(line, "expense_account", None):

                frappe.throw(_("Expense Account is required for non-default approval lines."))



    def validate_no_duplicate_accounts(self):
        """Ensure no duplicate expense accounts."""
        accounts = []
        for line in self.expense_approval_lines:










            if getattr(line, "is_default", 0):
                continue
            account = getattr(line, "expense_account", None)
            if account:
                if account in accounts:
                frappe.throw(

                        _("Duplicate Expense Account {0}. Each account should only have one approval line.").format(
                            frappe.bold(account)
                )












                        )
                accounts.append(account)
