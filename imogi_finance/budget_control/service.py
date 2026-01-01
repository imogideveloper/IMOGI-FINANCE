# Developer scan notes (2024-11-05):
# - Expense Request workflows and approval enforcement live in
#   imogi_finance/imogi_finance/doctype/expense_request/expense_request.py, with route resolution via
#   imogi_finance.approval.get_approval_route/get_active_setting_meta and Purchase Invoice creation through
#   imogi_finance.accounting.create_purchase_invoice_from_request.
# - Approval rules are configured in Expense Approval Setting/Line doctypes (imogi_finance.approval).
# - Branch defaults and enforcement rely on imogi_finance.branching.resolve_branch/apply_branch, also used in
#   imogi_finance.events.purchase_invoice and ExpenseRequest.apply_branch_defaults.
# - No budget control or internal charge doctypes existed prior to this phase; accounting helpers cover item
#   summarization (imogi_finance.accounting.summarize_request_items) and downstream link validation only.

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

import frappe
from frappe import _

from imogi_finance import accounting
from imogi_finance.budget_control import ledger, native_budget, utils


@dataclass
class BudgetCheckResult:
    ok: bool
    message: str
    available: float | None = None
    snapshot: dict | None = None


def resolve_dims(
    *,
    company: str | None = None,
    fiscal_year: str | None = None,
    cost_center: str | None = None,
    account: str | None = None,
    project: str | None = None,
    branch: str | None = None,
) -> utils.Dimensions:
    settings = utils.get_settings()
    dimension_mode = settings.get("dimension_mode") or "Native (Cost Center + Account)"
    resolved_company = company or utils.resolve_company_from_cost_center(cost_center)
    resolved_fy = utils.resolve_fiscal_year(fiscal_year)

    project_value = project if utils.allow_project(dimension_mode) else None
    branch_value = branch if utils.allow_branch(dimension_mode) else None

    return utils.Dimensions(
        company=resolved_company,
        fiscal_year=resolved_fy,
        cost_center=cost_center,
        account=account,
        project=project_value,
        branch=branch_value,
    )


def resolve_expense_accounts_from_items(items: Iterable) -> tuple[str, ...]:
    _, accounts = accounting.summarize_request_items(items, skip_invalid_items=True)
    return accounts


def check_budget_available(dims: utils.Dimensions, amount: float) -> BudgetCheckResult:
    result = ledger.check_budget_available(dims, amount)
    return BudgetCheckResult(
        ok=bool(result.get("ok")),
        message=result.get("message", ""),
        available=result.get("available"),
        snapshot=result if isinstance(result, dict) else None,
    )


def post_entry(
    entry_type: str,
    dims: utils.Dimensions,
    amount: float,
    direction: str,
    *,
    ref_doctype: str | None = None,
    ref_name: str | None = None,
    remarks: str | None = None,
) -> str | None:
    return ledger.post_entry(entry_type, dims, amount, direction, ref_doctype=ref_doctype, ref_name=ref_name, remarks=remarks)


def apply_budget_allocation_delta(dims: utils.Dimensions, delta_amount: float):
    return native_budget.apply_budget_allocation_delta(dims, delta_amount)


def record_reclass(
    *,
    from_dims: utils.Dimensions,
    to_dims: utils.Dimensions,
    amount: float,
    ref_doctype: str | None = None,
    ref_name: str | None = None,
):
    post_entry("RECLASS", from_dims, amount, "OUT", ref_doctype=ref_doctype, ref_name=ref_name, remarks=_("Budget reclassification outflow"))
    post_entry("RECLASS", to_dims, amount, "IN", ref_doctype=ref_doctype, ref_name=ref_name, remarks=_("Budget reclassification inflow"))
    apply_budget_allocation_delta(from_dims, -float(amount or 0))
    apply_budget_allocation_delta(to_dims, float(amount or 0))


def record_supplement(
    *,
    dims: utils.Dimensions,
    amount: float,
    ref_doctype: str | None = None,
    ref_name: str | None = None,
):
    post_entry("SUPPLEMENT", dims, amount, "IN", ref_doctype=ref_doctype, ref_name=ref_name, remarks=_("Additional budget allocation"))
    apply_budget_allocation_delta(dims, float(amount or 0))


def serialize_route(route: dict | None) -> str:
    if not route:
        return ""

    try:
        if hasattr(frappe, "as_json"):
            return frappe.as_json(route)
    except Exception:
        pass

    try:
        return json.dumps(route)
    except Exception:
        return str(route)
