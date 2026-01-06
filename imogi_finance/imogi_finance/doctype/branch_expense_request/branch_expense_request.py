from __future__ import annotations

from datetime import date
from typing import Iterable

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_first_day, get_last_day, nowdate

from imogi_finance import accounting
from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.budget_control import ledger, service
from imogi_finance.services.deferred_expense import generate_amortization_schedule
from imogi_finance.services.letter_template_service import render_payment_letter_html
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
    STATUS_PENDING = "Pending Approval"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CANCELLED = "Cancelled"

    def before_insert(self):
        self._set_requester()

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
        self._sync_status_field()

    def before_submit(self):
        settings = get_settings()
        self._validate_items(settings)
        self.validate_amounts()
        self.apply_branch_defaults()
        self.validate_tax_fields()
        self._validate_deferred_expense()
        self._update_totals()
        self._set_fiscal_year()
        if not getattr(self, "branch", None):
            frappe.throw(_("Branch is required before submission."))
        self._run_budget_checks(settings, for_submit=True)

        if not getattr(self, "workflow_state", None):
            self.workflow_state = self.STATUS_PENDING
        self.status = self.workflow_state

    def on_workflow_action(self, action, next_state=None):
        if action in {"Approve", "Reject"} and not getattr(self, "branch", None):
            frappe.throw(_("Branch is required before applying workflow actions."))

        if next_state:
            self.workflow_state = next_state
        self._sync_status_field()

    def on_cancel(self):
        self.status = self.STATUS_CANCELLED

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

    def _validate_deferred_expense(self):
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

    def get_payment_letter_html(self):
        return render_payment_letter_html(self)


def apply_default_amounts(item):
    item.qty = flt(getattr(item, "qty", 0)) or 0
    item.rate = flt(getattr(item, "rate", 0)) or 0
    item.amount = flt(item.qty) * flt(item.rate)


@frappe.whitelist()
def get_branch_expense_request_payment_letter(name: str):
    doc = frappe.get_doc("Branch Expense Request", name)
    return doc.get_payment_letter_html()
