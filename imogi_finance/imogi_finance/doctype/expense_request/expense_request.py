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
        self.validate_asset_details()
        self._sync_tax_invoice_upload()
        self.validate_tax_fields()
        self.validate_deferred_expense()
        validate_tax_invoice_upload_link(self, "Expense Request")
        self._ensure_final_state_immutability()

    def before_submit(self):
        """Prepare for submission - resolve approval route and initialize state."""
        self.validate_submit_permission()

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
        try:
            handle_expense_request_workflow(self, "Submit", getattr(self, "workflow_state"))
        except Exception:
            # Budget module not critical - don't block
            pass

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
                handle_expense_request_workflow(self, action, getattr(self, "workflow_state"))
            except Exception:
                # Budget module errors don't block workflow
                pass

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
        for doctype, field in [("Payment Entry", "linked_payment_entry"), ("Purchase Invoice", "linked_purchase_invoice"), ("Asset", "linked_asset")]:
            name = getattr(self, field, None)
            if name and frappe.db.get_value(doctype, name, "docstatus") != 2:
                active_links.append(f"{doctype} {name}")

        if active_links:
            frappe.throw(
                _("Cannot cancel while linked to: {0}. Cancel them first.").format(", ".join(active_links)),
                title=_("Active Links Exist"),
            )

    def on_cancel(self):
        """Clean up: release budget reservations."""
        try:
            release_budget_for_request(self, reason="Cancel")
        except Exception:
            pass

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
        pph_base_total = item_pph_total or (
            flt(getattr(self, "pph_base_amount", 0) or 0) if getattr(self, "is_pph_applicable", 0) else 0
        )
        pph_rate = _resolve_pph_rate(getattr(self, "pph_type", None))
        total_pph = (pph_base_total * pph_rate / 100) if pph_rate else pph_base_total
        # Ensure total_pph is always stored as positive (absolute value)
        # for consistency, since we subtract it in the formula.
        total_pph = abs(total_pph)
        # PPh is withholding tax, so it reduces the total payable amount.
        total_amount = total_expense + total_asset + total_ppn + total_ppnbm - total_pph

        # Keep header PPh base amount in sync with the effective base used for calculations.
        if getattr(self, "is_pph_applicable", 0) or item_pph_total:
            self.pph_base_amount = pph_base_total
        else:
            self.pph_base_amount = 0

        self.total_expense = total_expense
        self.total_asset = total_asset
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

    def validate_asset_details(self):
        """Ensure asset requests have required fields."""
        if self.request_type != "Asset":
            return

        if getattr(self, "build_cumulative_asset_from_items", 0):
            self._sync_cumulative_asset_items()
            return

        asset_items = self.get("asset_items") or []
        if not asset_items:
            frappe.throw(_("Asset List is required for Asset requests."))

        for idx, item in enumerate(asset_items, start=1):
            required = ["asset_category", "asset_name", "asset_description", "qty"]
            missing = [f for f in required if not getattr(item, f, None)]
            if missing:
                frappe.throw(_("Row {0} missing: {1}").format(idx, ", ".join(missing)))

    def _sync_cumulative_asset_items(self):
        """Build single asset from total amount."""
        items = self.get("items") or []
        if not items:
            frappe.throw(_("Expense Items required for cumulative asset."))

        required = ["asset_category", "asset_name", "asset_description"]
        missing = [f for f in required if not getattr(self, f, None)]
        if missing:
            frappe.throw(_("Header requires: {0}").format(", ".join(missing)))

        self.set("asset_items", [])
        self.append("asset_items", {
            "asset_category": self.asset_category,
            "asset_name": self.asset_name,
            "asset_description": self.asset_description,
            "asset_location": getattr(self, "asset_location", None),
            "qty": 1,
            "amount": flt(self.amount),
        })

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

    def validate_deferred_expense(self):
        """Validate deferred expense configuration."""
        if not getattr(self, "is_deferred_expense", 0):
            return

        if not getattr(self, "deferred_start_date", None):
            frappe.throw(_("Deferred Start Date required."))

        periods = getattr(self, "deferred_periods", None)
        if not periods or periods <= 0:
            frappe.throw(_("Deferred Periods must be > 0."))

        schedule = generate_amortization_schedule(
            flt(self.amount), periods, self.deferred_start_date
        )
        if not hasattr(self, "flags"):
            self.flags = type("Flags", (), {})()
        self.flags.deferred_amortization_schedule = schedule

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
            approval_amount = self.amount
            if getattr(self, "request_type", None) == "Asset":
                approval_amount = self.total_amount
            route = get_approval_route(
                self.cost_center,
                self._get_expense_accounts(),
                approval_amount,
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
