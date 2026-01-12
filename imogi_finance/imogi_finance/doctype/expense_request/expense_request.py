# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from imogi_finance import accounting, roles
from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.approval import (
    approval_setting_required_message,
    get_active_setting_meta,
    log_route_resolution_error,
)
from imogi_finance.budget_control.workflow import handle_expense_request_workflow, release_budget_for_request
from imogi_finance.services.approval_route_service import ApprovalRouteService
from imogi_finance.services.deferred_expense import generate_amortization_schedule
from imogi_finance.services.workflow_service import WorkflowService
from imogi_finance.tax_invoice_ocr import sync_tax_invoice_upload, validate_tax_invoice_upload_link
from imogi_finance.validators.finance_validator import FinanceValidator
from imogi_finance.workflows.workflow_engine import WorkflowEngine


def get_approval_route(cost_center: str, accounts, amount: float, *, setting_meta=None):
    """Compatibility wrapper for ApprovalRouteService.get_route used in tests and patches."""
    return ApprovalRouteService.get_route(cost_center, accounts, amount, setting_meta=setting_meta)


class ExpenseRequest(Document):
    """Main expense request document, integrating approval and accounting flows."""

    PENDING_REVIEW_STATE = "Pending Review"
    CANCEL_ALLOWED_ROLES = {roles.SYSTEM_MANAGER, roles.EXPENSE_APPROVER}
    REOPEN_ALLOWED_ROLES = {roles.SYSTEM_MANAGER}
    _workflow_service = WorkflowService()
    _workflow_engine = WorkflowEngine(
        config_path=frappe.get_app_path(
            "imogi_finance",
            "imogi_finance",
            "workflow",
            "expense_request_workflow",
            "expense_request_workflow.json",
        )
    )

    def before_validate(self):
        self.validate_amounts()

    def before_insert(self):
        self._set_requester_to_creator()
        self._reset_status_if_copied()

    def after_insert(self):
        self._auto_submit_if_skip_approval()

    def validate(self):
        self._set_requester_to_creator()
        self._ensure_status()
        self.validate_amounts()
        self.apply_branch_defaults()
        self.validate_asset_details()
        self._sync_tax_invoice_upload()
        self.validate_tax_fields()
        self.validate_deferred_expense()
        validate_tax_invoice_upload_link(self, "Expense Request")
        self._prepare_route_for_workflow()
        self.sync_status_with_workflow_state()
        self.handle_key_field_changes_after_submit()
        self.validate_pending_edit_restrictions()
        self.validate_final_state_immutability()
        self.validate_workflow_action_guard()

    def _prepare_route_for_submit(self):
        """Deprecated - route resolution now happens in before_submit only."""
        return

    def _prepare_route_for_workflow(self):
        if getattr(self, "docstatus", 0) != 0:
            return

        if not getattr(self, "cost_center", None):
            return

        if not self._get_expense_accounts():
            return

        self._resolve_and_apply_route()

    def validate_amounts(self):
        total, expense_accounts = FinanceValidator.validate_amounts(self.get("items"))
        self.amount = total
        self.expense_accounts = expense_accounts
        self.expense_account = expense_accounts[0] if len(expense_accounts) == 1 else None
        self._set_totals()

    def _set_totals(self):
        items = self.get("items") or []
        asset_items = self.get("asset_items") or []
        total_expense = flt(getattr(self, "amount", 0) or 0)
        total_asset = sum(flt(getattr(item, "amount", 0) or 0) for item in asset_items)
        total_ppn = flt(getattr(self, "ti_fp_ppn", None) or getattr(self, "ppn", None) or 0)
        total_ppnbm = flt(getattr(self, "ti_fp_ppnbm", None) or getattr(self, "ppnbm", None) or 0)
        item_pph_total = sum(
            flt(getattr(item, "pph_base_amount", 0) or 0)
            for item in items
            if getattr(item, "is_pph_applicable", 0)
        )
        total_pph = item_pph_total or flt(getattr(self, "pph_base_amount", 0) or 0)
        total_amount = total_expense + total_asset + total_ppn + total_ppnbm + total_pph

        self.total_expense = total_expense
        self.total_asset = total_asset
        self.total_ppn = total_ppn
        self.total_ppnbm = total_ppnbm
        self.total_pph = total_pph
        self.total_amount = total_amount

    def apply_branch_defaults(self):
        try:
            branch = resolve_branch(
                company=self._get_company(),
                cost_center=getattr(self, "cost_center", None),
                explicit_branch=getattr(self, "branch", None),
            )
        except Exception:
            branch = None
        if branch:
            apply_branch(self, branch)

    def validate_asset_details(self):
        if self.request_type != "Asset":
            return

        if getattr(self, "build_cumulative_asset_from_items", 0):
            self._sync_cumulative_asset_items()
            return

        asset_items = self.get("asset_items") or []
        if not asset_items:
            frappe.throw(_("Asset List is required for Asset requests."))

        for idx, item in enumerate(asset_items, start=1):
            missing_fields = []
            if not getattr(item, "asset_category", None):
                missing_fields.append(_("Asset Category"))
            if not getattr(item, "asset_name", None):
                missing_fields.append(_("Asset Name"))
            if not getattr(item, "asset_description", None):
                missing_fields.append(_("Asset Description"))
            if not getattr(item, "qty", None):
                missing_fields.append(_("Qty"))

            if missing_fields:
                frappe.throw(
                    _("Asset item row {0} requires the following fields: {1}.").format(
                        idx, _(", ").join(missing_fields)
                    )
                )

    def _sync_cumulative_asset_items(self):
        items = self.get("items") or []
        if not items:
            frappe.throw(_("Expense Items are required to build a cumulative asset."))

        header_missing = []
        if not getattr(self, "asset_category", None):
            header_missing.append(_("Asset Category"))
        if not getattr(self, "asset_name", None):
            header_missing.append(_("Asset Name"))
        if not getattr(self, "asset_description", None):
            header_missing.append(_("Asset Description"))

        if header_missing:
            frappe.throw(
                _("Cumulative asset requires the following header fields: {0}.").format(
                    _(", ").join(header_missing)
                )
            )

        total_amount = float(getattr(self, "amount", 0) or 0)
        self.set("asset_items", [])
        self.append(
            "asset_items",
            {
                "asset_category": self.asset_category,
                "asset_name": self.asset_name,
                "asset_description": self.asset_description,
                "asset_location": getattr(self, "asset_location", None),
                "qty": 1,
                "amount": total_amount,
            },
        )

    def validate_tax_fields(self):
        FinanceValidator.validate_tax_fields(self)

    def validate_deferred_expense(self):
        if not getattr(self, "is_deferred_expense", 0):
            return

        if not getattr(self, "deferred_start_date", None):
            frappe.throw(_("Deferred Start Date is required for Deferred Expense."))

        periods = getattr(self, "deferred_periods", None)
        if not periods or periods <= 0:
            frappe.throw(_("Deferred Periods must be greater than zero."))

        schedule = generate_amortization_schedule(
            getattr(self, "amount", 0) or 0, periods, self.deferred_start_date
        )
        flags = getattr(self, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            self.flags = flags
        self.flags.deferred_amortization_schedule = schedule

    def _sync_tax_invoice_upload(self):
        if not getattr(self, "ti_tax_invoice_upload", None):
            return

        sync_tax_invoice_upload(self, "Expense Request", save=False)

    def validate_final_state_immutability(self):
        """Prevent edits to key fields after approval or downstream linkage."""
        if getattr(self, "docstatus", 0) != 1 or self.status not in {"Approved", "PI Created", "Paid"}:
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

    def _reset_status_if_copied(self):
        """Ensure duplicated documents start from Draft instead of Rejected/Approved.

        When a submitted request (e.g. Rejected) is duplicated, Frappe copies the
        status and workflow_state fields. For the new draft, we want a clean start
        so users can submit it again without being stuck in a terminal state.
        """
        if getattr(self, "docstatus", 0) == 0 and getattr(self, "status", None) in {"Rejected", "Approved"}:
            self.status = None
            self.workflow_state = None
            self.current_approval_level = 0
            # Clear approval audit and route snapshot on copied drafts
            self.approved_on = None
            self.rejected_on = None
            self.approval_route_snapshot = None
            self.level_1_user = None
            self.level_2_user = None
            self.level_3_user = None

    def _ensure_status(self):
        if getattr(self, "status", None):
            if self.status == self.PENDING_REVIEW_STATE and not getattr(self, "current_approval_level", None):
                self.current_approval_level = 1
            return

        workflow_state = getattr(self, "workflow_state", None)
        if workflow_state:
            self.status = workflow_state
        else:
            self.status = "Draft"

        if self.status == self.PENDING_REVIEW_STATE:
            self.current_approval_level = getattr(self, "current_approval_level", None) or 1
        else:
            self.current_approval_level = 0

    def before_submit(self):
        """Resolve approval route and set initial workflow state."""
        self.validate_amounts()
        self.validate_submit_permission()
        self.validate_reopen_override_resolution()

        route = self._resolve_and_apply_route()

        # Jika tidak ada approval setting atau route kosong, auto-approve
        if self._skip_approval_route or not self._route_has_approver(route):
            self.current_approval_level = 0
            self.status = "Approved"
            self.workflow_state = "Approved"
            self._set_approval_audit()
            self.record_approval_route_snapshot()

            # Log untuk audit
            self._log_missing_approval_setting()

            frappe.msgprint(
                _("No approval route configured for Cost Center {0}. Request auto-approved.").format(
                    self.cost_center
                ),
                alert=True,
                indicator="green",
            )
            return

        self._ensure_route_ready(route)
        self.validate_route_users_exist(route)
        self.validate_initial_approver(route)
        initial_level = self._get_initial_approval_level(route)
        # Set workflow_action_allowed flag for ERPNext v15+ compatibility
        flags = getattr(self, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            self.flags = flags
        self.flags.workflow_action_allowed = True

        self._set_pending_review(level=initial_level)

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

        # Handle "Create PI" workflow action
        if action == "Create PI":
            next_state = kwargs.get("next_state")
            if next_state == "PI Created":
                # Call the actual Purchase Invoice creation logic
                try:
                    pi_name = accounting.create_purchase_invoice_from_request(self.name)
                    if not pi_name:
                        frappe.throw(
                            _("Failed to create Purchase Invoice. Please check validation requirements."),
                            title=_("PI Creation Failed")
                        )
                    # Update the document with the PI link
                    self.linked_purchase_invoice = pi_name
                    self.pending_purchase_invoice = None
                except Exception as e:
                    # Re-throw with clear message
                    error_msg = str(e)
                    frappe.throw(
                        _("Cannot complete 'Create PI' action: {0}").format(error_msg),
                        title=_("Purchase Invoice Creation Error")
                    )
            return

        self._workflow_engine.guard_action(
            doc=self,
            action=action,
            current_state=self.status,
            next_state=kwargs.get("next_state"),
        )
        if action == "Reopen":
            self.validate_reopen_permission()
            return

        if action in {"Approve", "Reject"}:
            self.validate_pending_route_freshness()
            self.validate_reopen_override_resolution()
            self.validate_route_users_exist()

        if not self.is_pending_review():
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
        """Handle post-workflow action state updates."""
        next_state = kwargs.get("next_state")
        if action == "Submit":
            handle_expense_request_workflow(self, action, self.status)
            return

        if action == "Approve" and next_state == "Approved":
            self.record_approval_route_snapshot()
            self.current_approval_level = 0
            self._set_approval_audit()
        if action == "Approve" and next_state == self.PENDING_REVIEW_STATE:
            self._advance_approval_level()

        if action == "Reject":
            self.current_approval_level = 0
            # Ensure approval audit fields are cleared when rejected
            self.approved_on = None
            self.rejected_on = now_datetime()

        # Validate "Create PI" action - ensure PI was actually created
        if action == "Create PI" and next_state == "PI Created":
            if not getattr(self, "linked_purchase_invoice", None):
                frappe.throw(
                    _("Cannot set status to 'PI Created' without a linked Purchase Invoice. "
                      "The Purchase Invoice creation may have failed. Please check error logs."),
                    title=_("Invalid State Transition")
                )
            self.status = next_state
            self.workflow_state = next_state
            # Don't call handle_expense_request_workflow for Create PI action
            return

        if action in {"Approve", "Reject"} and next_state:
            self.status = next_state
            self.workflow_state = next_state

        if action == "Reopen":
            self._handle_reopen_action(next_state)
            return

        handle_expense_request_workflow(self, action, next_state)

    def _handle_reopen_action(self, next_state):
        """Handle reopen workflow action."""
        self.validate_amounts()
        route, setting_meta, failed = self._resolve_approval_route()
        self._approval_route_resolution_failed = failed
        self._ensure_route_ready(route, context="reopen")
        self.validate_route_users_exist(route)
        self.clear_downstream_links()
        self.apply_route(route, setting_meta=setting_meta)
        self._skip_approval_route = self._should_skip_approval(route)

        if self._skip_approval_route:
            self.current_approval_level = 0
            self.status = "Approved"
            self.workflow_state = "Approved"
            self._set_approval_audit()
        else:
            # Set workflow_action_allowed flag for ERPNext v15+ compatibility
            flags = getattr(self, "flags", None)
            if flags is None:
                flags = type("Flags", (), {})()
                self.flags = flags
            self.flags.workflow_action_allowed = True
            self._set_pending_review(level=self._get_initial_approval_level(route))

        handle_expense_request_workflow(self, "Reopen", self.status)

    def on_cancel(self):
        release_budget_for_request(self, reason="Cancel")

    def on_submit(self):
        # Purchase Invoice creation is handled manually via action button.
        if self._should_skip_approval():
            target_state = "Approved"
            if getattr(self, "workflow_state", None) != target_state:
                self.db_set("workflow_state", target_state)
                self.workflow_state = target_state
            if getattr(self, "status", None) != target_state:
                self.db_set("status", target_state)
                self.status = target_state
            self._set_approval_audit()

        flags = getattr(self, "flags", None)
        workflow_action_allowed = bool(flags and getattr(flags, "workflow_action_allowed", False))
        if not workflow_action_allowed:
            handle_expense_request_workflow(self, "Submit", getattr(self, "status", None))

    def _set_approval_audit(self):
        """Set approval timestamp when the request reaches Approved state."""
        try:
            self.approved_on = now_datetime()
        except Exception:
            # Avoid blocking workflow if timestamp setting fails for any reason.
            pass

    def on_update_after_submit(self):
        self.sync_status_with_workflow_state()
        self._ensure_budget_lock_synced_after_approval()

    def _auto_submit_if_skip_approval(self):
	    """Auto submit dan approve jika tidak ada approval setting untuk cost center."""
	    if getattr(self, "docstatus", 0) != 0:
	        return
	
	    if getattr(self, "status", None) not in {None, "", "Draft"}:
	        return
	
	    # Cek apakah ada Expense Approval Setting untuk cost center ini
	    if not getattr(self, "cost_center", None):
	        return
	
	    # Cek apakah cost center terdaftar di Expense Approval Setting yang aktif
	    approval_setting_exists = frappe.db.exists('Expense Approval Setting', {
	        'cost_center': self.cost_center,
	        'is_active': 1
	    })
	
	    if approval_setting_exists:
	        # Ada approval setting, tidak auto-approve
	        frappe.logger("imogi_finance").info(
	            f"Expense Request {self.name} requires approval - Cost Center {self.cost_center} has active Expense Approval Setting"
	        )
	        return
	
	    # Tidak ada approval setting, proceed dengan auto-approve
	    frappe.logger("imogi_finance").info(
	        f"Auto-approving Expense Request {self.name} - No active Expense Approval Setting for Cost Center {self.cost_center}"
	    )
	
	    # Validasi amounts sebelum submit
	    self.validate_amounts()
	
	    # Set flag untuk skip approval
	    if getattr(self, "_skip_approval_route", None) is None:
	        route = {
	            "level_1": {"user": None},
	            "level_2": {"user": None},
	            "level_3": {"user": None},
	        }
	        self.apply_route(route, setting_meta=None)
	        self._skip_approval_route = True
	
	    # Set workflow state dan status langsung ke Approved
	    self.workflow_state = "Approved"
	    self.status = "Approved"
	    self.current_approval_level = 0
	    self._set_approval_audit()
	
	    # Set flag untuk allow workflow action
	    flags = getattr(self, "flags", None)
	    if flags is None:
	        flags = type("Flags", (), {})()
	        self.flags = flags
	    self.flags.workflow_action_allowed = True
	
	    try:
	        # Submit document
	        self.submit()
	        frappe.msgprint(
	            _("No approval required for this Cost Center. Request auto-approved."),
	            alert=True,
	            indicator="green",
	        )
	    except Exception as e:
	        frappe.logger("imogi_finance").error(
	            f"Failed to auto-submit Expense Request {self.name}: {str(e)}"
	        )
	        # Rollback status changes jika submit gagal
	        self.workflow_state = None
	        self.status = "Draft"
	        self.current_approval_level = 0
	        raise

    def before_cancel(self):
        self.validate_cancel_permission()
        self.validate_cancel_without_active_links()

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

    def validate_cancel_permission(self):
        allowed = self.CANCEL_ALLOWED_ROLES
        current_roles = set(frappe.get_roles())

        if current_roles & allowed:
            return

        frappe.throw(
            _("You do not have permission to cancel this request. Required: {roles}.").format(
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
        pending_purchase_invoice = getattr(self, "pending_purchase_invoice", None)
        asset = getattr(self, "linked_asset", None)

        if payment_entry and _is_active("Payment Entry", payment_entry):
            active_links.append(_("Payment Entry {0}").format(payment_entry))

        if purchase_invoice and _is_active("Purchase Invoice", purchase_invoice):
            active_links.append(_("Purchase Invoice {0}").format(purchase_invoice))

        if (
            pending_purchase_invoice
            and pending_purchase_invoice != purchase_invoice
            and _is_active("Purchase Invoice", pending_purchase_invoice)
        ):
            active_links.append(_("Purchase Invoice {0}").format(pending_purchase_invoice))

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

    def validate_cancel_without_active_links(self):
        active_links = []

        def _is_active(doctype, name):
            docstatus = frappe.db.get_value(doctype, name, "docstatus")
            return docstatus != 2

        payment_entry = getattr(self, "linked_payment_entry", None)
        purchase_invoice = getattr(self, "linked_purchase_invoice", None)
        pending_purchase_invoice = getattr(self, "pending_purchase_invoice", None)
        asset = getattr(self, "linked_asset", None)

        if payment_entry and _is_active("Payment Entry", payment_entry):
            active_links.append(_("Payment Entry {0}").format(payment_entry))

        if purchase_invoice and _is_active("Purchase Invoice", purchase_invoice):
            active_links.append(_("Purchase Invoice {0}").format(purchase_invoice))

        if (
            pending_purchase_invoice
            and pending_purchase_invoice != purchase_invoice
            and _is_active("Purchase Invoice", pending_purchase_invoice)
        ):
            active_links.append(_("Purchase Invoice {0}").format(pending_purchase_invoice))

        if asset and _is_active("Asset", asset):
            active_links.append(_("Asset {0}").format(asset))

        if not active_links:
            return

        frappe.throw(
            _("Cannot cancel while the request is still linked to: {0}. Please cancel those documents first.").format(
                _(", ").join(active_links)
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

        configured_levels = [level for level in (1, 2, 3) if self._level_configured(level)]
        if not configured_levels:
            return

        last_level = str(configured_levels[-1])
        if current_level != last_level:
            frappe.throw(_("Cannot approve directly when further levels are configured."))

    def apply_route(self, route: dict, *, setting_meta: dict | None = None):
        """Store approval route on the document for audit and workflow guards."""
        self.level_1_user = route.get("level_1", {}).get("user")
        self.level_2_user = route.get("level_2", {}).get("user")
        self.level_3_user = route.get("level_3", {}).get("user")
        self._approval_meta_recorded_during_guard = False
        self._record_route_setting_meta(setting_meta)

    def validate_pending_route_freshness(self):
        """Require route refresh when approval configuration has changed while pending."""
        if getattr(self, "docstatus", 0) != 1:
            return

        if not self.is_pending_review():
            return

        # get_active_setting_meta returns None if not found (no exception)
        current_meta = get_active_setting_meta(self.cost_center)
        
        # No approval setting = skip freshness check
        if not current_meta:
            return

        stored_name = getattr(self, "approval_setting", None)
        stored_modified = getattr(self, "approval_setting_last_modified", None)
        metadata_missing = not stored_name and not stored_modified
        guard_injected_meta = getattr(self, "_approval_meta_recorded_during_guard", False)

        current_name = current_meta.get("name")  # Now safe
        current_modified = current_meta.get("modified")  # Now safe

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
            "level_1": {"user": getattr(self, "level_1_user", None)},
            "level_2": {"user": getattr(self, "level_2_user", None)},
            "level_3": {"user": getattr(self, "level_3_user", None)},
        }

    def record_approval_route_snapshot(self):
        """Persist the route used at final approval for later Close validation."""
        try:
            self.approval_route_snapshot = self.get_route_snapshot()
        except Exception:
            # Avoid blocking workflow if snapshot persistence fails.
            pass


    def _resolve_approval_route(self) -> tuple[dict, dict | None, bool]:
	    """Resolve approval route. Returns empty route for auto-approve if not configured."""
	    try:
	        setting_meta = get_active_setting_meta(self.cost_center)
	        
	        # Jika tidak ada setting_meta (approval setting tidak exist), return empty route
	        if setting_meta is None:
	            frappe.logger("imogi_finance").info(
	                f"No Expense Approval Setting found for Cost Center {self.cost_center} - will auto-approve"
	            )
	            return {
	                "level_1": {"user": None},
	                "level_2": {"user": None},
	                "level_3": {"user": None},
	            }, None, False
	        
	        route_result = get_approval_route(
	            self.cost_center, self._get_expense_accounts(), self.amount, setting_meta=setting_meta
	        )
	        
	        if isinstance(route_result, tuple):
	            route = route_result[0] if route_result else {}
	            if len(route_result) > 1 and setting_meta is None:
	                setting_meta = route_result[1]
	        else:
	            route = route_result
	            
	    except (frappe.DoesNotExistError, frappe.ValidationError) as exc:
	        frappe.logger("imogi_finance").info(
	            f"Approval setting not found for Cost Center {self.cost_center}: {str(exc)}"
	        )
	        # Return empty route untuk auto-approve
	        return {
	            "level_1": {"user": None},
	            "level_2": {"user": None},
	            "level_3": {"user": None},
	        }, None, False
	
	    return route, setting_meta, False

    def _resolve_and_apply_route(self) -> dict:
        route, setting_meta, failed = self._resolve_approval_route()
        self._approval_route_resolution_failed = failed
        self.apply_route(route, setting_meta=setting_meta)
        self._skip_approval_route = self._should_skip_approval(route)
        return route

    def _ensure_route_ready(self, route: dict, *, context: str = "submit"):
        """Validate route is ready for workflow progression.
        
        If no approval setting exists or resolution failed, treat as skip-approval
        (auto-approve) instead of blocking.
        """
        # Remove the error throwing - allow empty route to proceed as auto-approve
        if getattr(self, "_approval_route_resolution_failed", False):
            # Log for audit but don't block
            self._log_missing_approval_setting()
            return

        if not self._route_has_approver(route):
            return

    @staticmethod
    def _route_has_approver(route: dict | None) -> bool:
        if not route:
            return False

        return any(
            [
                route.get("level_1", {}).get("user"),
                route.get("level_2", {}).get("user"),
                route.get("level_3", {}).get("user"),
            ]
        )

    def _should_skip_approval(self, route: dict | None = None) -> bool:
        if route is not None:
            return not self._route_has_approver(route)

        flag = getattr(self, "_skip_approval_route", None)
        if flag is not None:
            return flag

        return not self._route_has_approver(self.get_route_snapshot())

    def get_current_level_key(self) -> str | None:
        if self.is_pending_review():
            level = getattr(self, "current_approval_level", None) or 0
            return str(level) if level else None

        status = getattr(self, "status", None)
        if status == "Pending Level 1":
            return "1"
        if status == "Pending Level 2":
            return "2"
        if status == "Pending Level 3":
            return "3"
        return None

    def _set_pending_review(self, *, level: int = 1):
        self.status = self.PENDING_REVIEW_STATE
        self.workflow_state = self.PENDING_REVIEW_STATE
        self.current_approval_level = level

    def _get_initial_approval_level(self, route: dict | None = None) -> int:
        route = route or self.get_route_snapshot()
        for level in (1, 2, 3):
            target = route.get(f"level_{level}", {}) if isinstance(route, dict) else {}
            if target.get("user"):
                return level
        return 1

    def is_pending_review(self) -> bool:
        return getattr(self, "status", None) == self.PENDING_REVIEW_STATE or getattr(self, "workflow_state", None) == self.PENDING_REVIEW_STATE

    def _level_configured(self, level: int) -> bool:
        if level not in {1, 2, 3}:
            return False

        user = self.get(f"level_{level}_user")
        return bool(user)

    def has_next_approval_level(self) -> bool:
        current = getattr(self, "current_approval_level", None) or 1
        for level in range(current + 1, 4):
            if self._level_configured(level):
                return True
        return False

    def _advance_approval_level(self):
        current = getattr(self, "current_approval_level", None) or 1
        for level in range(current + 1, 4):
            if self._level_configured(level):
                self.current_approval_level = level
                return
        self.current_approval_level = current

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

        if self.status in {"Approved", "PI Created", "Paid"}:
            frappe.throw(
                _("Cannot modify key fields after approval: {0}.").format(_(", ").join(changed_fields)),
                title=_("Not Allowed"),
            )

        route, setting_meta, failed = self._resolve_approval_route()
        self._approval_route_resolution_failed = failed
        self._ensure_route_ready(route)
        self.apply_route(route, setting_meta=setting_meta)
        if self._should_skip_approval(route):
            self.current_approval_level = 0
            self.status = "Approved"
            self.workflow_state = "Approved"
        else:
            # Set workflow_action_allowed flag for ERPNext v15+ compatibility
            flags = getattr(self, "flags", None)
            if flags is None:
                flags = type("Flags", (), {})()
                self.flags = flags
            self.flags.workflow_action_allowed = True
            self._set_pending_review(level=self._get_initial_approval_level(route))
        self._add_pending_edit_audit(previous)

    def sync_status_with_workflow_state(self):
        """Keep status aligned with workflow_state when workflows use a separate field."""
        self._workflow_service.sync_status(
            self,
            valid_states={
                "Draft",
                self.PENDING_REVIEW_STATE,
                "Reopened",
                "Approved",
                "Rejected",
                "PI Created",
                "Paid",
            },
        )
        if self.is_pending_review():
            self.current_approval_level = getattr(self, "current_approval_level", None) or 1
        else:
            self.current_approval_level = 0

    def validate_pending_edit_restrictions(self):
        """Limit who can edit pending requests and add audit breadcrumbs."""
        if getattr(self, "docstatus", 0) != 1:
            return

        if not self.is_pending_review():
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

        user_allowed = session_user in allowed_users

        self._add_pending_edit_audit(previous, changed_fields=audited_fields, denied=not user_allowed)

        if user_allowed:
            return

        frappe.throw(
            _("Edits while pending are restricted to routed approvers or the document owner. Please request an authorized user to update or log an audit note."),
            title=_("Not Allowed"),
        )

    def _ensure_budget_lock_synced_after_approval(self):
        """Best-effort guard to ensure budget reservations exist after approval.

        In normal flows, budget control is driven via handle_expense_request_workflow
        from on_workflow_action. This helper covers edge cases where status is
        already Approved but no reservation entries were created (for example,
        migrated documents or non-standard transitions).
        """
        try:
            from imogi_finance.budget_control import utils as budget_utils  # type: ignore
            from imogi_finance.budget_control import workflow as budget_workflow  # type: ignore
        except Exception:
            return

        try:
            settings = budget_utils.get_settings()
        except Exception:
            return

        if not settings.get("enable_budget_lock"):
            return

        target_state = settings.get("lock_on_workflow_state") or "Approved"
        status = getattr(self, "status", None)
        workflow_state = getattr(self, "workflow_state", None)
        if status != target_state and workflow_state != target_state:
            return

        name = getattr(self, "name", None)
        if not name:
            return

        try:
            existing = frappe.get_all(
                "Budget Control Entry",
                filters={
                    "ref_doctype": "Expense Request",
                    "ref_name": name,
                    "entry_type": "RESERVATION",
                    "docstatus": 1,
                },
                limit=1,
            )
        except Exception:
            existing = []

        if existing:
            return

        try:
            budget_workflow.reserve_budget_for_request(self, trigger_action="Approve", next_state=target_state)
        except Exception:
            # Fail silently; core validation and guards in budget workflow already
            # enforce consistency when features are enabled.
            return

    def validate_route_users_exist(self, route: dict | None = None):
        """Validate approval route users still exist and are enabled."""
        if route is None:
            route = self.get_route_snapshot()

        if not route:
            return

        invalid_users = []
        disabled_users = []

        for level in (1, 2, 3):
            level_data = route.get(f"level_{level}", {})
            if not isinstance(level_data, dict):
                continue

            user = level_data.get("user")
            if not user:
                continue

            if not frappe.db.exists("User", user):
                invalid_users.append(
                    {
                        "level": level,
                        "user": user,
                        "reason": "not_found",
                    }
                )
                continue

            is_enabled = frappe.db.get_value("User", user, "enabled")
            if not is_enabled:
                disabled_users.append(
                    {
                        "level": level,
                        "user": user,
                        "reason": "disabled",
                    }
                )

        error_parts = []

        if invalid_users:
            user_list = ", ".join(
                _("Level {level}: {user}").format(level=entry["level"], user=entry["user"])
                for entry in invalid_users
            )
            error_parts.append(
                _("The following approval users no longer exist: {0}").format(user_list)
            )

        if disabled_users:
            user_list = ", ".join(
                _("Level {level}: {user}").format(level=entry["level"], user=entry["user"])
                for entry in disabled_users
            )
            error_parts.append(
                _("The following approval users are disabled: {0}").format(user_list)
            )

        if not error_parts:
            return

        self._log_invalid_route_users(invalid_users, disabled_users)
        frappe.throw(
            _("{errors}. Please update the Expense Approval Setting to use valid, active users.").format(
                errors=_("; ").join(error_parts)
            ),
            title=_("Invalid Approval Route"),
        )

    def _log_invalid_route_users(self, invalid_users: list[dict], disabled_users: list[dict]):
        """Log invalid route users for audit purposes."""
        try:
            details = []
            for entry in invalid_users:
                details.append(_("Level {0}: User '{1}' not found").format(entry["level"], entry["user"]))
            for entry in disabled_users:
                details.append(_("Level {0}: User '{1}' is disabled").format(entry["level"], entry["user"]))

            if details and getattr(self, "name", None) and hasattr(self, "add_comment"):
                self.add_comment(
                    "Comment",
                    _("Approval route validation failed. {0}").format(_("; ").join(details)),
                )

            logger = getattr(frappe, "logger", None)
            if logger:
                logger("imogi_finance").warning(
                    "Invalid users in approval route",
                    extra={
                        "expense_request": getattr(self, "name", None),
                        "invalid_users": invalid_users,
                        "disabled_users": disabled_users,
                        "cost_center": self.cost_center,
                    },
                )
        except Exception:
            pass

    def validate_initial_approver(self, route: dict):
        """Ensure the approval route has at least one configured user or role."""
        if self._should_skip_approval(route):
            return
        if self._get_initial_approval_level(route):
            return

        frappe.throw(
            _("At least one approver level is required before submitting an Expense Request."),
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
        self._workflow_service.guard_status_changes(self)

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
                "Paid using unrestricted override from site config. Ensure manual audit note is added and disable the flag after emergency use. User: {user}."
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
        ApprovalRouteService.record_setting_meta(self, setting_meta)

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

    def _log_missing_approval_setting(self):
        """Log when approval setting is missing but request proceeds with auto-approve."""
        try:
            message = _(
                "No Expense Approval Setting found for Cost Center {0}. "
                "Request will be auto-approved. Configure approval settings to enable review workflow."
            ).format(self.cost_center)
            
            if getattr(self, "name", None) and hasattr(self, "add_comment"):
                self.add_comment("Comment", message)
            
            logger = getattr(frappe, "logger", None)
            if logger:
                logger("imogi_finance").info(
                    "Auto-approve due to missing approval setting",
                    extra={
                        "expense_request": getattr(self, "name", None),
                        "cost_center": self.cost_center,
                        "amount": self.amount,
                    },
                )
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
    pi_name = accounting.create_purchase_invoice_from_request(expense_request)

    if pi_name:
        frappe.db.set_value(
            "Expense Request",
            expense_request,
            {
                "workflow_state": "PI Created",
                "status": "PI Created",
                "linked_purchase_invoice": pi_name,
                "pending_purchase_invoice": None,
            },
            update_modified=True,
        )
        frappe.db.commit()

    return pi_name


@frappe.whitelist()
def mark_as_paid(expense_request: str, payment_entry: str | None = None) -> bool:
    """Mark expense request as Paid after payment is completed."""
    er = frappe.get_doc("Expense Request", expense_request)

    if er.status != "PI Created":
        frappe.throw(_("Expense Request must be in 'PI Created' status to mark as Paid."))

    er.db_set("workflow_state", "Paid")
    er.db_set("status", "Paid")

    if payment_entry:
        er.db_set("linked_payment_entry", payment_entry)

    frappe.db.commit()
    return True
