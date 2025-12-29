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
        self.handle_key_field_changes_after_submit()
        self.validate_final_state_immutability()

    def validate_amounts(self):
        if self.amount is None or self.amount <= 0:
            frappe.throw(_("Amount must be greater than zero."))

    def validate_asset_details(self):
        if self.request_type != "Asset":
            return

        missing_fields = []

        if not self.asset_category:
            missing_fields.append(_("Asset Category"))
        if not self.asset_name:
            missing_fields.append(_("Asset Name"))
        if not self.asset_description:
            missing_fields.append(_("Asset Description"))

        if missing_fields:
            frappe.throw(
                _("Asset requests require the following fields: {0}.").format(
                    _(", ").join(missing_fields)
                )
            )

    def validate_tax_fields(self):
        is_ppn_applicable = getattr(self, "is_ppn_applicable", 0)
        if is_ppn_applicable and not self.ppn_template:
            frappe.throw(_("Please select a PPN Template when PPN is applicable."))

        is_pph_applicable = getattr(self, "is_pph_applicable", 0)
        if is_pph_applicable:
            if not self.pph_type:
                frappe.throw(_("Please select a PPh Type when PPh is applicable."))
            if not self.pph_base_amount or self.pph_base_amount <= 0:
                frappe.throw(_("Please enter a PPh Base Amount greater than zero when PPh is applicable."))

    def validate_final_state_immutability(self):
        """Prevent edits to key fields after approval or downstream linkage."""
        if self.docstatus != 1 or self.status not in {"Approved", "Linked", "Closed"}:
            return

        previous = self._get_previous_doc()

        if not previous:
            return

        key_fields = (
            "request_type",
            "supplier",
            "expense_account",
            "amount",
            "currency",
            "cost_center",
            "project",
            "asset_category",
            "asset_name",
            "asset_description",
            "asset_location",
        )

        changed_fields = [
            field for field in key_fields if self._get_value(previous, field) != self.get(field)
        ]

        if changed_fields:
            frappe.throw(
                _("Cannot modify key fields after approval: {0}.").format(_(", ").join(changed_fields)),
                title=_("Not Allowed"),
            )

    def before_submit(self):
        """Resolve approval route and set initial workflow state."""
        route = get_approval_route(self.cost_center, self.expense_account, self.amount)
        self.apply_route(route)
        self.status = "Pending Level 1"

    def before_workflow_action(self, action, **kwargs):
        """Gate workflow transitions by the resolved approver route.

        The workflow definition intentionally uses broad role access (\"All\").
        Permission is enforced here by matching the dynamic route stored on the
        document so workflow maintainers don't need to manage static roles that
        could conflict with routed approvers.
        """
        if action == "Close" and self.status in {"Linked", "Closed"}:
            self.validate_close_permission()
            return

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
            self.validate_not_skipping_levels(action, kwargs.get("next_state"))
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

    def validate_close_permission(self):
        """Validate that the user may close linked expense requests.

        Closing is allowed when:
        - The site configuration flag ``imogi_finance_allow_unrestricted_close`` is set.
        - The user matches any routed approver user.
        - The user has any routed approver role.
        """
        if getattr(getattr(frappe, "conf", None), "imogi_finance_allow_unrestricted_close", False):
            return

        allowed_roles = [
            role
            for role in (
                getattr(self, "level_1_role", None),
                getattr(self, "level_2_role", None),
                getattr(self, "level_3_role", None),
            )
            if role
        ]
        allowed_users = [
            user
            for user in (
                getattr(self, "level_1_user", None),
                getattr(self, "level_2_user", None),
                getattr(self, "level_3_user", None),
            )
            if user
        ]

        if not allowed_roles and not allowed_users:
            return

        user_allowed = getattr(getattr(frappe, "session", None), "user", None) in allowed_users
        role_allowed = bool(set(frappe.get_roles()) & set(allowed_roles))

        if user_allowed or role_allowed:
            return

        requirements = []
        if allowed_users:
            requirements.append(_("one of the users ({0})").format(_(", ").join(allowed_users)))
        if allowed_roles:
            requirements.append(_("one of the roles ({0})").format(_(", ").join(allowed_roles)))

        frappe.throw(
            _("You do not have permission to close this request. Required: {requirements}.").format(
                requirements=_(" or ").join(requirements)
            ),
            title=_("Not Allowed"),
        )

    def validate_not_skipping_levels(self, action: str, next_state: str | None):
        """Ensure approval follows each configured level before reaching Approved."""
        if action != "Approve" or not next_state:
            return

        current_level = self.get_current_level_key()
        if not current_level or next_state != "Approved":
            return

        level_2_role = self.get("level_2_role")
        level_2_user = self.get("level_2_user")
        level_3_role = self.get("level_3_role")
        level_3_user = self.get("level_3_user")

        if current_level == "1" and (level_2_role or level_2_user or level_3_role or level_3_user):
            frappe.throw(_("Cannot approve directly when further levels are configured."))

        if current_level == "2" and (level_3_role or level_3_user):
            frappe.throw(_("Cannot approve directly when further levels are configured."))

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

    def handle_key_field_changes_after_submit(self):
        """React to key field changes on submitted documents.

        When key fields change post-submit, approval must restart from level 1 with
        a recomputed route. Final states remain immutable and will raise a validation
        error instead.
        """
        if self.docstatus != 1:
            return

        previous = self._get_previous_doc()
        if not previous:
            return

        key_fields = ("amount", "expense_account", "cost_center")
        changed_fields = [
            field for field in key_fields if self._get_value(previous, field) != self.get(field)
        ]

        if not changed_fields:
            return

        if self.status in {"Approved", "Linked", "Closed"}:
            frappe.throw(
                _("Cannot modify key fields after approval: {0}.").format(_(", ").join(changed_fields)),
                title=_("Not Allowed"),
            )

        route = get_approval_route(self.cost_center, self.expense_account, self.amount)
        self.apply_route(route)
        self.status = "Pending Level 1"

    @staticmethod
    def _get_value(source, field):
        if hasattr(source, "get"):
            return source.get(field)
        return getattr(source, field, None)

    def _get_previous_doc(self):
        previous = getattr(self, "_doc_before_save", None)
        if not previous and hasattr(self, "get_doc_before_save"):
            try:
                previous = self.get_doc_before_save()
            except Exception:
                previous = None

        return previous


@frappe.whitelist()
def create_purchase_invoice(expense_request: str) -> str:
    """Whitelisted helper to build a Purchase Invoice from an Expense Request."""
    return accounting.create_purchase_invoice_from_request(expense_request)
