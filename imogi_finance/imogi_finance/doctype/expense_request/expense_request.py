# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance import accounting
from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.approval import (
    approval_setting_required_message,
    get_active_setting_meta,
    get_approval_route,
    log_route_resolution_error,
)
from imogi_finance.budget_control.workflow import handle_expense_request_workflow, release_budget_for_request


class ExpenseRequest(Document):
    """Main expense request document, integrating approval and accounting flows."""

    REOPEN_ALLOWED_ROLES = {"System Manager"}

    def before_insert(self):
        self._set_requester_to_creator()

    def validate(self):
        self._set_requester_to_creator()
        self._ensure_status()
        self.validate_amounts()
        self.apply_branch_defaults()
        self.validate_asset_details()
        self.validate_tax_fields()
        self.sync_status_with_workflow_state()
        self.handle_key_field_changes_after_submit()
        self.validate_pending_edit_restrictions()
        self.validate_final_state_immutability()
        self.validate_workflow_action_guard()

    def validate_amounts(self):
        total, expense_accounts = accounting.summarize_request_items(self.get("items"))
        self.amount = total
        self.expense_accounts = expense_accounts
        self.expense_account = expense_accounts[0] if len(expense_accounts) == 1 else None

    def apply_branch_defaults(self):
        branch = resolve_branch(
            company=self._get_company(),
            cost_center=getattr(self, "cost_center", None),
            explicit_branch=getattr(self, "branch", None),
        )
        if branch:
            apply_branch(self, branch)

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

        is_ppn_applicable = getattr(self, "is_ppn_applicable", 0)
        if is_ppn_applicable and not self.ppn_template:
            frappe.throw(_("Please select a PPN Template when PPN is applicable."))

        item_pph_applicable = [item for item in items if getattr(item, "is_pph_applicable", 0)]
        is_pph_applicable = getattr(self, "is_pph_applicable", 0) or bool(item_pph_applicable)
        if is_pph_applicable:
            if not self.pph_type:
                frappe.throw(_("Please select a PPh Type when PPh is applicable."))

            if getattr(self, "is_pph_applicable", 0) and not item_pph_applicable:
                if not self.pph_base_amount or self.pph_base_amount <= 0:
                    frappe.throw(
                        _("Please enter a PPh Base Amount greater than zero when PPh is applicable.")
                    )

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
            "branch",
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

    def _set_requester_to_creator(self):
        if getattr(self, "requester", None) in {None, "", "frappe.session.user"}:
            self.requester = frappe.session.user

    def _ensure_status(self):
        if getattr(self, "status", None):
            return

        workflow_state = getattr(self, "workflow_state", None)
        if workflow_state:
            self.status = workflow_state
        else:
            self.status = "Draft"

    def before_submit(self):
        """Resolve approval route and set initial workflow state."""
        self.validate_amounts()
        try:
            setting_meta = get_active_setting_meta(self.cost_center)
            route = get_approval_route(
                self.cost_center, self._get_expense_accounts(), self.amount, setting_meta=setting_meta
            )
        except (frappe.DoesNotExistError, frappe.ValidationError) as exc:
            log_route_resolution_error(
                exc,
                cost_center=self.cost_center,
                accounts=self._get_expense_accounts(),
                amount=self.amount,
            )
            frappe.throw(approval_setting_required_message(self.cost_center))

        self.apply_route(route, setting_meta=setting_meta)
        self.validate_initial_approver(route)
        self.status = "Pending Level 1"

    def before_workflow_action(self, action, **kwargs):
        """Gate workflow transitions by the resolved approver route.

        The workflow definition intentionally uses broad role access (\"All\").
        Permission is enforced here by matching the dynamic route stored on the
        document so workflow maintainers don't need to manage static roles that
        could conflict with routed approvers.
        """
        self._ensure_status()
        flags = getattr(self, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            self.flags = flags
        self.flags.workflow_action_allowed = True
        if action == "Submit":
            self.validate_submit_permission()
            self.validate_reopen_override_resolution()
            return

        if action == "Reopen":
            self.validate_reopen_permission()
            return

        if action == "Close":
            if self.status not in {"Linked", "Closed"}:
                frappe.throw(
                    _("Close action is only allowed when the request is Linked or already Closed."),
                    title=_("Not Allowed"),
                )

            self.validate_close_permission()
            return

        if action in {"Approve", "Reject"}:
            self.validate_pending_route_freshness()
            self.validate_reopen_override_resolution()

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
        next_state = kwargs.get("next_state")
        if action == "Approve" and next_state == "Approved":
            self.record_approval_route_snapshot()

        if action in {"Approve", "Reject", "Close", "Submit"} and next_state:
            self.status = next_state

        if action != "Reopen":
            handle_expense_request_workflow(self, action, next_state)
            return

        try:
            self.validate_amounts()
            setting_meta = get_active_setting_meta(self.cost_center)
            route = get_approval_route(
                self.cost_center, self._get_expense_accounts(), self.amount, setting_meta=setting_meta
            )
            self.clear_downstream_links()
            self.apply_route(route, setting_meta=setting_meta)
            self.status = next_state or "Pending Level 1"
        except (frappe.DoesNotExistError, frappe.ValidationError) as exc:
            log_route_resolution_error(
                exc,
                cost_center=self.cost_center,
                accounts=self._get_expense_accounts(),
                amount=self.amount,
            )
            frappe.throw(approval_setting_required_message(self.cost_center))

        handle_expense_request_workflow(self, action, next_state)

    def on_cancel(self):
        release_budget_for_request(self)

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

    def validate_reopen_override_resolution(self):
        """Ensure downstream links overridden during reopen are resolved before progressing."""
        recorded_links = getattr(self, "reopen_override_links", None)
        if not recorded_links:
            recorded_links = getattr(getattr(self, "flags", None), "reopen_override_links", None)

        if not recorded_links:
            return

        active_links = self._collect_active_links(recorded_links)
        if not active_links:
            return

        frappe.throw(
            _(
                "Downstream documents reopened with override remain active: {links}. Please cancel/close them before continuing."
            ).format(links=_(", ").join(active_links)),
            title=_("Downstream Links Active"),
        )

    def validate_reopen_without_active_links(self):
        active_links = []
        active_link_refs = []

        def _is_active(doctype, name):
            docstatus = frappe.db.get_value(doctype, name, "docstatus")
            if docstatus != 2:
                active_link_refs.append({"doctype": doctype, "name": name, "docstatus": docstatus})
                return True
            return False

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
            self.reopen_override_links = []
            return

        allow_site_override = getattr(
            getattr(frappe, "conf", None), "imogi_finance_allow_reopen_with_active_links", False
        )
        allow_request_override = getattr(self, "allow_reopen_with_active_links", False)

        if allow_site_override or allow_request_override:
            self.reopen_override_links = active_link_refs
            self._add_reopen_override_audit(active_links, allow_site_override, allow_request_override)
            notifier = getattr(frappe, "msgprint", None)
            if notifier:
                notifier(
                    _(
                        "Reopening while downstream documents remain active: {links}. Please cancel or audit them to prevent duplicate processing and complete the reopening checklist (cancel/close related Purchase Invoice, Payment Entry, or Asset as needed)."
                    ).format(links=_(", ").join(active_links)),
                    alert=True,
                )
            flags = getattr(self, "flags", None)
            if flags is None:
                flags = type("Flags", (), {})()
                self.flags = flags
            self.flags.reopen_override_links = active_links
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
            self._add_unrestricted_close_audit()
            return

        target_amount = getattr(self, "amount", None)
        if target_amount is None:
            target_amount, account_summary = accounting.summarize_request_items(self.get("items"))
            self.amount = target_amount

        try:
            setting_meta = get_active_setting_meta(self.cost_center)
            fresh_route = get_approval_route(
                self.cost_center, self._get_expense_accounts(), target_amount, setting_meta=setting_meta
            )
        except (frappe.DoesNotExistError, frappe.ValidationError) as exc:
            log_route_resolution_error(
                exc,
                cost_center=self.cost_center,
                accounts=self._get_expense_accounts(),
                amount=target_amount,
            )
            fresh_route = None

        route_for_close = fresh_route if self._route_has_approver(fresh_route) else None
        if route_for_close is None:
            snapshot_route = self.get_route_snapshot()
            route_for_close = snapshot_route if self._route_has_approver(snapshot_route) else None

        if not route_for_close:
            frappe.throw(
                _(
                    "Unable to validate current or saved approver route for closing. Please refresh the Expense Approval Setting or reopen this request to rebuild the approval route."
                ),
                title=_("Not Allowed"),
            )

        allowed_roles = [
            role
            for role in (
                route_for_close.get("level_1", {}).get("role"),
                route_for_close.get("level_2", {}).get("role"),
                route_for_close.get("level_3", {}).get("role"),
            )
            if role
        ]
        allowed_users = [
            user
            for user in (
                route_for_close.get("level_1", {}).get("user"),
                route_for_close.get("level_2", {}).get("user"),
                route_for_close.get("level_3", {}).get("user"),
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

    def apply_route(self, route: dict, *, setting_meta: dict | None = None):
        """Store approval route on the document for audit and workflow guards."""
        self.level_1_role = route.get("level_1", {}).get("role")
        self.level_1_user = route.get("level_1", {}).get("user")
        self.level_2_role = route.get("level_2", {}).get("role")
        self.level_2_user = route.get("level_2", {}).get("user")
        self.level_3_role = route.get("level_3", {}).get("role")
        self.level_3_user = route.get("level_3", {}).get("user")
        self._approval_meta_recorded_during_guard = False
        self._record_route_setting_meta(setting_meta)

    def validate_pending_route_freshness(self):
        """Require route refresh when approval configuration has changed while pending."""
        if getattr(self, "docstatus", 0) != 1:
            return

        if self.status not in {"Pending Level 1", "Pending Level 2", "Pending Level 3"}:
            return

        try:
            current_meta = get_active_setting_meta(self.cost_center)
        except Exception:
            return

        stored_name = getattr(self, "approval_setting", None)
        stored_modified = getattr(self, "approval_setting_last_modified", None)
        metadata_missing = not stored_name and not stored_modified
        guard_injected_meta = getattr(self, "_approval_meta_recorded_during_guard", False)

        current_name = current_meta.get("name")
        current_modified = current_meta.get("modified")

        document_dt = self._parse_datetime(
            getattr(self, "modified", None) or getattr(self, "creation", None)
        )
        current_dt = self._parse_datetime(current_modified)

        if (metadata_missing or guard_injected_meta) and document_dt and current_dt and current_dt > document_dt:
            self._record_route_setting_meta(current_meta)
            self._approval_meta_recorded_during_guard = True
            self._add_stale_route_comment(
                current_meta,
                _("Expense Approval Setting {0} was updated after this request was submitted.").format(
                    current_name or _("(unknown)")
                ),
            )
            frappe.throw(
                _(
                    "Approval configuration changed after submission. Please refresh the route (reopen or toggle a key field) before approving."
                ),
                title=_("Route Refresh Required"),
            )

        if metadata_missing:
            self._record_route_setting_meta(current_meta)
            self._approval_meta_recorded_during_guard = True
            return

        stored_name = getattr(self, "approval_setting", None)
        stored_modified = getattr(self, "approval_setting_last_modified", None)

        if stored_name and current_name and stored_name != current_name:
            self._add_stale_route_comment(
                current_meta, _("Active Expense Approval Setting changed from {0} to {1}.").format(stored_name, current_name)
            )
            frappe.throw(
                _("Approval configuration changed. Please reopen or refresh key fields to rebuild the approval route before continuing."),
                title=_("Route Refresh Required"),
            )

        stored_dt = self._parse_datetime(stored_modified)
        current_dt = self._parse_datetime(current_modified)
        if stored_dt and current_dt and current_dt > stored_dt:
            self._add_stale_route_comment(
                current_meta,
                _("Expense Approval Setting {0} was updated after this route was calculated.").format(
                    current_name or _("(unknown)")
                ),
            )
            frappe.throw(
                _("Approval configuration was updated after this request entered Pending. Please refresh the route (reopen or toggle a key field) before approving."),
                title=_("Route Refresh Required"),
            )

    def get_route_snapshot(self) -> dict:
        snapshot = getattr(self, "approval_route_snapshot", None)
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except Exception:
                snapshot = None

        if snapshot:
            return snapshot

        return {
            "level_1": {"role": getattr(self, "level_1_role", None), "user": getattr(self, "level_1_user", None)},
            "level_2": {"role": getattr(self, "level_2_role", None), "user": getattr(self, "level_2_user", None)},
            "level_3": {"role": getattr(self, "level_3_role", None), "user": getattr(self, "level_3_user", None)},
        }

    def record_approval_route_snapshot(self):
        """Persist the route used at final approval for later Close validation."""
        try:
            self.approval_route_snapshot = self.get_route_snapshot()
        except Exception:
            # Avoid blocking workflow if snapshot persistence fails.
            pass

    @staticmethod
    def _route_has_approver(route: dict | None) -> bool:
        if not route:
            return False

        return any(
            [
                route.get("level_1", {}).get("role"),
                route.get("level_1", {}).get("user"),
                route.get("level_2", {}).get("role"),
                route.get("level_2", {}).get("user"),
                route.get("level_3", {}).get("role"),
                route.get("level_3", {}).get("user"),
            ]
        )

    def get_current_level_key(self) -> str | None:
        status = getattr(self, "status", None)
        if status == "Pending Level 1":
            return "1"
        if status == "Pending Level 2":
            return "2"
        if status == "Pending Level 3":
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

        key_fields = ("amount", "cost_center", "branch")
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

        setting_meta = get_active_setting_meta(self.cost_center)
        route = get_approval_route(
            self.cost_center, self._get_expense_accounts(), self.amount, setting_meta=setting_meta
        )
        self.apply_route(route, setting_meta=setting_meta)
        self.status = "Pending Level 1"
        flags = getattr(self, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            self.flags = flags
        self.flags.workflow_action_allowed = True
        self._add_pending_edit_audit(previous)

    def sync_status_with_workflow_state(self):
        """Keep status aligned with workflow_state when workflows use a separate field."""
        workflow_state = getattr(self, "workflow_state", None)
        if not workflow_state:
            return

        valid_states = {
            "Draft",
            "Pending Level 1",
            "Pending Level 2",
            "Pending Level 3",
            "Approved",
            "Rejected",
            "Linked",
            "Closed",
        }
        if workflow_state not in valid_states:
            return

        current_status = getattr(self, "status", None)
        if current_status == workflow_state:
            return

        self.status = workflow_state
        flags = getattr(self, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            self.flags = flags
        self.flags.workflow_action_allowed = True

    def validate_pending_edit_restrictions(self):
        """Limit who can edit pending requests and add audit breadcrumbs."""
        if getattr(self, "docstatus", 0) != 1:
            return

        if self.status not in {"Pending Level 1", "Pending Level 2", "Pending Level 3"}:
            return

        session_user = getattr(getattr(frappe, "session", None), "user", None)
        if not session_user:
            return

        previous = self._get_previous_doc()
        if not previous:
            return

        changed_fields = self._get_pending_change_fields(previous)
        if not changed_fields:
            return

        allowed_pending_fields = self._get_pending_edit_allowed_fields()
        audited_fields = [field for field in changed_fields if field not in allowed_pending_fields]

        if not audited_fields:
            return

        allowed_roles = {
            role
            for role in {
                getattr(self, "level_1_role", None),
                getattr(self, "level_2_role", None),
                getattr(self, "level_3_role", None),
                "System Manager",
            }
            if role
        }
        allowed_users = {
            user
            for user in {
                getattr(self, "level_1_user", None),
                getattr(self, "level_2_user", None),
                getattr(self, "level_3_user", None),
                getattr(self, "owner", None),
            }
            if user
        }

        role_allowed = bool(set(frappe.get_roles()) & allowed_roles)
        user_allowed = session_user in allowed_users

        self._add_pending_edit_audit(previous, changed_fields=audited_fields, denied=not (role_allowed or user_allowed))

        if role_allowed or user_allowed:
            return

        frappe.throw(
            _("Edits while pending are restricted to routed approvers or the document owner. Please request an authorized user to update or log an audit note."),
            title=_("Not Allowed"),
        )

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
        self.pending_purchase_invoice = None

    def validate_workflow_action_guard(self):
        """Block status mutations that bypass workflow enforcement."""
        flags_obj = getattr(self, "flags", None)
        if flags_obj and getattr(flags_obj, "workflow_action_allowed", False):
            return

        flags = getattr(frappe, "flags", None)
        if getattr(flags, "in_patch", False) or getattr(flags, "in_install", False):
            return

        previous = self._get_previous_doc()
        if not previous or getattr(previous, "docstatus", None) != getattr(self, "docstatus", None):
            return

        if getattr(previous, "status", None) == getattr(self, "status", None):
            return

        frappe.throw(
            _("Status changes must be performed via workflow actions."),
            title=_("Not Allowed"),
        )

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

    def _get_company(self) -> str | None:
        cached_company = getattr(self, "_cached_company", None)
        if cached_company is not None:
            return cached_company

        company = None
        cost_center = getattr(self, "cost_center", None)
        if cost_center:
            company = frappe.db.get_value("Cost Center", cost_center, "company")

        self._cached_company = company
        return company

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

    def _get_pending_edit_allowed_fields(self) -> set[str]:
        def _parse_fields(source) -> set[str]:
            if not source:
                return set()

            if isinstance(source, str):
                raw_fields = source.replace("\n", ",").split(",")
                return {field.strip() for field in raw_fields if field and field.strip()}

            if isinstance(source, (list, tuple, set)):
                return {str(field) for field in source if field}

            return set()

        allowed = set()
        allowed.update(_parse_fields(getattr(getattr(frappe, "conf", None), "pending_edit_allowed_fields", None)))
        allowed.update(_parse_fields(getattr(self, "pending_edit_allowed_fields", None)))
        return allowed

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

    def _add_pending_edit_audit(self, previous=None, changed_fields: list[str] | None = None, denied: bool = False):
        """Record audit comment for edits performed while Pending."""
        if not getattr(self, "name", None) or not hasattr(self, "add_comment"):
            return

        try:
            fields_text = _(", ").join(changed_fields) if changed_fields else _("unspecified fields")
            action_text = _("attempted") if denied else _("made")
            self.add_comment(
                "Comment",
                _(
                    "User {user} {action} edits on pending request (fields: {fields}). Pending edits are tracked; ensure changes are justified."
                ).format(
                    user=getattr(getattr(frappe, "session", None), "user", None),
                    action=action_text,
                    fields=fields_text,
                ),
            )
        except Exception:
            pass

    def _get_pending_change_fields(self, previous) -> list[str]:
        monitored_fields = (
            "amount",
            "cost_center",
            "project",
            "currency",
            "description",
            "attachment",
            "pph_type",
            "pph_base_amount",
            "supplier_invoice_no",
            "supplier_invoice_date",
            "expense_accounts",
        )

        system_fields = {
            "name",
            "owner",
            "creation",
            "modified",
            "modified_by",
            "docstatus",
            "idx",
            "doctype",
            "flags",
            "_doc_before_save",
            "pending_edit_allowed_fields",
            "items",
        }

        dynamic_fields = set(getattr(previous, "__dict__", {}) or {}).union(self.__dict__ or {})
        candidate_fields = [field for field in monitored_fields if field not in system_fields]
        for field in sorted(dynamic_fields):
            if field in system_fields or field in monitored_fields or field.startswith("_"):
                continue

            current_value = getattr(self, field, None)
            previous_value = getattr(previous, field, None)
            if callable(current_value) or callable(previous_value):
                continue

            candidate_fields.append(field)

        changed = [field for field in candidate_fields if self._get_value(previous, field) != self.get(field)]
        return changed

    def _add_reopen_override_audit(self, active_links: list[str], site_override: bool, request_override: bool):
        """Record an audit trail when reopening is forced with active downstream links."""
        try:
            source = []
            if site_override:
                source.append(_("site config"))
            if request_override:
                source.append(_("request override"))

            source_text = _(" and ").join(source) if source else _("unknown override")
            message = _(
                "Reopened with active links: {links}. Override source: {source}. User: {user}. Complete the mandatory reopen checklist and disable any override flags after resolving downstream documents."
            ).format(
                links=_(", ").join(active_links),
                source=source_text,
                user=getattr(getattr(frappe, "session", None), "user", None),
            )

            if getattr(self, "name", None) and hasattr(self, "add_comment"):
                self.add_comment("Comment", message)

            logger = getattr(frappe, "logger", None)
            if logger:
                try:
                    logger("imogi_finance").warning(
                        "Reopen override used with active links",
                        extra={
                            "expense_request": getattr(self, "name", None),
                            "active_links": active_links,
                            "site_override": site_override,
                            "request_override": request_override,
                            "session_user": getattr(getattr(frappe, "session", None), "user", None),
                        },
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _collect_active_links(self, recorded_links) -> list[str]:
        """Return user-facing list of still-active links from stored reopen overrides."""
        parsed_links = recorded_links
        if isinstance(recorded_links, str):
            try:
                parsed_links = json.loads(recorded_links)
            except Exception:
                parsed_links = [recorded_links]

        if not isinstance(parsed_links, (list, tuple)):
            parsed_links = [parsed_links]

        active_links = []

        def _append_active(doctype, name):
            if not doctype or not name:
                return
            status = frappe.db.get_value(doctype, name, "docstatus")
            if status != 2:
                active_links.append(_("{0} {1}").format(doctype, name))

        for entry in parsed_links:
            if isinstance(entry, dict):
                _append_active(entry.get("doctype"), entry.get("name"))
            else:
                # fall back to current link fields if only names were captured
                if entry == getattr(self, "linked_payment_entry", None):
                    _append_active("Payment Entry", entry)
                elif entry == getattr(self, "linked_purchase_invoice", None):
                    _append_active("Purchase Invoice", entry)
                elif entry == getattr(self, "linked_asset", None):
                    _append_active("Asset", entry)

        # also re-check current link fields in case overrides were not stored as references
        current_links = {
            "Payment Entry": getattr(self, "linked_payment_entry", None),
            "Purchase Invoice": getattr(self, "linked_purchase_invoice", None),
            "Asset": getattr(self, "linked_asset", None),
        }
        for doctype, name in current_links.items():
            if name:
                _append_active(doctype, name)

        return sorted(set(active_links))

    def _add_unrestricted_close_audit(self):
        """Record when unrestricted close override is used to bypass route validation."""
        try:
            message = _(
                "Closed using unrestricted override from site config. Ensure manual audit note is added and disable the flag after emergency use. User: {user}."
            ).format(user=getattr(getattr(frappe, "session", None), "user", None))

            if getattr(self, "name", None) and hasattr(self, "add_comment"):
                self.add_comment("Comment", message)

            logger = getattr(frappe, "logger", None)
            if logger:
                try:
                    logger("imogi_finance").warning(
                        "Unrestricted close override used",
                        extra={
                            "expense_request": getattr(self, "name", None),
                            "session_user": getattr(getattr(frappe, "session", None), "user", None),
                        },
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _record_route_setting_meta(self, setting_meta: dict | None):
        if not setting_meta:
            return

        if isinstance(setting_meta, str):
            self.approval_setting = setting_meta
            return

        if not isinstance(setting_meta, dict):
            self.approval_setting = str(setting_meta)
            return

        self.approval_setting = setting_meta.get("name") or self.approval_setting
        if setting_meta.get("modified") is not None:
            self.approval_setting_last_modified = setting_meta.get("modified")

    def _add_stale_route_comment(self, current_meta: dict, message: str):
        if not getattr(self, "name", None) or not hasattr(self, "add_comment"):
            return

        try:
            detail = _(
                "{message} Current setting modified: {modified}. Perform a controlled reopen or safe key-field refresh to rebuild the route."
            ).format(message=message, modified=current_meta.get("modified") or _("unknown"))
            self.add_comment("Comment", detail)
        except Exception:
            pass

    @staticmethod
    def _parse_datetime(value):
        if not value:
            return None

        try:
            from frappe.utils import get_datetime
        except Exception:
            get_datetime = None

        if get_datetime:
            try:
                return get_datetime(value)
            except Exception:
                pass

        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None


@frappe.whitelist()
def create_purchase_invoice(expense_request: str) -> str:
    """Whitelisted helper to build a Purchase Invoice from an Expense Request."""
    return accounting.create_purchase_invoice_from_request(expense_request)
