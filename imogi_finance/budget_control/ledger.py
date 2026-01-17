# Developer scan notes (2024-11-05):
# - Expense Request approval, workflow guards, and Purchase Invoice creation live in
#   imogi_finance/imogi_finance/doctype/expense_request/expense_request.py with approval resolution
#   through imogi_finance.approval.get_approval_route/get_active_setting_meta.
# - Approval configuration is defined by Expense Approval Setting and Expense Approval Line doctypes.
# - Branch handling is centralized in imogi_finance.branching (resolve_branch/apply_branch) and enforced
#   in purchase invoice events (imogi_finance.events.purchase_invoice) and ExpenseRequest.apply_branch_defaults.
# - No budget or internal charge ledger exists yet; accounting helpers cover item summarization and link checks only.

from __future__ import annotations

from datetime import date

import frappe
from frappe import _

from imogi_finance.budget_control import native_budget
from imogi_finance.budget_control.utils import Dimensions, get_settings


def _entry_filters(dims: Dimensions, entry_types: list[str]):
    filters = {
        "company": dims.company,
        "fiscal_year": dims.fiscal_year,
        "cost_center": dims.cost_center,
        "account": dims.account,
        "entry_type": ["in", entry_types],
        "docstatus": 1,
    }

    if dims.project:
        filters["project"] = dims.project
    if dims.branch:
        filters["branch"] = dims.branch

    return filters


def get_reserved_total(dims: Dimensions, from_date: date | None = None, to_date: date | None = None) -> float:
    """Calculate total reserved budget from Budget Control Entries.
    
    Reserved = RESERVATION (OUT) - CONSUMPTION (IN) + REVERSAL (OUT)
    
    Logic:
    - RESERVATION: Budget yang di-hold untuk Expense Request
    - CONSUMPTION: Mengurangi reserved saat PI submit (consume dari reservation)
    - REVERSAL: Mengembalikan reserved saat PI cancel (restore reservation)
    - RELEASE: TIDAK DIPAKAI LAGI (simplified flow)
    
    Contoh:
    - ER submit: RESERVATION +100 → Reserved = 100
    - PI submit: CONSUMPTION +100 → Reserved = 100 - 100 = 0
    - PI cancel: REVERSAL +100 → Reserved = 100 - 100 + 100 = 100
    """
    try:
        rows = frappe.get_all(
            "Budget Control Entry",
            filters={
                **_entry_filters(dims, ["RESERVATION", "CONSUMPTION", "REVERSAL"]),
                **(
                    {"posting_date": ["between", [from_date, to_date]]}
                    if from_date and to_date
                    else {}
                ),
            },
            fields=["entry_type", "direction", "amount"],
        )
    except Exception:
        rows = []

    total = 0.0
    for row in rows or []:
        entry_type = row.get("entry_type")
        direction = row.get("direction")
        amount = float(row.get("amount") or 0.0)

        if entry_type == "RESERVATION" and direction == "OUT":
            total += amount  # Reserve budget
        elif entry_type == "CONSUMPTION" and direction == "IN":
            total -= amount  # Consume reserved budget
        elif entry_type == "REVERSAL" and direction == "OUT":
            total += amount  # Restore reserved budget (after PI cancel)

    return total


def get_availability(dims: Dimensions, from_date: date | None = None, to_date: date | None = None) -> dict:
    allocated = native_budget.get_allocated_from_erpnext_budget(dims)
    actual = native_budget.get_actual_spent(dims, from_date=from_date, to_date=to_date)
    reserved = get_reserved_total(dims, from_date=from_date, to_date=to_date)
    available = allocated - actual - reserved

    return {
        "allocated": allocated,
        "actual": actual,
        "reserved": reserved,
        "available": available,
    }


def check_budget_available(dims: Dimensions, amount: float, from_date: date | None = None, to_date: date | None = None) -> dict:
    settings = get_settings()
    if not settings.get("enable_budget_lock"):
        return {"ok": True, "message": _("Budget lock disabled in settings."), "available": None}

    # Check if Budget document exists for this cost center/company/fiscal year
    if not native_budget.budget_exists_for_dims(dims):
        return {
            "ok": True,
            "message": _("No Budget configured for Cost Center {cc} - budget check bypassed.").format(
                cc=dims.cost_center or _("(unknown)")
            ),
            "available": None,
            "allocated": None,
            "actual": None,
            "reserved": None,
        }

    snapshot = get_availability(dims, from_date=from_date, to_date=to_date)
    ok = snapshot["available"] >= float(amount or 0)
    message = (
        _("Available budget is {available}, requested {amount}.").format(
            available=snapshot["available"], amount=amount
        )
        if ok
        else _("Insufficient budget. Available {available}, requested {amount}.").format(
            available=snapshot["available"], amount=amount
        )
    )
    snapshot.update({"ok": ok, "message": message})
    return snapshot


def post_entry(
    entry_type: str,
    dims: Dimensions,
    amount: float,
    direction: str,
    *,
    ref_doctype: str | None = None,
    ref_name: str | None = None,
    remarks: str | None = None,
) -> str | None:
    settings = get_settings()
    if entry_type in {"RESERVATION", "CONSUMPTION", "REVERSAL"} and not settings.get("enable_budget_lock"):
        return None
    if entry_type == "RECLASS" and not settings.get("enable_budget_reclass"):
        return None
    if entry_type == "SUPPLEMENT" and not settings.get("enable_additional_budget"):
        return None

    try:
        entry = frappe.new_doc("Budget Control Entry")
    except Exception:
        return None

    entry.entry_type = entry_type
    entry.company = dims.company
    entry.posting_date = date.today()
    entry.fiscal_year = dims.fiscal_year
    entry.cost_center = dims.cost_center
    entry.account = dims.account
    entry.amount = float(amount or 0.0)
    entry.direction = direction
    entry.ref_doctype = ref_doctype
    entry.ref_name = ref_name
    entry.remarks = remarks

    if getattr(entry, "meta", None) and getattr(entry.meta, "get_field", None):
        # Populate optional dimensions when the field exists.
        if dims.project and entry.meta.get_field("project"):
            entry.project = dims.project
        if dims.branch and entry.meta.get_field("branch"):
            entry.branch = dims.branch
    else:
        entry.project = getattr(dims, "project", None)
        entry.branch = getattr(dims, "branch", None)

    try:
        entry.insert(ignore_permissions=True)
        if hasattr(entry, "submit"):
            entry.submit()
        return entry.name
    except Exception:
        return None
