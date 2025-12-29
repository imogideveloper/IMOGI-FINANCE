# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.approval import get_approval_route
from imogi_finance import accounting


class ExpenseRequest(Document):
    """Main expense request document, integrating approval and accounting flows."""

    def validate(self):
        self.validate_amounts()
        self.validate_asset_details()
        self.validate_tax_fields()

    def validate_amounts(self):
        if self.amount is None or self.amount <= 0:
            frappe.throw(_("Amount must be greater than zero."))

    def validate_asset_details(self):
        if self.request_type == "Asset" and not self.asset_category:
            frappe.throw(_("Asset Category is required for asset requests."))

    def validate_tax_fields(self):
        if self.is_pph_applicable and not self.pph_type:
            frappe.throw(_("Please select a PPh Type when PPh is applicable."))

    def before_submit(self):
        """Resolve approval route and set initial workflow state."""
        route = get_approval_route(self.cost_center, self.expense_account, self.amount)
        self.apply_route(route)
        self.status = "Pending Level 1"

    def before_workflow_action(self, action):
        """Gate workflow transitions by the resolved approver route."""
        if self.status not in {"Pending Level 1", "Pending Level 2", "Pending Level 3"}:
            return

        current_level = self.get_current_level_key()
        if not current_level:
            return

        role_field = f"level_{current_level}_role"
        user_field = f"level_{current_level}_user"
        expected_role = self.get(role_field)
        expected_user = self.get(user_field)

        if not expected_role and not expected_user:
            return

        role_allowed = not expected_role or expected_role in frappe.get_roles()
        user_allowed = not expected_user or expected_user == frappe.session.user

        if role_allowed and user_allowed:
            return

        requirements = []
        if expected_user:
            requirements.append(_("user '{0}'").format(expected_user))
        if expected_role:
            requirements.append(_("role '{0}'").format(expected_role))

        frappe.throw(
            _("You must be {requirements} to perform this action for the current approval level.").format(
                requirements=_(" and ").join(requirements)
            ),
            title=_("Not Allowed"),
        )

    def apply_route(self, route: dict):
        """Store approval route on the document for audit and workflow guards."""
        self.level_1_role = route.get("level_1", {}).get("role")
        self.level_1_user = route.get("level_1", {}).get("user")
        self.level_2_role = route.get("level_2", {}).get("role")
        self.level_2_user = route.get("level_2", {}).get("user")
        self.level_3_role = route.get("level_3", {}).get("role")
        self.level_3_user = route.get("level_3", {}).get("user")

    def get_current_level_key(self) -> str | None:
        if self.status == "Pending Level 1":
            return "1"
        if self.status == "Pending Level 2":
            return "2"
        if self.status == "Pending Level 3":
            return "3"
        return None


@frappe.whitelist()
def create_purchase_invoice(expense_request: str) -> str:
    """Whitelisted helper to build a Purchase Invoice from an Expense Request."""
    return accounting.create_purchase_invoice_from_request(expense_request)


@frappe.whitelist()
def create_journal_entry(expense_request: str) -> str:
    """Whitelisted helper to build a Journal Entry from an Expense Request."""
    return accounting.create_journal_entry_from_request(expense_request)
