from __future__ import annotations

import json
from datetime import date
from typing import Iterable

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_first_day, get_last_day, nowdate, now_datetime

from imogi_finance import accounting, roles
from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.branch_approval import (
    branch_approval_setting_required_message,
    get_active_setting_meta_for_branch,
    get_branch_approval_route,
    log_branch_route_resolution_error,
)
from imogi_finance.budget_control import ledger, service
from imogi_finance.services.deferred_expense import generate_amortization_schedule
from ..expense_deferred_settings.expense_deferred_settings import get_deferrable_account_map
from imogi_finance.tax_invoice_ocr import sync_tax_invoice_upload, validate_tax_invoice_upload_link
from imogi_finance.validators.finance_validator import FinanceValidator
from imogi_finance.validators.employee_validator import EmployeeValidator
from ..branch_expense_request_settings.branch_expense_request_settings import get_settings


def resolve_fiscal_year(posting_date, company: str | None):
    for path in ("erpnext.accounts.utils.get_fiscal_year", "frappe.utils.get_fiscal_year"):
        try:
            getter = frappe.get_attr(path)
        except Exception:
            continue

        try:
            fiscal = getter(posting_date, company=company, as_dict=True)
        except TypeError:
            fiscal = getter(posting_date, company=company)

        if isinstance(fiscal, dict):
            return fiscal
        if isinstance(fiscal, (list, tuple)) and fiscal:
            return {"name": fiscal[0]}
    return None


class BranchExpenseRequest(Document):
    STATUS_DRAFT = "Draft"
    STATUS_PENDING = "Pending Review"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CANCELLED = "Cancelled"
    PENDING_REVIEW_STATE = "Pending Review"

    def before_insert(self):
        self._set_requester()
        self._reset_status_if_copied()

    def validate(self):
        settings = get_settings()
        self._ensure_enabled(settings)
        self._set_requester()
        self._ensure_status()
        self._set_defaults_from_company()
        self._apply_employee_branch()
        self.apply_branch_defaults()
        self._set_fiscal_year()
        self._validate_employee_requirement(settings)
        self._validate_items(settings)
        self.validate_amounts()
        self._sync_tax_invoice_upload()
        self.validate_tax_fields()
        self._validate_deferred_expense()
        validate_tax_invoice_upload_link(self, "Branch Expense Request")
        self._update_totals()
        self._run_budget_checks(settings)
        self._prepare_route_for_workflow()
        self._sync_status_field()

    def before_submit(self):
        settings = get_settings()
        self._validate_items(settings)
        self.validate_amounts()
        self.apply_branch_defaults()
        self.validate_tax_fields()
        
        # Validate tax invoice OCR data if OCR is enabled and applicable
        self.validate_tax_invoice_ocr_before_submit()
        
        self._validate_deferred_expense()
        self._update_totals()
        self._set_fiscal_year()
        if not getattr(self, "branch", None):
            frappe.throw(_("Branch is required before submission."))
        self._run_budget_checks(settings, for_submit=True)

        # Resolve and apply approval route
        route = self._resolve_and_apply_route()
        self._ensure_route_ready(route)
        self.validate_route_users_exist(route)

        if self._skip_approval_route:
            self.current_approval_level = 0
            self.status = "Approved"
            self.workflow_state = "Approved"
            self.record_approval_route_snapshot()
            self._set_approval_audit()
            frappe.msgprint(
                _("No approval route configured. Request auto-approved."),
                alert=True,
                indicator="green",
            )
            return

        self.validate_initial_approver(route)
        initial_level = self._get_initial_approval_level(route)
        # Set workflow_action_allowed flag for ERPNext v15+ compatibility
        flags = getattr(self, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            self.flags = flags
        self.flags.workflow_action_allowed = True
        self._set_pending_review(level=initial_level)

    def on_workflow_action(self, action, next_state=None):
        if action in {"Approve", "Reject"} and not getattr(self, "branch", None):
            frappe.throw(_("Branch is required before applying workflow actions."))

        if action == "Submit":
            return

        if action == "Approve" and next_state == "Approved":
            self.record_approval_route_snapshot()
            self.current_approval_level = 0
        if action == "Approve" and next_state == self.PENDING_REVIEW_STATE:
            self._advance_approval_level()

        if action == "Reject":
            self.current_approval_level = 0

        if next_state:
            self.workflow_state = next_state
        self._sync_status_field()

    def on_cancel(self):
        self.status = self.STATUS_CANCELLED

    def on_trash(self):
        """Clean up OCR links and monitoring records before deletion.

        Automatically clears references to Tax Invoice OCR Upload and
        deletes any Tax Invoice OCR Monitoring records to avoid circular
        dependency issues when deleting Branch Expense Request.
        """
        from imogi_finance.tax_invoice_fields import get_upload_link_field

        # Clear Tax Invoice OCR Upload link to break circular dependency
        upload_field = get_upload_link_field("Branch Expense Request")
        if upload_field and getattr(self, upload_field, None):
            frappe.db.set_value("Branch Expense Request", self.name, upload_field, None)

        # Delete any OCR Monitoring records pointing to this Branch Expense Request
        if frappe.db.table_exists("Tax Invoice OCR Monitoring"):
            monitoring_records = frappe.get_all(
                "Tax Invoice OCR Monitoring",
                filters={"target_doctype": "Branch Expense Request", "target_name": self.name},
                pluck="name",
            )
            for record in monitoring_records:
                frappe.delete_doc("Tax Invoice OCR Monitoring", record, ignore_permissions=True, force=True)

    def before_workflow_action(self, action, **kwargs):
        """Gate workflow transitions by the resolved approver route."""
        self._ensure_status()

        if action == "Submit":
            return

        if not self.is_pending_review():
            return

        # Get current level - defaults to 1 for first approval
        current_level = self.get_current_level_key()

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
        if expected_user:
            requirements.append(_("user '{0}'").format(expected_user))
        if expected_role:
            requirements.append(_("role '{0}'").format(expected_role))

        frappe.throw(
            _("You must be {requirements} to perform this action for approval level {level}.").format(
                requirements=_(" and ").join(requirements), level=current_level
            ),
            title=_("Not Allowed"),
        )

    def validate_amounts(self):
        total, expense_accounts = FinanceValidator.validate_amounts(self.get("items"))
        self.total_amount = total
        self.amount = total
        self.expense_accounts = expense_accounts
        self.expense_account = expense_accounts[0] if len(expense_accounts) == 1 else None

    def apply_branch_defaults(self):
        branch = resolve_branch(
            company=self._get_company(),
            cost_center=self._get_primary_cost_center(),
            explicit_branch=getattr(self, "branch", None),
        )
        if branch:
            apply_branch(self, branch)

    def validate_tax_fields(self):
        FinanceValidator.validate_tax_fields(self)

    def validate_tax_invoice_ocr_before_submit(self):
        """Validate tax invoice OCR data before submit: NPWP, DPP, PPN, PPnBM."""
        # Skip if OCR not enabled or no OCR upload
        try:
            from imogi_finance.tax_invoice_ocr import get_settings, normalize_npwp
        except ImportError:
            return

        settings = get_settings()
        if not settings.get("enable_tax_invoice_ocr"):
            return

        # Skip if not using OCR upload
        if not getattr(self, "ti_tax_invoice_upload", None):
            return

        # Skip if PPN not applicable
        if not getattr(self, "is_ppn_applicable", 0):
            return

        errors = []
        warnings = []

        # Note: Branch Expense Request does not have supplier field,
        # so NPWP validation against supplier is not applicable
        
        # 1. Validate DPP, PPN, PPnBM with tolerance
        # Get tolerance from settings (both fixed IDR and percentage)
        tolerance = flt(settings.get("tolerance_idr", 10000))  # Default Rp 10,000
        tolerance_pct = flt(settings.get("tolerance_percentage", 1.0))  # Default 1%
        
        # Get PPN type - only validate amounts for Standard PPN
        ppn_type = getattr(self, "ti_fp_ppn_type", None)
        if ppn_type and ppn_type != "Standard":
            # Skip DPP/PPN validation for Zero Rated or Exempt
            # Only NPWP validation applies
            if errors:
                frappe.throw(
                    "<br>".join(["<strong>Validasi Faktur Pajak Gagal:</strong>"] + errors),
                    title=_("Tax Invoice Validation Error")
                )
            return
        
        # Get OCR values
        ocr_dpp = flt(getattr(self, "ti_fp_dpp", 0) or 0)
        ocr_ppn = flt(getattr(self, "ti_fp_ppn", 0) or 0)
        ocr_ppnbm = flt(getattr(self, "ti_fp_ppnbm", 0) or 0)
        
        # Calculate expected values from expense request
        expected_dpp = flt(getattr(self, "amount", 0) or 0)  # Total expense as DPP
        
        # Expected PPN calculation
        ppn_template = getattr(self, "ppn_template", None)
        ppn_rate = 11  # Default PPN rate
        if ppn_template:
            # Get rate from template
            template = frappe.get_doc("Purchase Taxes and Charges Template", ppn_template)
            for tax in template.get("taxes", []):
                if tax.rate:
                    ppn_rate = flt(tax.rate)
                    break
        
        expected_ppn = expected_dpp * ppn_rate / 100
        
        # Check DPP difference
        # Use both fixed IDR tolerance and percentage tolerance (whichever is more lenient)
        if ocr_dpp > 0 and expected_dpp > 0:
            # Calculate variance (OCR - Expected) - can be negative or positive
            dpp_variance = ocr_dpp - expected_dpp
            dpp_diff = abs(dpp_variance)
            dpp_diff_pct = (dpp_diff / expected_dpp * 100) if expected_dpp > 0 else 0
            
            # Save variance for tax operations (will be used for PPN payable calculation)
            self.ti_dpp_variance = dpp_variance
            
            # Validate using tolerance from settings
            if dpp_diff > tolerance and dpp_diff_pct > tolerance_pct:
                errors.append(
                    _("DPP dari OCR ({0}) berbeda dengan Total Expense ({1}). Selisih: {2} atau {3:.2f}% (toleransi: {4} atau {5}%)").format(
                        frappe.format_value(ocr_dpp, {"fieldtype": "Currency"}),
                        frappe.format_value(expected_dpp, {"fieldtype": "Currency"}),
                        frappe.format_value(dpp_variance, {"fieldtype": "Currency"}),
                        dpp_diff_pct,
                        frappe.format_value(tolerance, {"fieldtype": "Currency"}),
                        tolerance_pct
                    )
                )
            elif dpp_diff > tolerance or dpp_diff_pct > tolerance_pct:
                # Warning zone: exceeds one tolerance but not both
                warnings.append(
                    _("⚠️ DPP dari OCR berbeda {0} atau {1:.2f}% (masih dalam toleransi)").format(
                        frappe.format_value(dpp_variance, {"fieldtype": "Currency"}),
                        dpp_diff_pct
                    )
                )
        
        # Check PPN difference
        if ocr_ppn > 0:
            ppn_diff = abs(ocr_ppn - expected_ppn)
            ppn_diff_pct = (ppn_diff / expected_ppn * 100) if expected_ppn > 0 else 0
            
            # Allow up to 1% difference OR fixed tolerance (whichever is more lenient)
            max_pct_tolerance = 1.0  # 1%
            
            if ppn_diff > tolerance and ppn_diff_pct > max_pct_tolerance:
                errors.append(
                    _("PPN dari OCR ({0}) berbeda dengan PPN yang dihitung ({1}). Selisih: {2} atau {3:.2f}% (toleransi: {4} atau {5}%)").format(
                        frappe.format_value(ocr_ppn, {"fieldtype": "Currency"}),
                        frappe.format_value(expected_ppn, {"fieldtype": "Currency"}),
                        frappe.format_value(ppn_diff, {"fieldtype": "Currency"}),
                        ppn_diff_pct,
                        frappe.format_value(tolerance, {"fieldtype": "Currency"}),
                        max_pct_tolerance
                    )
                )
            elif ppn_diff > tolerance or ppn_diff_pct > max_pct_tolerance:
                # Warning zone: exceeds one tolerance but not both
                warnings.append(
                    _("⚠️ PPN dari OCR berbeda {0} atau {1:.2f}% (masih dalam toleransi)").format(
                        frappe.format_value(ppn_diff, {"fieldtype": "Currency"}),
                        ppn_diff_pct
                    )
                )
        
        # PPnBM validation (if applicable) - usually PPnBM should be 0 or match expected
        # For now, just note if PPnBM exists but we can add validation later if needed
        
        # Show warnings as msgprint (non-blocking)
        if warnings:
            frappe.msgprint(
                "<br>".join(["<strong>Peringatan Validasi Faktur Pajak:</strong>"] + warnings),
                title=_("Tax Invoice Validation Warning"),
                indicator="orange"
            )
        
        # Show errors and block submission
        if errors:
            frappe.throw(
                "<br>".join(["<strong>Validasi Faktur Pajak Gagal:</strong>"] + errors),
                title=_("Tax Invoice Validation Error")
            )

    def _validate_deferred_expense(self):
        settings, deferrable_accounts = get_deferrable_account_map()
        if not getattr(settings, "enable_deferred_expense", 1):
            if any(getattr(item, "is_deferred_expense", 0) for item in self.get("items", [])):
                frappe.throw(_("Deferred Expense is disabled in settings."))
            return

        valid_prepaid_accounts = sorted(deferrable_accounts)
        for item in self.get("items", []):
            if not getattr(item, "is_deferred_expense", 0):
                continue

            if not getattr(item, "prepaid_account", None):
                frappe.throw(_("Prepaid Account is required for deferred expense items."))

            if item.prepaid_account not in deferrable_accounts:
                frappe.throw(
                    _("Prepaid Account {0} is not in deferrable accounts. Valid accounts: {1}").format(
                        item.prepaid_account, ", ".join(valid_prepaid_accounts) or _("None")
                    )
                )

            if not getattr(item, "deferred_start_date", None):
                frappe.throw(_("Deferred Start Date is required for deferred expense items."))

            periods = getattr(item, "deferred_periods", None)
            if not periods or periods <= 0:
                frappe.throw(_("Deferred Periods must be greater than zero for deferred expense items."))

            schedule = generate_amortization_schedule(
                getattr(item, "amount", 0) or 0, periods, item.deferred_start_date
            )
            flags = getattr(item, "flags", None)
            if flags is None:
                flags = type("Flags", (), {})()
                item.flags = flags
            item.flags.deferred_amortization_schedule = schedule

    def _sync_tax_invoice_upload(self):
        if not getattr(self, "ti_tax_invoice_upload", None):
            return

        sync_tax_invoice_upload(self, "Branch Expense Request", save=False)

    def _ensure_enabled(self, settings):
        if getattr(settings, "enable_branch_expense_request", 1):
            return
        frappe.throw(_("Branch Expense Request is disabled in settings."))

    def _ensure_status(self):
        if getattr(self, "status", None):
            return

        workflow_state = getattr(self, "workflow_state", None)
        if workflow_state:
            self.status = workflow_state
            return

        self.status = self.STATUS_DRAFT

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

    def _reset_status_if_copied(self):
        """Ensure duplicated documents start from Draft instead of Rejected/Approved.

        When a submitted request (e.g. Rejected) is duplicated, Frappe copies the
        status and workflow_state fields. For the new draft, we want a clean start
        so users can submit it again without being stuck in a terminal state.
        """
        if getattr(self, "docstatus", 0) == 0 and getattr(self, "status", None) in {self.STATUS_REJECTED, self.STATUS_APPROVED}:
            self.status = self.STATUS_DRAFT
            self.workflow_state = None
            self.current_approval_level = 0
            # Clear route snapshot on copied drafts
            self.approval_route_snapshot = None
            self.level_1_user = None
            self.level_2_user = None
            self.level_3_user = None

    def _get_company(self):
        if getattr(self, "company", None):
            return self.company

        cost_center = self._get_primary_cost_center()
        if cost_center:
            return frappe.db.get_value("Cost Center", cost_center, "company")
        return None

    def _get_primary_cost_center(self):
        for item in self.get("items") or []:
            cost_center = getattr(item, "cost_center", None)
            if cost_center:
                return cost_center
        return None

    def _set_fiscal_year(self):
        if getattr(self, "fiscal_year", None) or not getattr(self, "posting_date", None):
            return

        fiscal = resolve_fiscal_year(self.posting_date, self._get_company())
        if not fiscal:
            return

        self.fiscal_year = fiscal.get("name") or fiscal.get("fiscal_year")

    def _validate_employee_requirement(self, settings):
        EmployeeValidator.require_employee(self, enabled=getattr(settings, "require_employee", 0))

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
            if not getattr(item, "expense_account", None):
                frappe.throw(_("Expense Account is required for each item."))
            item.is_pph_applicable = 1 if getattr(item, "is_pph_applicable", 0) else 0
            item.amount = flt(item.qty) * flt(item.rate)

    def _update_totals(self):
        items: Iterable[object] = self.get("items") or []
        self.total_amount = sum(flt(getattr(item, "amount", 0)) for item in items)
        self.amount = self.total_amount
        if getattr(self, "expense_accounts", None):
            self.expense_account = (
                self.expense_accounts[0] if len(self.expense_accounts) == 1 else None
            )

    def _get_budget_window(self, settings) -> tuple[date | None, date | None]:
        basis = (getattr(settings, "budget_check_basis", None) or "Fiscal Year").lower()
        if basis.startswith("fiscal period") and getattr(self, "posting_date", None):
            return get_first_day(self.posting_date), get_last_day(self.posting_date)
        return None, None

    def _reset_budget_flags(self, status: str = "Not Checked"):
        self.budget_check_status = status
        self.budget_check_message = None
        for item in self.get("items") or []:
            item.budget_result = None
            item.budget_available = None
            item.budget_consumed = None
            item.budget_message = None

    def _check_item_budget(self, item, settings) -> str:
        account = getattr(item, "expense_account", None) or getattr(settings, "default_expense_account", None)
        amount = flt(getattr(item, "amount", 0))
        dims = service.resolve_dims(
            company=getattr(self, "company", None),
            fiscal_year=getattr(self, "fiscal_year", None),
            cost_center=getattr(item, "cost_center", None),
            account=account,
            project=getattr(item, "project", None),
            branch=getattr(self, "branch", None),
        )
        from_date, to_date = self._get_budget_window(settings)

        result = service.check_budget_available(dims, amount, from_date=from_date, to_date=to_date)
        snapshot = result.snapshot or {}
        message = result.message or snapshot.get("message")
        available = result.available if result.available is not None else snapshot.get("available")
        if available is None:
            availability = ledger.get_availability(dims, from_date=from_date, to_date=to_date)
            snapshot.update(availability)
            available = availability.get("available")

        allocated = snapshot.get("allocated")
        consumed = None
        if allocated is not None and available is not None:
            consumed = flt(allocated) - flt(available)

        ok = bool(result.ok) if available is None else available >= amount
        status = "OK" if ok else ("Warning" if getattr(settings, "budget_warn_on_over", 0) else "Over Budget")

        if not message and available is not None:
            message = _("Available budget is {0}, requested {1}.").format(available, amount)

        item.budget_result = status
        item.budget_available = available
        item.budget_consumed = consumed
        item.budget_message = message

        return status

    def _run_budget_checks(self, settings, *, for_submit: bool = False):
        self._reset_budget_flags()
        if not getattr(settings, "enable_budget_check", 0):
            return

        if not getattr(self, "fiscal_year", None):
            frappe.throw(_("Fiscal Year is required for budget checking."))

        summary_status = "OK"
        messages = set()
        for item in self.get("items") or []:
            status = self._check_item_budget(item, settings)
            if status == "Over Budget":
                summary_status = "Over Budget"
            elif status == "Warning" and summary_status != "Over Budget":
                summary_status = "Warning"
            if getattr(item, "budget_message", None):
                messages.add(item.budget_message)

        self.budget_check_status = summary_status
        if messages:
            self.budget_check_message = "\n".join(sorted(messages))

        over_budget = summary_status == "Over Budget"
        block_overrun = getattr(settings, "budget_block_on_over", 0) and not getattr(settings, "budget_warn_on_over", 0)
        if for_submit and over_budget and block_overrun:
            frappe.throw(_("Budget check failed. Please resolve over budget items before submission."))

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

    # ========== Approval Routing Methods ==========

    def _prepare_route_for_workflow(self):
        """Resolve route during validate for display purposes."""
        if getattr(self, "docstatus", 0) != 0:
            return

        if not getattr(self, "branch", None):
            return

        try:
            route, setting_meta, skip = self._resolve_approval_route()
            self._apply_route_to_fields(route, setting_meta)
        except Exception:
            pass

    def _resolve_approval_route(self) -> tuple[dict, dict | None, bool]:
        """Resolve approval route. Returns empty route for auto-approve if not configured."""
        try:
            setting_meta = get_active_setting_meta_for_branch(self.branch)
            route_result = get_branch_approval_route(
                self.branch, self._get_expense_accounts(), self.amount, setting_meta=setting_meta
            )
            route = route_result if isinstance(route_result, dict) else {}
        except (frappe.DoesNotExistError, frappe.ValidationError) as exc:
            log_branch_route_resolution_error(
                exc,
                branch=self.branch,
                accounts=self._get_expense_accounts(),
                amount=self.amount,
            )
            route = {}
            setting_meta = None

        has_approvers = any([
            route.get("level_1", {}).get("user"),
            route.get("level_2", {}).get("user"),
            route.get("level_3", {}).get("user"),
        ])

        skip = not has_approvers
        return route, setting_meta, skip

    def _resolve_and_apply_route(self) -> dict:
        """Resolve and apply approval route during submit."""
        route, setting_meta, skip = self._resolve_approval_route()
        self._skip_approval_route = skip
        self._apply_route_to_fields(route, setting_meta)
        return route

    def _apply_route_to_fields(self, route: dict, setting_meta: dict | None = None):
        """Apply resolved route to document fields."""
        if setting_meta:
            self.approval_setting = setting_meta.get("name")

        for level in (1, 2, 3):
            level_data = route.get(f"level_{level}", {})
            user = level_data.get("user")
            role = level_data.get("role")

            setattr(self, f"level_{level}_user", user or None)
            setattr(self, f"level_{level}_role", role or None)

    def _ensure_route_ready(self, route: dict):
        """Validate route is ready for submission."""
        if self._skip_approval_route:
            return

        if not route:
            frappe.throw(
                branch_approval_setting_required_message(self.branch),
                title=_("Approval Route Not Found"),
            )

    def _set_pending_review(self, *, level: int = 1):
        """Set document to pending review status."""
        self.status = self.PENDING_REVIEW_STATE
        self.workflow_state = self.PENDING_REVIEW_STATE
        self.current_approval_level = level

    def _get_initial_approval_level(self, route: dict | None = None) -> int:
        """Get initial approval level."""
        route = route or self.get_route_snapshot()
        for level in (1, 2, 3):
            target = route.get(f"level_{level}", {}) if isinstance(route, dict) else {}
            if target.get("user"):
                return level
        return 1

    def is_pending_review(self) -> bool:
        """Check if document is in pending review state."""
        return (
            getattr(self, "status", None) == self.PENDING_REVIEW_STATE
            or getattr(self, "workflow_state", None) == self.PENDING_REVIEW_STATE
        )

    def _level_configured(self, level: int) -> bool:
        """Check if approval level is configured."""
        if level not in {1, 2, 3}:
            return False
        user = self.get(f"level_{level}_user")
        return bool(user)

    def has_next_approval_level(self) -> bool:
        """Check if there is a next approval level."""
        current = getattr(self, "current_approval_level", 0) or 0
        if current >= 3:
            return False
        return self._level_configured(current + 1)

    def _advance_approval_level(self):
        """Advance to next approval level."""
        current = getattr(self, "current_approval_level", 0) or 0
        if current >= 3:
            return
        self.current_approval_level = current + 1

    def get_current_level_key(self) -> int:
        """Get current approval level key. Defaults to 1 if not set."""
        level = getattr(self, "current_approval_level", None)
        if level and 1 <= level <= 3:
            return level
        # Default to level 1 for pending review documents without explicit level
        return 1

    def validate_not_skipping_levels(self, action: str, next_state: str | None):
        """Validate that approval is not skipping levels."""
        if action != "Approve":
            return

        current = getattr(self, "current_approval_level", 0) or 0
        if current == 0:
            return

        # Check if we're at the right level
        if next_state == "Approved":
            # Final approval - check no more levels configured
            for level in range(current + 1, 4):
                if self._level_configured(level):
                    frappe.throw(
                        _("Cannot skip approval level {0}. Please complete all configured approval levels.").format(
                            level
                        )
                    )

    def validate_initial_approver(self, route: dict):
        """Ensure the approval route has at least one configured user."""
        has_user = any([
            route.get("level_1", {}).get("user"),
            route.get("level_2", {}).get("user"),
            route.get("level_3", {}).get("user"),
        ])

        if not has_user:
            frappe.throw(
                _("Approval route must have at least one configured approver."),
                title=_("Invalid Approval Route"),
            )

    def validate_route_users_exist(self, route: dict | None = None):
        """Validate approval route users still exist and are enabled."""
        from imogi_finance.branch_approval import validate_route_users

        route = route or self.get_route_snapshot()
        if not route:
            return

        validation = validate_route_users(route)
        if validation.get("valid"):
            return

        error_parts: list[str] = []

        invalid_users = validation.get("invalid_users") or []
        if invalid_users:
            self._log_invalid_route_users(invalid_users, validation.get("disabled_users") or [])
            user_list = ", ".join(
                _("Level {level}: {user}").format(level=u.get("level"), user=u.get("user"))
                for u in invalid_users
            )
            error_parts.append(_("Users not found: {0}").format(user_list))

        disabled_users = validation.get("disabled_users") or []
        if disabled_users:
            user_list = ", ".join(
                _("Level {level}: {user}").format(level=u.get("level"), user=u.get("user"))
                for u in disabled_users
            )
            error_parts.append(_("Users disabled: {0}").format(user_list))

        if error_parts:
            frappe.throw(
                _("; ").join(error_parts) + ". " + _("Please update the Branch Expense Approval Setting."),
                title=_("Invalid Approvers"),
            )

    def _log_invalid_route_users(self, invalid_users: list[dict], disabled_users: list[dict]):
        """Log invalid route users for audit purposes."""
        try:
            frappe.log_error(
                title=_("Branch Expense Request: Invalid Approval Route Users"),
                message={
                    "document": self.name,
                    "branch": self.branch,
                    "invalid_users": invalid_users,
                    "disabled_users": disabled_users,
                },
            )
        except Exception:
            pass

    def record_approval_route_snapshot(self):
        """Save approval route snapshot."""
        snapshot = {
            "level_1": {"user": self.level_1_user, "role": self.level_1_role},
            "level_2": {"user": self.level_2_user, "role": self.level_2_role},
            "level_3": {"user": self.level_3_user, "role": self.level_3_role},
        }
        self.approval_route_snapshot = json.dumps(snapshot)

    def get_route_snapshot(self) -> dict | None:
        """Get approval route snapshot."""
        from imogi_finance.branch_approval import parse_route_snapshot
        
        snapshot = getattr(self, "approval_route_snapshot", None)
        if not snapshot:
            return None
        
        parsed = parse_route_snapshot(snapshot)
        return parsed if parsed else None

    def _get_expense_accounts(self) -> tuple[str, ...]:
        """Get expense accounts from items."""
        accounts = set()
        for item in self.get("items") or []:
            account = getattr(item, "expense_account", None)
            if account:
                accounts.add(account)
        return tuple(sorted(accounts))

def apply_default_amounts(item):
    item.qty = flt(getattr(item, "qty", 0)) or 0
    item.rate = flt(getattr(item, "rate", 0)) or 0
    item.amount = flt(item.qty) * flt(item.rate)
