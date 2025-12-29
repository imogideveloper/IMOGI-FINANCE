# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance import accounting
from imogi_finance.approval import get_approval_route


class ExpenseRequest(Document):
    """Main expense request document, integrating approval and accounting flows."""

    REOPEN_ALLOWED_ROLES = {"System Manager"}

    def validate(self):
        self.validate_amounts()
        self.validate_asset_details()
        self.validate_tax_fields()
        self.handle_key_field_changes_after_submit()
        self.validate_final_state_immutability()

    def validate_amounts(self):
        total, expense_accounts = accounting.summarize_request_items(self.get("items"))
        self.amount = total
        self.expense_accounts = expense_accounts
        self.expense_account = expense_accounts[0] if len(expense_accounts) == 1 else None

    def validate_asset_details(self):
        if self.request_type != "Asset":
            return

        items = self.get("items") or []
        if not items:
            return

        for item in items:
            missing_fields = []
            if not getattr(item, "asset_category", None):
                missing_fields.append(_("Asset Category"))
            if not getattr(item, "asset_name", None):
                missing_fields.append(_("Asset Name"))
            if not getattr(item, "asset_description", None):
                missing_fields.append(_("Asset Description"))

            if missing_fields:
                frappe.throw(
                    _("Asset items require the following fields: {0}.").format(
                        _(", ").join(missing_fields)
                    )
                )

    def validate_tax_fields(self):
        items = self.get("items") or []

        is_ppn_applicable = getattr(self, "is_ppn_applicable", 0) or any(
            getattr(item, "is_ppn_applicable", 0) for item in items
        )
        if is_ppn_applicable and not self.ppn_template:
            frappe.throw(_("Please select a PPN Template when PPN is applicable."))

        item_pph_applicable = [item for item in items if getattr(item, "is_pph_applicable", 0)]
        is_pph_applicable = getattr(self, "is_pph_applicable", 0) or bool(item_pph_applicable)
        if is_pph_applicable:
            if not self.pph_type:
                frappe.throw(_("Please select a PPh Type when PPh is applicable."))

            if getattr(self, "is_pph_applicable", 0) and (
                not self.pph_base_amount or self.pph_base_amount <= 0
            ):
                frappe.throw(_("Please enter a PPh Base Amount greater than zero when PPh is applicable."))

            for item in item_pph_applicable:
                base_amount = getattr(item, "pph_base_amount", None)
                if not base_amount or base_amount <= 0:
                    frappe.throw(
                        _("Please enter a PPh Base Amount greater than zero for item {0}.").format(
                            getattr(item, "description", None) or getattr(item, "expense_account", None) or item.idx
                        )
                    )

    def validate_final_state_immutability(self):
        """Prevent edits to key fields after approval or downstream linkage."""
        if getattr(self, "docstatus", 0) != 1 or self.status not in {"Approved", "Linked", "Closed"}:
            return

        previous = self._get_previous_doc()
        if not previous:
            return

        previous_accounts = self._get_expense_accounts_from_doc(previous)
        current_accounts = self._get_expense_accounts_from_doc(self)

        key_fields = (
            "request_type",
            "supplier",
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
        if previous_accounts != current_accounts:
            changed_fields.append("expense_accounts")

        if changed_fields:
            frappe.throw(
                _("Cannot modify key fields after approval: {0}.").format(_(", ").join(changed_fields)),
                title=_("Not Allowed"),
            )

    def before_submit(self):
        """Resolve approval route and set initial workflow state."""
        self.validate_amounts()
        route = get_approval_route(self.cost_center, self._get_expense_accounts(), self.amount)
        self.apply_route(route)
        self.validate_initial_approver(route)
        self.status = "Pending Level 1"

    def before_workflow_action(self, action, **kwargs):
        """Gate workflow transitions by the resolved approver route.

        The workflow definition intentionally uses broad role access (\"All\").
        Permission is enforced here by matching the dynamic route stored on the
        document so workflow maintainers don't need to manage static roles that
        could conflict with routed approvers.
        """
        if action == "Submit":
            self.validate_submit_permission()
            return

        if action == "Reopen":
            self.validate_reopen_permission()
            return

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
            if action == "Approve":
                frappe.throw(
                    _(
                        "No approver is configured for level {0}. Please refresh the approval route before approving."
                    ).format(current_level),
                    title=_("Not Allowed"),
                )
            return

        role_allowed = not expected_role or expected_role in frappe.get_roles()
        user_allowed = not expected_user or expected_user == frappe.session.user

        if role_allowed and user_allowed:
            self.validate_not_skipping_levels(action, kwargs.get("next_state"))
            return

        requirements = []
        requirement_details = []
        if expected_user:
            requirements.append(_("user '{0}'").format(expected_user))
            requirement_details.append(_("user '{0}'").format(expected_user))
        if expected_role:
            requirements.append(_("role '{0}'").format(expected_role))
            requirement_details.append(_("role '{0}'").format(expected_role))

        self._add_denied_workflow_comment(action, current_level, requirement_details)
        self._log_denied_action(action, current_level, expected_role, expected_user)
        frappe.throw(
            _("You must be {requirements} to perform this action for approval level {level}.").format(
                requirements=_(" and ").join(requirements), level=current_level
            ),
            title=_("Not Allowed"),
        )

    def on_workflow_action(self, action, **kwargs):
        """Reset approval routing when a request is reopened."""
        if action != "Reopen":
            return

        next_state = kwargs.get("next_state")
        self.clear_downstream_links()
        self.validate_amounts()
        route = get_approval_route(self.cost_center, self._get_expense_accounts(), self.amount)
        self.apply_route(route)
        self.status = next_state or "Pending Level 1"

    def validate_reopen_permission(self):
        allowed = self.REOPEN_ALLOWED_ROLES
        current_roles = set(frappe.get_roles())

        if current_roles & allowed:
            self.validate_reopen_without_active_links()
            return

        frappe.throw(
            _("You do not have permission to reopen this request. Required: {roles}.").format(
                roles=_(", ").join(sorted(allowed))
            ),
            title=_("Not Allowed"),
        )

    def validate_reopen_without_active_links(self):
        active_links = []

        def _is_active(doctype, name):
            docstatus = frappe.db.get_value(doctype, name, "docstatus")
            return docstatus != 2

        payment_entry = getattr(self, "linked_payment_entry", None)
        purchase_invoice = getattr(self, "linked_purchase_invoice", None)
        asset = getattr(self, "linked_asset", None)

        if payment_entry and _is_active("Payment Entry", payment_entry):
            active_links.append(_("Payment Entry {0}").format(payment_entry))

        if purchase_invoice and _is_active("Purchase Invoice", purchase_invoice):
            active_links.append(_("Purchase Invoice {0}").format(purchase_invoice))

        if asset and _is_active("Asset", asset):
            active_links.append(_("Asset {0}").format(asset))

        if not active_links:
            return

        frappe.throw(
            _("Cannot reopen while the request is still linked to: {0}. Please cancel those documents first.").format(
                _(", ").join(active_links)
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
            frappe.throw(
                _(
                    "No routed approver is defined to close this request. Refresh the approval route or enable unrestricted close via site config."
                ),
                title=_("Not Allowed"),
            )

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
        if getattr(self, "docstatus", 0) != 1:
            return

        previous = self._get_previous_doc()
        if not previous:
            return

        previous_accounts = self._get_expense_accounts_from_doc(previous)
        current_accounts = self._get_expense_accounts_from_doc(self)

        key_fields = ("amount", "cost_center")
        changed_fields = [
            field for field in key_fields if self._get_value(previous, field) != self.get(field)
        ]

        if previous_accounts != current_accounts:
            changed_fields.append("expense_accounts")

        if not changed_fields:
            return

        if self.status in {"Approved", "Linked", "Closed"}:
            frappe.throw(
                _("Cannot modify key fields after approval: {0}.").format(_(", ").join(changed_fields)),
                title=_("Not Allowed"),
            )

        route = get_approval_route(self.cost_center, self._get_expense_accounts(), self.amount)
        self.apply_route(route)
        self.status = "Pending Level 1"

    def validate_initial_approver(self, route: dict):
        """Ensure the first approval level has a configured user or role."""
        first_level = route.get("level_1", {}) if route else {}
        if first_level.get("role") or first_level.get("user"):
            return

        frappe.throw(
            _("Level 1 approver is required before submitting an Expense Request."),
            title=_("Not Allowed"),
        )

    def validate_submit_permission(self):
        """Restrict submission to the creator of the request."""
        session_user = getattr(getattr(frappe, "session", None), "user", None)
        if session_user == self.owner:
            return

        frappe.throw(
            _("Only the creator of this Expense Request can submit it."),
            title=_("Not Allowed"),
        )

    def clear_downstream_links(self):
        """Remove downstream links when reopening to prevent duplicate approval loops."""
        self.linked_payment_entry = None
        self.linked_purchase_invoice = None
        self.linked_asset = None

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

    def _get_expense_accounts(self) -> tuple[str, ...]:
        accounts = getattr(self, "expense_accounts", None)
        if accounts:
            return accounts

        _, expense_accounts = accounting.summarize_request_items(self.get("items"))
        self.expense_accounts = expense_accounts
        self.expense_account = expense_accounts[0] if len(expense_accounts) == 1 else None
        return expense_accounts

    @staticmethod
    def _get_expense_accounts_from_doc(doc) -> tuple[str, ...]:
        items = doc.get("items") if hasattr(doc, "get") else getattr(doc, "items", None)
        _, accounts = accounting.summarize_request_items(items)
        return accounts

    def _log_denied_action(self, action, level, expected_role, expected_user):
        logger = getattr(frappe, "logger", None)
        if not logger:
            return

        try:
            logger("imogi_finance").warning(
                "Denied workflow action",
                extra={
                    "expense_request": getattr(self, "name", None),
                    "action": action,
                    "level": level,
                    "expected_role": expected_role,
                    "expected_user": expected_user,
                    "session_user": getattr(getattr(frappe, "session", None), "user", None),
                },
            )
        except Exception:
            pass

    def _add_denied_workflow_comment(self, action, level, requirements: list[str]):
        """Add timeline comment when workflow action is denied for transparency."""
        if not getattr(self, "name", None):
            return

        try:
            requirement_text = _(", ").join(requirements) if requirements else _("No approver configured")
            self.add_comment(
                "Comment",
                _(
                    "Workflow action {action} denied at level {level}. Required: {requirements}. User: {user}."
                ).format(
                    action=action,
                    level=level,
                    requirements=requirement_text,
                    user=getattr(getattr(frappe, "session", None), "user", None),
                ),
            )
        except Exception:
            pass


@frappe.whitelist()
def create_purchase_invoice(expense_request: str) -> str:
    """Whitelisted helper to build a Purchase Invoice from an Expense Request."""
    return accounting.create_purchase_invoice_from_request(expense_request)
