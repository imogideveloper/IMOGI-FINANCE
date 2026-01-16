"""Refactored Expense Request - minimal logic, leveraging ApprovalService and native hooks."""
from __future__ import annotations

import json
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from imogi_finance import accounting, roles
from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.approval import get_active_setting_meta, approval_setting_required_message
from imogi_finance.budget_control.workflow import handle_expense_request_workflow, release_budget_for_request
from imogi_finance.services.approval_route_service import ApprovalRouteService
from imogi_finance.services.approval_service import ApprovalService
from imogi_finance.services.deferred_expense import generate_amortization_schedule
from ..expense_deferred_settings.expense_deferred_settings import get_deferrable_account_map
from imogi_finance.tax_invoice_ocr import sync_tax_invoice_upload, validate_tax_invoice_upload_link
from imogi_finance.tax_invoice_fields import get_upload_link_field
from imogi_finance.validators.finance_validator import FinanceValidator


def _resolve_pph_rate(pph_type: str | None) -> float:
    if not pph_type:
        return 0

    get_doc = getattr(frappe, "get_doc", None)
    if not callable(get_doc):
        return 0

    try:
        category = get_doc("Tax Withholding Category", pph_type)
    except Exception:
        return 0

    for field in ("tax_withholding_rate", "rate", "withholding_rate"):
        value = getattr(category, field, None)
        if value:
            return flt(value)

    withholding_rows = None
    for field in ("withholding_tax", "tax_withholding_rates", "rates", "tax_withholding_rate"):
        rows = getattr(category, field, None)
        if rows:
            withholding_rows = rows
            break
    if withholding_rows is None:
        withholding_rows = []
    today = now_datetime().date()
    fallback_rate = 0.0

    for row in withholding_rows:
        row_rate = None
        for field in ("tax_withholding_rate", "rate", "withholding_rate", "tax_rate"):
            value = getattr(row, field, None)
            if value:
                row_rate = flt(value)
                break

        if row_rate:
            from_date = getattr(row, "from_date", None)
            to_date = getattr(row, "to_date", None)
            if (from_date or to_date) and (
                (not from_date or from_date <= today) and (not to_date or to_date >= today)
            ):
                return row_rate
            if not fallback_rate:
                fallback_rate = row_rate
                continue

        withholding_name = getattr(row, "withholding_tax", None)
        if withholding_name:
            rate = getattr(frappe.db, "get_value", lambda *_args, **_kwargs: None)(
                "Withholding Tax",
                withholding_name,
                "rate",
            )
            if rate:
                return flt(rate)

    if fallback_rate:
        return fallback_rate

    return 0


@frappe.whitelist()
def get_pph_rate(pph_type: str | None = None) -> dict:
    return {"rate": _resolve_pph_rate(pph_type)}


def get_approval_route(cost_center: str, accounts, amount: float, *, setting_meta=None):
    """Wrapper for ApprovalRouteService.get_route."""
    return ApprovalRouteService.get_route(cost_center, accounts, amount, setting_meta=setting_meta)


class ExpenseRequest(Document):
    """Expense Request - minimal logic, validation only.
    
    Approval workflow, budget control, and accounting are delegated to:
    - ApprovalService: Multi-level approval state machine
    - budget_control.workflow: Budget locking/reservation
    - accounting: Purchase Invoice creation
    - hooks (on_submit, etc): Standard Frappe patterns
    """

    def before_validate(self):
        self.validate_amounts()

    def before_insert(self):
        self._set_requester_to_creator()
        self._reset_status_if_copied()

    def after_insert(self):
        # Best practice: always let user explicitly submit.
        # Auto-approval (tanpa approver) akan dijalankan lewat workflow/ApprovalService,
        # bukan dengan submit otomatis saat insert.
        pass

    def validate(self):
        """All business rule validation."""
        self._set_requester_to_creator()
        self._initialize_status()
        self.validate_amounts()
        self.apply_branch_defaults()
        self._sync_tax_invoice_upload()
        self.validate_tax_fields()
        self.validate_deferred_expense()
        validate_tax_invoice_upload_link(self, "Expense Request")
        self._ensure_final_state_immutability()

    def before_submit(self):
        """Prepare for submission - resolve approval route and initialize state."""
        self.validate_submit_permission()
        
        # Validate tax invoice OCR data if OCR is enabled and applicable
        self.validate_tax_invoice_ocr_before_submit()

        # Resolve approval route for this request
        route, setting_meta, failed = self._resolve_approval_route()
        self._ensure_route_ready(route, failed)
        self.apply_route(route, setting_meta=setting_meta)
        self.record_approval_route_snapshot(route)
        self.validate_route_users_exist(route)
        # Use ApprovalService to set initial approval state
        approval_service = ApprovalService("Expense Request", state_field="workflow_state")
        approval_service.before_submit(self, route=route, skip_approval=not self._has_approver(route))

    def on_submit(self):
        """Post-submit: sync budget (if enabled) and record in activity."""
        # Budget control: lock/reserve budget if configured
        # If budget control is enabled and fails, the entire submit MUST fail
        try:
            handle_expense_request_workflow(self, "Submit", getattr(self, "workflow_state"))
        except frappe.ValidationError:
            # Re-raise validation errors (e.g., budget exceeded)
            raise
        except Exception as e:
            # Log unexpected errors and fail the transaction
            frappe.log_error(
                title=f"Budget Control Critical Error for {self.name}",
                message=f"Failed to handle budget workflow on submit: {str(e)}\n\n{frappe.get_traceback()}"
            )
            frappe.throw(
                _("Budget control operation failed. Transaction cannot be completed. Error: {0}").format(str(e)),
                title=_("Budget Control Error")
            )

    def before_workflow_action(self, action, **kwargs):
        """Gate workflow actions using ApprovalService + route validation."""
        approval_service = ApprovalService("Expense Request", state_field="workflow_state")
        route = self._get_route_snapshot()
        approval_service.before_workflow_action(self, action, next_state=kwargs.get("next_state"), route=route)

    def on_workflow_action(self, action, **kwargs):
        """Handle state transitions via ApprovalService."""
        approval_service = ApprovalService("Expense Request", state_field="workflow_state")
        next_state = kwargs.get("next_state")
        approval_service.on_workflow_action(self, action, next_state=next_state)

        # Post-action: sync related systems
        if action in ("Approve", "Reject", "Reopen"):
            try:
                # Pass next_state from kwargs, not the already-changed workflow_state
                handle_expense_request_workflow(self, action, next_state)
            except frappe.ValidationError:
                # Re-raise validation errors
                raise
            except Exception as e:
                # Log unexpected errors and fail the workflow action
                frappe.log_error(
                    title=f"Budget Control Critical Error for {self.name}",
                    message=f"Failed to handle budget workflow on {action}: {str(e)}\n\n{frappe.get_traceback()}"
                )
                frappe.throw(
                    _("Budget control operation failed. Workflow action cannot be completed. Error: {0}").format(str(e)),
                    title=_("Budget Control Error")
                )

    def on_update_after_submit(self):
        """Post-save: guard status changes to prevent bypass."""
        approval_service = ApprovalService("Expense Request", state_field="workflow_state")
        approval_service.guard_status_changes(self)

    def before_cancel(self):
        """Validate permissions and downstream links before cancel."""
        allowed_roles = {roles.SYSTEM_MANAGER, roles.EXPENSE_APPROVER}
        current_roles = set(frappe.get_roles())
        if not (current_roles & allowed_roles):
            frappe.throw(_("Only System Manager or Expense Approver can cancel."), title=_("Not Allowed"))

        # Check for active downstream links
        active_links = []
        
        # Check Payment Entry
        pe = getattr(self, "linked_payment_entry", None)
        if pe and frappe.db.get_value("Payment Entry", pe, "docstatus") != 2:
            active_links.append(f"Payment Entry {pe}")
        
        # Check Purchase Invoice
        pi = getattr(self, "linked_purchase_invoice", None)
        if pi and frappe.db.get_value("Purchase Invoice", pi, "docstatus") != 2:
            active_links.append(f"Purchase Invoice {pi}")
        
        if active_links:
            frappe.throw(
                _("Cannot cancel while linked to: {0}. Cancel them first.").format(", ".join(active_links)),
                title=_("Active Links Exist"),
            )

    def on_cancel(self):
        """Clean up: release budget reservations."""
        # Check for active downstream links - MUST be cancelled first
        active_links = []
        
        pe = getattr(self, "linked_payment_entry", None)
        if pe and frappe.db.get_value("Payment Entry", pe, "docstatus") == 1:
            active_links.append(f"Payment Entry {pe}")
        
        pi = getattr(self, "linked_purchase_invoice", None)
        if pi and frappe.db.get_value("Purchase Invoice", pi, "docstatus") == 1:
            active_links.append(f"Purchase Invoice {pi}")
        
        if active_links:
            frappe.throw(
                _("Cannot cancel Expense Request. Please cancel these documents first: {0}").format(", ".join(active_links)),
                title=_("Active Links Exist")
            )
        
        # Release budget reservations - MUST succeed or cancel fails
        try:
            release_budget_for_request(self, reason="Cancel")
        except Exception as e:
            frappe.log_error(
                title=f"Budget Release Error for {self.name}",
                message=f"Error releasing budget: {str(e)}\n\n{frappe.get_traceback()}"
            )
            frappe.throw(
                _("Failed to release budget. Cancel operation cannot proceed. Error: {0}").format(str(e)),
                title=_("Budget Release Error")
            )

    def on_trash(self):
        """Clean up OCR links and monitoring records before deletion.

        Automatically clears references to Tax Invoice OCR Upload and
        deletes any Tax Invoice OCR Monitoring records to avoid circular
        dependency issues when deleting Expense Request.
        """

        # Clear Tax Invoice OCR Upload link to break circular dependency
        upload_field = get_upload_link_field("Expense Request")
        if upload_field and getattr(self, upload_field, None):
            # Clear the link field - use db_set since document is being deleted
            frappe.db.set_value("Expense Request", self.name, upload_field, None)

        # Delete any OCR Monitoring records pointing to this Expense Request
        if frappe.db.table_exists("Tax Invoice OCR Monitoring"):
            monitoring_records = frappe.get_all(
                "Tax Invoice OCR Monitoring",
                filters={"target_doctype": "Expense Request", "target_name": self.name},
                pluck="name",
            )
            for record in monitoring_records:
                frappe.delete_doc("Tax Invoice OCR Monitoring", record, ignore_permissions=True, force=True)

    # ===================== Business Logic =====================

    def validate_amounts(self):
        """Sum item amounts and set total."""
        total, expense_accounts = FinanceValidator.validate_amounts(self.get("items"))
        self.amount = total
        self.expense_accounts = expense_accounts
        self.expense_account = expense_accounts[0] if len(expense_accounts) == 1 else None
        self._set_totals()

    def _set_totals(self):
        """Calculate and set all total fields."""
        items = self.get("items") or []
        total_expense = flt(getattr(self, "amount", 0) or 0)
        total_ppn = flt(getattr(self, "ti_fp_ppn", None) or getattr(self, "ppn", None) or 0)
        total_ppnbm = flt(getattr(self, "ti_fp_ppnbm", None) or getattr(self, "ppnbm", None) or 0)
        item_pph_total = sum(
            flt(getattr(item, "pph_base_amount", 0) or 0)
            for item in items
            if getattr(item, "is_pph_applicable", 0)
        )
        pph_base_total = item_pph_total or (
            flt(getattr(self, "pph_base_amount", 0) or 0) if getattr(self, "is_pph_applicable", 0) else 0
        )
        pph_rate = _resolve_pph_rate(getattr(self, "pph_type", None))
        total_pph = (pph_base_total * pph_rate / 100) if pph_rate else pph_base_total
        # Ensure total_pph is always stored as positive (absolute value)
        # for consistency, since we subtract it in the formula.
        total_pph = abs(total_pph)
        # PPh is withholding tax, so it reduces the total payable amount.
        total_amount = total_expense + total_ppn + total_ppnbm - total_pph

        # Keep header PPh base amount in sync with the effective base used for calculations.
        if getattr(self, "is_pph_applicable", 0) or item_pph_total:
            self.pph_base_amount = pph_base_total
        else:
            self.pph_base_amount = 0

        self.total_expense = total_expense
        self.total_ppn = total_ppn
        self.total_ppnbm = total_ppnbm
        self.total_pph = total_pph
        self.total_amount = total_amount

    def apply_branch_defaults(self):
        """Auto-set branch fields based on cost center."""
        try:
            branch = resolve_branch(
                company=self._get_company(),
                cost_center=getattr(self, "cost_center", None),
                explicit_branch=getattr(self, "branch", None),
            )
            if branch:
                apply_branch(self, branch)
        except Exception:
            pass

    def validate_tax_fields(self):
        """Validate tax configuration and basic PPN sanity with OCR values."""
        FinanceValidator.validate_tax_fields(self)

        # Extra guardrail: jika ada nilai PPN dari OCR dan manual sekaligus,
        # pastikan keduanya tidak berbeda terlalu jauh (di luar tolerance_idr).
        try:
            from imogi_finance.tax_invoice_ocr import get_settings

            settings = get_settings()
            tolerance = flt(settings.get("tolerance_idr", 10))
            ti_ppn = flt(getattr(self, "ti_fp_ppn", 0) or 0)
            manual_ppn = flt(getattr(self, "ppn", 0) or 0)
            if ti_ppn and manual_ppn:
                diff = abs(ti_ppn - manual_ppn)
                if diff > tolerance:
                    frappe.throw(
                        _(
                            "PPN on Expense Request ({0}) differs from OCR Faktur Pajak ({1}) by more than {2}."
                        ).format(manual_ppn, ti_ppn, tolerance)
                    )
        except Exception:
            # Jangan blokir jika settings tidak bisa di-load; pengecekan utama tetap di modul OCR.
            pass

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

        # 1. Validate NPWP matches supplier
        supplier = getattr(self, "supplier", None)
        if supplier:
            supplier_npwp = frappe.db.get_value("Supplier", supplier, "tax_id")
            if supplier_npwp:
                supplier_npwp = normalize_npwp(supplier_npwp)
                ocr_npwp = normalize_npwp(getattr(self, "ti_fp_npwp", None))
                
                if ocr_npwp and supplier_npwp and ocr_npwp != supplier_npwp:
                    errors.append(
                        _("NPWP dari OCR ({0}) tidak sesuai dengan NPWP Supplier ({1})").format(
                            getattr(self, "ti_fp_npwp", ""), supplier_npwp
                        )
                    )

        # 2. Validate DPP, PPN, PPnBM with tolerance
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
            # Calculate variance (OCR - Expected) - can be negative or positive
            ppn_variance = ocr_ppn - expected_ppn
            ppn_diff = abs(ppn_variance)
            ppn_diff_pct = (ppn_diff / expected_ppn * 100) if expected_ppn > 0 else 0
            
            # Save variance for tax operations (will be used for PPN payable calculation)
            self.ti_ppn_variance = ppn_variance
            
            # Validate using tolerance from settings
            if ppn_diff > tolerance and ppn_diff_pct > tolerance_pct:
                errors.append(
                    _("PPN dari OCR ({0}) berbeda dengan PPN yang dihitung ({1}). Selisih: {2} atau {3:.2f}% (toleransi: {4} atau {5}%)").format(
                        frappe.format_value(ocr_ppn, {"fieldtype": "Currency"}),
                        frappe.format_value(expected_ppn, {"fieldtype": "Currency"}),
                        frappe.format_value(ppn_variance, {"fieldtype": "Currency"}),
                        ppn_diff_pct,
                        frappe.format_value(tolerance, {"fieldtype": "Currency"}),
                        tolerance_pct
                    )
                )
            elif ppn_diff > tolerance or ppn_diff_pct > tolerance_pct:
                # Warning zone: exceeds one tolerance but not both
                warnings.append(
                    _("⚠️ PPN dari OCR berbeda {0} atau {1:.2f}% (masih dalam toleransi)").format(
                        frappe.format_value(ppn_variance, {"fieldtype": "Currency"}),
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

    def validate_deferred_expense(self):
        """Validate deferred expense configuration."""
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
                frappe.throw(_("Deferred Start Date required for deferred expense items."))

            periods = getattr(item, "deferred_periods", None)
            if not periods or periods <= 0:
                frappe.throw(_("Deferred Periods must be > 0 for deferred expense items."))

            schedule = generate_amortization_schedule(
                flt(item.amount), periods, item.deferred_start_date
            )
            if not hasattr(item, "flags"):
                item.flags = type("Flags", (), {})()
            item.flags.deferred_amortization_schedule = schedule

    def _sync_tax_invoice_upload(self):
        """Sync tax invoice OCR data if configured."""
        if getattr(self, "ti_tax_invoice_upload", None):
            sync_tax_invoice_upload(self, "Expense Request", save=False)

    def _ensure_final_state_immutability(self):
        """Prevent key field edits after approval."""
        if getattr(self, "docstatus", 0) != 1:
            return

        if self.status not in ("Approved", "PI Created", "Paid"):
            return

        previous = self._get_previous_doc()
        if not previous:
            return

        key_fields = ("request_type", "supplier", "amount", "cost_center", "branch", "project")
        changed = [f for f in key_fields if self._get_value(previous, f) != getattr(self, f, None)]
        
        if changed:
            frappe.throw(_("Cannot modify after approval: {0}").format(", ".join(changed)))

    # ===================== Approval Helpers =====================

    def _initialize_status(self):
        """Set initial status from workflow_state or default."""
        if getattr(self, "status", None):
            return
        state = getattr(self, "workflow_state", None)
        self.status = state or "Draft"
        if self.status == "Pending Review":
            self.current_approval_level = getattr(self, "current_approval_level", None) or 1
        else:
            self.current_approval_level = 0

    def _set_requester_to_creator(self):
        """Set requester to current user if not set."""
        if not getattr(self, "requester", None):
            self.requester = frappe.session.user

    def _reset_status_if_copied(self):
        """Clear status when copying from submitted doc."""
        if getattr(self, "docstatus", 0) == 0 and getattr(self, "status", None) in ("Rejected", "Approved"):
            self.status = None
            self.workflow_state = None
            self.current_approval_level = 0
            self.approved_on = None
            self.rejected_on = None
            self.approval_route_snapshot = None
            self.level_1_user = None
            self.level_2_user = None
            self.level_3_user = None

    def validate_submit_permission(self):
        """Best practice: only creator or Expense Approver/System Manager can submit."""
        allowed_roles = {roles.SYSTEM_MANAGER, roles.EXPENSE_APPROVER}
        current_roles = set(frappe.get_roles())

        if frappe.session.user == self.owner:
            return

        if current_roles & allowed_roles:
            return

        frappe.throw(_("Only the creator or an Expense Approver/System Manager can submit."))

    def _resolve_approval_route(self) -> tuple[dict, dict | None, bool]:
        """Get approval route for this request."""
        try:
            setting = get_active_setting_meta(self.cost_center)
            route = get_approval_route(
                self.cost_center,
                self._get_expense_accounts(),
                self.amount,
                setting_meta=setting,
            )
            return route or {}, setting, False
        except Exception:
            return {}, None, True

    def _ensure_route_ready(self, route: dict, failed: bool = False) -> None:
        """Validate route is ready; require at least one configured approver.

        For Expense Request, we do **not** auto-approve when there is no
        approver/route. Instead we force configuration of an Expense
        Approval Setting before submit.
        """
        if failed or not self._has_approver(route):
            message = approval_setting_required_message(getattr(self, "cost_center", None))
            frappe.throw(message, title=_("Approval Route Not Found"))

    def apply_route(self, route: dict, *, setting_meta: dict | None = None) -> None:
        """Store approval route on document."""
        self.level_1_user = route.get("level_1", {}).get("user")
        self.level_2_user = route.get("level_2", {}).get("user")
        self.level_3_user = route.get("level_3", {}).get("user")
        ApprovalRouteService.record_setting_meta(self, setting_meta)

    def record_approval_route_snapshot(self, route: dict | None = None) -> None:
        """Save route for audit (used at Approved for Close validation)."""
        route = route or self._get_route_snapshot()
        try:
            self.approval_route_snapshot = json.dumps(route) if isinstance(route, dict) else route
        except Exception:
            pass

    def validate_route_users_exist(self, route: dict | None = None) -> None:
        """Ensure all route users exist and are enabled."""
        from imogi_finance.approval import validate_route_users

        route = route or self._get_route_snapshot()
        if not route:
            return

        validation = validate_route_users(route)
        if validation.get("valid"):
            return

        error_parts: list[str] = []

        invalid_users = validation.get("invalid_users") or []
        if invalid_users:
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
                _("Invalid approvers: {0}. Update Expense Approval Setting.").format("; ".join(error_parts))
            )

    def _get_route_snapshot(self) -> dict:
        """Get stored approval route."""
        from imogi_finance.approval import parse_route_snapshot
        
        snapshot = getattr(self, "approval_route_snapshot", None)
        parsed = parse_route_snapshot(snapshot)
        if parsed:
            return parsed
        
        # Fallback: build from level_*_user fields
        return {f"level_{l}": {"user": getattr(self, f"level_{l}_user", None)} for l in (1, 2, 3)}

    def _has_approver(self, route: dict | None) -> bool:
        """Check if route has at least one approver."""
        from imogi_finance.approval import has_approver_in_route
        return has_approver_in_route(route)

    # ===================== Utility =====================

    def _get_company(self) -> str | None:
        cost_center = getattr(self, "cost_center", None)
        if cost_center:
            return frappe.db.get_value("Cost Center", cost_center, "company")
        return None

    def _get_expense_accounts(self) -> tuple[str, ...]:
        """Get expense accounts from items."""
        accounts = getattr(self, "expense_accounts", None)
        if accounts:
            return accounts

        _, accounts = accounting.summarize_request_items(self.get("items"))
        return accounts

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
                pass
        return previous
