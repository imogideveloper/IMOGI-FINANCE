# Developer scan notes (2024-11-05):
# - Expense Request approval and workflow guards live in imogi_finance/imogi_finance/doctype/expense_request/expense_request.py
#   using imogi_finance.approval.get_approval_route/get_active_setting_meta plus accounting.summarize_request_items.
# - Approval routes rely on Expense Approval Setting and Expense Approval Line doctypes (imogi_finance.approval).
# - Branch handling flows through imogi_finance.branching.resolve_branch/apply_branch and is enforced in events hooks
#   such as imogi_finance.events.purchase_invoice.on_submit.
# - No prior budget ledger or internal charge doctypes exist; accounting helpers are limited to Purchase Invoice creation
#   and downstream link validation.

from __future__ import annotations

from typing import Iterable

import frappe
from frappe import _

from imogi_finance.budget_control.utils import Dimensions


def _find_budget_for_dims(dims: Dimensions) -> str | None:
    filters = {
        "company": dims.company,
        "fiscal_year": dims.fiscal_year,
    }

    if dims.cost_center:
        filters["cost_center"] = dims.cost_center

    try:
        budgets = frappe.get_all("Budget", filters=filters, fields=["name", "cost_center"])
    except Exception:
        budgets = []

    if not budgets and dims.cost_center:
        # Retry without cost center to avoid missing a single company/fiscal budget.
        try:
            budgets = frappe.get_all(
                "Budget",
                filters={"company": dims.company, "fiscal_year": dims.fiscal_year},
                fields=["name", "cost_center"],
            )
        except Exception:
            budgets = []

    if not budgets:
        return None

    if dims.cost_center:
        scoped = [row for row in budgets if row.get("cost_center") == dims.cost_center]
        if len(scoped) == 1:
            return scoped[0].get("name")

        if len(scoped) > 1:
            frappe.throw(
                _(
                    "Multiple Budgets found for Cost Center {0}. Please consolidate or set a single active Budget."
                ).format(dims.cost_center)
            )

    if len(budgets) > 1:
        frappe.throw(
            _(
                "Multiple Budgets found for Company {company} and Fiscal Year {fy}. Please keep one active Budget or scope Budgets per Cost Center."
            ).format(company=dims.company or _("(unknown)"), fy=dims.fiscal_year or _("(unknown)"))
        )

    return budgets[0].get("name")


def _load_budget_account_row(budget_name: str, account: str | None):
    if not budget_name or not account:
        return None

    try:
        rows = frappe.get_all(
            "Budget Account",
            filters={"parent": budget_name, "account": account},
            fields=["name", "budget_amount"],
            limit=1,
        )
        return rows[0] if rows else None
    except Exception:
        return None


def get_allocated_from_erpnext_budget(dims: Dimensions) -> float:
    budget_name = _find_budget_for_dims(dims)
    if not budget_name:
        return 0.0

    row = _load_budget_account_row(budget_name, dims.account)
    if not row:
        return 0.0

    amount = row.get("budget_amount")
    try:
        return float(amount or 0.0)
    except Exception:
        return 0.0


def get_actual_spent(dims: Dimensions) -> float:
    if not getattr(frappe, "db", None) or not getattr(frappe.db, "sql", None):
        return 0.0

    params = {
        "company": dims.company,
        "account": dims.account,
        "cost_center": dims.cost_center,
    }

    fiscal_filters = ""
    if dims.fiscal_year:
        try:
            fy_row = frappe.db.get_value(
                "Fiscal Year", dims.fiscal_year, ["year_start_date", "year_end_date"], as_dict=True
            )
        except Exception:
            fy_row = None

        if fy_row and fy_row.get("year_start_date") and fy_row.get("year_end_date"):
            fiscal_filters = "and posting_date between %(year_start)s and %(year_end)s"
            params["year_start"] = fy_row.get("year_start_date")
            params["year_end"] = fy_row.get("year_end_date")

    branch_filter = ""
    project_filter = ""
    if getattr(dims, "branch", None):
        branch_filter = "and branch = %(branch)s"
        params["branch"] = dims.branch
    if getattr(dims, "project", None):
        project_filter = "and project = %(project)s"
        params["project"] = dims.project

    sql = f"""
        select coalesce(sum(debit) - sum(credit), 0) as balance
        from `tabGL Entry`
        where company = %(company)s
          and account = %(account)s
          and cost_center = %(cost_center)s
          {fiscal_filters}
          {branch_filter}
          {project_filter}
          and is_cancelled = 0
    """
    try:
        result = frappe.db.sql(sql, params, as_dict=True)
        return float(result[0].get("balance") or 0.0) if result else 0.0
    except Exception:
        return 0.0


def apply_budget_allocation_delta(dims: Dimensions, delta_amount: float, *, allow_row_creation: bool = True):
    budget_name = _find_budget_for_dims(dims)
    if not budget_name:
        frappe.throw(
            _(
                "No ERPNext Budget found for Company {company}, Fiscal Year {fy}, Cost Center {cc}. Please create a Budget before applying allocations."
            ).format(company=dims.company or _("(unknown)"), fy=dims.fiscal_year or _("(unknown)"), cc=dims.cost_center or _("(unknown)"))
        )

    try:
        budget_doc = frappe.get_doc("Budget", budget_name)
    except Exception as exc:
        frappe.throw(
            _("Unable to load Budget {0}: {1}").format(budget_name, exc),
            title=_("Budget Not Found"),
        )

    existing = None
    for row in getattr(budget_doc, "accounts", []) or []:
        if getattr(row, "account", None) == dims.account:
            existing = row
            break

    if existing:
        current = getattr(existing, "budget_amount", 0) or 0
        try:
            existing.budget_amount = float(current) + float(delta_amount or 0)
        except Exception:
            existing.budget_amount = current
    elif allow_row_creation:
        try:
            budget_doc.append(
                "accounts",
                {
                    "account": dims.account,
                    "budget_amount": float(delta_amount or 0),
                },
            )
        except Exception as exc:
            frappe.throw(
                _("Unable to append Budget Account row: {0}").format(exc),
                title=_("Budget Update Failed"),
            )
    else:
        frappe.throw(
            _(
                "No Budget Account row found for account {0}. Please add the account to the Budget before applying allocation changes."
            ).format(dims.account)
        )

    try:
        budget_doc.save(ignore_permissions=True)
    except Exception as exc:
        frappe.throw(
            _("Failed to update Budget {0}: {1}").format(budget_name, exc),
            title=_("Budget Update Failed"),
        )
