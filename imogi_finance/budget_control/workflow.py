"""Workflow helpers for Expense Request budget lock, internal charge, and consumption."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Iterable

import frappe
from frappe import _

from imogi_finance import accounting
from imogi_finance.budget_control import ledger, service, utils


def _get_account_totals(items: Iterable) -> tuple[float, dict[str, float]]:
    total = 0.0
    per_account: dict[str, float] = defaultdict(float)

    for item in items or []:
        account = accounting._get_item_value(item, "expense_account")
        amount = accounting._get_item_value(item, "amount")

        if not account or amount is None:
            continue

        per_account[account] += float(amount)
        total += float(amount)

    return total, per_account


def _load_internal_charge_request(ic_name: str | None):
    if not ic_name:
        return None

    try:
        return frappe.get_doc("Internal Charge Request", ic_name)
    except Exception:
        return None


def _parse_route_snapshot(raw_snapshot):
    if not raw_snapshot:
        return {}

    if isinstance(raw_snapshot, dict):
        return raw_snapshot

    try:
        return json.loads(raw_snapshot)
    except Exception:
        return {}


def _iter_internal_charge_lines(ic_doc) -> Iterable:
    for line in getattr(ic_doc, "internal_charge_lines", []) or []:
        yield line


def _require_internal_charge_ready(expense_request, settings):
    required = settings.get("internal_charge_required_before_er_approval")
    if not required:
        return None

    ic_name = getattr(expense_request, "internal_charge_request", None)
    if not ic_name:
        frappe.throw(_("Internal Charge Request is required before approval for allocated requests."))

    ic_doc = _load_internal_charge_request(ic_name)
    if not ic_doc or getattr(ic_doc, "status", None) != "Approved":
        frappe.throw(_("Internal Charge Request {0} must be Approved.").format(ic_name))

    total_amount, account_totals = _get_account_totals(getattr(expense_request, "items", []) or [])
    ic_total = sum(float(getattr(line, "amount", 0) or 0) for line in _iter_internal_charge_lines(ic_doc))

    if total_amount and abs(ic_total - total_amount) > 0.0001:
        frappe.throw(_("Internal Charge Request total ({0}) must equal Expense Request total ({1}).").format(ic_total, total_amount))

    if not account_totals:
        frappe.throw(_("Expense Request must have at least one expense account before allocating."))

    return ic_doc


def _build_allocation_slices(expense_request, *, settings=None, ic_doc=None):
    settings = settings or utils.get_settings()
    company = utils.resolve_company_from_cost_center(getattr(expense_request, "cost_center", None))
    fiscal_year = getattr(expense_request, "fiscal_year", None)

    total_amount, account_totals = _get_account_totals(getattr(expense_request, "items", []) or [])
    if not account_totals:
        return []

    slices = []

    if getattr(expense_request, "allocation_mode", "Direct") != "Allocated via Internal Charge":
        for account, amount in account_totals.items():
            dims = service.resolve_dims(
                company=company,
                fiscal_year=fiscal_year,
                cost_center=getattr(expense_request, "cost_center", None),
                account=account,
                project=getattr(expense_request, "project", None),
                branch=getattr(expense_request, "branch", None),
            )
            slices.append((dims, float(amount)))
        return slices

    ic_doc = ic_doc or _load_internal_charge_request(getattr(expense_request, "internal_charge_request", None))
    if not ic_doc:
        return []

    if not total_amount:
        return []

    for line in _iter_internal_charge_lines(ic_doc):
        ratio = float(getattr(line, "amount", 0) or 0) / float(total_amount or 1)
        for account, account_amount in account_totals.items():
            dims = service.resolve_dims(
                company=company,
                fiscal_year=fiscal_year,
                cost_center=getattr(line, "target_cost_center", None),
                account=account,
                project=getattr(expense_request, "project", None),
                branch=getattr(expense_request, "branch", None),
            )
            slices.append((dims, float(account_amount) * ratio))

    return slices


def _get_entries_for_ref(ref_doctype: str, ref_name: str, entry_type: str | None = None):
    filters = {"ref_doctype": ref_doctype, "ref_name": ref_name, "docstatus": 1}
    if entry_type:
        filters["entry_type"] = entry_type

    try:
        return frappe.get_all(
            "Budget Control Entry",
            filters=filters,
            fields=[
                "name",
                "entry_type",
                "company",
                "fiscal_year",
                "cost_center",
                "account",
                "project",
                "branch",
                "amount",
                "direction",
            ],
        )
    except Exception:
        return []


def _reverse_reservations(expense_request):
    reservations = _get_entries_for_ref("Expense Request", getattr(expense_request, "name", None), "RESERVATION")
    if not reservations:
        return

    for row in reservations:
        dims = utils.Dimensions(
            company=row.get("company"),
            fiscal_year=row.get("fiscal_year"),
            cost_center=row.get("cost_center"),
            account=row.get("account"),
            project=row.get("project"),
            branch=row.get("branch"),
        )
        ledger.post_entry(
            "RELEASE",
            dims,
            float(row.get("amount") or 0),
            "IN",
            ref_doctype="Expense Request",
            ref_name=getattr(expense_request, "name", None),
            remarks=_("Releasing prior reservation before re-locking"),
        )


def reserve_budget_for_request(expense_request, *, trigger_action: str | None = None, next_state: str | None = None):
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return

    target_state = settings.get("lock_on_workflow_state") or "Approved"
    if getattr(expense_request, "status", None) != target_state:
        return

    ic_doc = None
    if getattr(expense_request, "allocation_mode", "Direct") == "Allocated via Internal Charge":
        ic_doc = _require_internal_charge_ready(expense_request, settings)

    slices = _build_allocation_slices(expense_request, settings=settings, ic_doc=ic_doc)
    if not slices:
        return

    allow_role = settings.get("allow_budget_overrun_role")
    allow_overrun = bool(allow_role and allow_role in frappe.get_roles())

    _reverse_reservations(expense_request)

    any_overrun = False
    for dims, amount in slices:
        result = service.check_budget_available(dims, float(amount or 0))
        if not result.ok and not allow_overrun:
            frappe.throw(result.message)

        if not result.ok:
            any_overrun = True

    for dims, amount in slices:
        ledger.post_entry(
            "RESERVATION",
            dims,
            float(amount or 0),
            "OUT",
            ref_doctype="Expense Request",
            ref_name=getattr(expense_request, "name", None),
            remarks=_("Budget reservation for Expense Request"),
        )

    status = "Overrun Allowed" if any_overrun else "Locked"
    if getattr(expense_request, "budget_lock_status", None) != status:
        if hasattr(expense_request, "db_set"):
            expense_request.db_set("budget_lock_status", status)
        expense_request.budget_lock_status = status


def release_budget_for_request(expense_request):
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return

    reservations = _get_entries_for_ref("Expense Request", getattr(expense_request, "name", None), "RESERVATION")
    if not reservations:
        return

    for row in reservations:
        dims = utils.Dimensions(
            company=row.get("company"),
            fiscal_year=row.get("fiscal_year"),
            cost_center=row.get("cost_center"),
            account=row.get("account"),
            project=row.get("project"),
            branch=row.get("branch"),
        )
        ledger.post_entry(
            "RELEASE",
            dims,
            float(row.get("amount") or 0),
            "IN",
            ref_doctype="Expense Request",
            ref_name=getattr(expense_request, "name", None),
            remarks=_("Release on rejection or cancel"),
        )

    if hasattr(expense_request, "db_set"):
        expense_request.db_set("budget_lock_status", "Released")
    expense_request.budget_lock_status = "Released"


def handle_expense_request_workflow(expense_request, action: str | None, next_state: str | None):
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return

    target_state = settings.get("lock_on_workflow_state") or "Approved"

    if action in {"Reject", "Reopen"} or (next_state and next_state not in {target_state, "Linked"}):
        release_budget_for_request(expense_request)
        return

    if getattr(expense_request, "status", None) == target_state or next_state == target_state:
        reserve_budget_for_request(expense_request, trigger_action=action, next_state=next_state)


def consume_budget_for_purchase_invoice(purchase_invoice, expense_request=None):
    settings = utils.get_settings()
    enforce_mode = (settings.get("enforce_mode") or "Both").lower()
    if not settings.get("enable_budget_lock"):
        return

    if enforce_mode not in {"both", "pi submit only"}:
        return

    request = expense_request
    if request is None:
        er_name = getattr(purchase_invoice, "imogi_expense_request", None) or getattr(purchase_invoice, "expense_request", None)
        if not er_name:
            return

        try:
            request = frappe.get_doc("Expense Request", er_name)
        except Exception:
            request = None

    if not request:
        return

    existing = _get_entries_for_ref("Purchase Invoice", getattr(purchase_invoice, "name", None), "CONSUMPTION")
    if existing:
        return

    slices = _build_allocation_slices(request, settings=settings)
    if not slices:
        return

    for dims, amount in slices:
        ledger.post_entry(
            "CONSUMPTION",
            dims,
            float(amount or 0),
            "IN",
            ref_doctype="Purchase Invoice",
            ref_name=getattr(purchase_invoice, "name", None),
            remarks=_("Budget consumption on Purchase Invoice submit"),
        )

    if hasattr(request, "db_set"):
        request.db_set("budget_lock_status", "Consumed")
    request.budget_lock_status = "Consumed"


def reverse_consumption_for_purchase_invoice(purchase_invoice, expense_request=None):
    settings = utils.get_settings()
    enforce_mode = (settings.get("enforce_mode") or "Both").lower()
    if not settings.get("enable_budget_lock"):
        return

    if enforce_mode not in {"both", "pi submit only"}:
        return

    request = expense_request
    if request is None:
        er_name = getattr(purchase_invoice, "imogi_expense_request", None) or getattr(purchase_invoice, "expense_request", None)
        if er_name:
            try:
                request = frappe.get_doc("Expense Request", er_name)
            except Exception:
                request = None

    entries = _get_entries_for_ref("Purchase Invoice", getattr(purchase_invoice, "name", None), "CONSUMPTION")
    if not entries:
        return

    for row in entries:
        dims = utils.Dimensions(
            company=row.get("company"),
            fiscal_year=row.get("fiscal_year"),
            cost_center=row.get("cost_center"),
            account=row.get("account"),
            project=row.get("project"),
            branch=row.get("branch"),
        )
        ledger.post_entry(
            "REVERSAL",
            dims,
            float(row.get("amount") or 0),
            "OUT",
            ref_doctype="Purchase Invoice",
            ref_name=getattr(purchase_invoice, "name", None),
            remarks=_("Reverse consumption on Purchase Invoice cancel"),
        )

    if request:
        if hasattr(request, "db_set"):
            request.db_set("budget_lock_status", "Locked")
        request.budget_lock_status = "Locked"


def maybe_post_internal_charge_je(purchase_invoice, expense_request=None):
    settings = utils.get_settings()
    if settings.get("internal_charge_posting_mode") != "Auto JE on PI Submit":
        return

    request = expense_request
    if request is None:
        er_name = getattr(purchase_invoice, "imogi_expense_request", None) or getattr(purchase_invoice, "expense_request", None)
        if not er_name:
            return

        try:
            request = frappe.get_doc("Expense Request", er_name)
        except Exception:
            return

    if getattr(request, "allocation_mode", "Direct") != "Allocated via Internal Charge":
        return

    ic_doc = _load_internal_charge_request(getattr(request, "internal_charge_request", None))
    if not ic_doc or getattr(ic_doc, "status", None) != "Approved":
        return

    slices = _build_allocation_slices(request, settings=settings, ic_doc=ic_doc)
    if not slices:
        return

    total_amount, account_totals = _get_account_totals(getattr(request, "items", []) or [])
    if not total_amount:
        return

    per_cc_account: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for dims, amount in slices:
        per_cc_account[dims.cost_center][dims.account] += float(amount or 0)

    try:
        je = frappe.new_doc("Journal Entry")
    except Exception:
        return

    je.company = getattr(purchase_invoice, "company", None)
    je.posting_date = getattr(purchase_invoice, "posting_date", None)
    je.user_remark = _(
        "Auto internal charge reclassification for Expense Request {0} via Purchase Invoice {1}."
    ).format(getattr(request, "name", None), getattr(purchase_invoice, "name", None))

    source_cc = getattr(request, "cost_center", None)

    for account, amount in account_totals.items():
        je.append(
            "accounts",
            {
                "account": account,
                "cost_center": source_cc,
                "credit_in_account_currency": float(amount or 0),
                "reference_type": "Purchase Invoice",
                "reference_name": getattr(purchase_invoice, "name", None),
            },
        )

    for cc, accounts in per_cc_account.items():
        if cc == source_cc:
            continue
        for account, amount in accounts.items():
            je.append(
                "accounts",
                {
                    "account": account,
                    "cost_center": cc,
                    "debit_in_account_currency": float(amount or 0),
                    "reference_type": "Purchase Invoice",
                    "reference_name": getattr(purchase_invoice, "name", None),
                },
            )

    if not getattr(je, "accounts", None):
        return

    je.flags.ignore_permissions = True
    try:
        je.insert(ignore_permissions=True)
        if hasattr(je, "submit"):
            je.submit()
    except Exception:
        try:
            frappe.log_error(
                title=_("Internal Charge Journal Entry Failed"),
                message={
                    "expense_request": getattr(request, "name", None),
                    "purchase_invoice": getattr(purchase_invoice, "name", None),
                },
            )
        except Exception:
            pass


@frappe.whitelist()
def create_internal_charge_from_expense_request(er_name: str) -> str:
    settings = utils.get_settings()
    if not settings.get("enable_internal_charge"):
        frappe.throw(_("Internal Charge feature is disabled. Please enable it in Budget Control Settings."))

    request = frappe.get_doc("Expense Request", er_name)
    if getattr(request, "allocation_mode", "Direct") != "Allocated via Internal Charge":
        frappe.throw(_("Allocation mode must be 'Allocated via Internal Charge' to create an Internal Charge Request."))

    if getattr(request, "internal_charge_request", None):
        return request.internal_charge_request

    total, expense_accounts = accounting.summarize_request_items(getattr(request, "items", []) or [])
    company = utils.resolve_company_from_cost_center(getattr(request, "cost_center", None))
    fiscal_year = utils.resolve_fiscal_year(getattr(request, "fiscal_year", None))

    ic = frappe.new_doc("Internal Charge Request")
    ic.expense_request = request.name
    ic.company = company
    ic.fiscal_year = fiscal_year
    ic.posting_date = getattr(request, "request_date", None) or frappe.utils.nowdate()
    ic.source_cost_center = getattr(request, "cost_center", None)
    ic.total_amount = total
    ic.allocation_mode = "Allocated via Internal Charge"

    # auto-suggest a single line to the source cost center as a starting point
    ic.append(
        "internal_charge_lines",
        {
            "target_cost_center": getattr(request, "cost_center", None),
            "amount": total,
        },
    )

    ic.insert(ignore_permissions=True)

    if hasattr(request, "db_set"):
        request.db_set("internal_charge_request", ic.name)
    request.internal_charge_request = ic.name

    return ic.name
