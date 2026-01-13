# Developer scan notes (2024-11-05):
# - Expense Request controller (imogi_finance/imogi_finance/doctype/expense_request/expense_request.py)
#   drives approval via imogi_finance.approval.get_approval_route/get_active_setting_meta with guards
#   in before_workflow_action and purchase invoice creation through imogi_finance.accounting.create_purchase_invoice_from_request.
# - Approval engine is centralized in imogi_finance.approval with Expense Approval Setting/Line doctypes.
# - Branch propagation uses imogi_finance.branching.resolve_branch/apply_branch and is enforced in events
#   such as imogi_finance.events.purchase_invoice and ExpenseRequest.apply_branch_defaults.
# - No existing budget-control or internal-charge doctypes/ledgers; accounting utilities are limited to
#   summarize_request_items and downstream link validation in imogi_finance.events.utils.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from imogi_finance import roles
from frappe import _

DEFAULT_SETTINGS = {
    "enable_budget_lock": 0,
    "enable_budget_reclass": 0,
    "enable_additional_budget": 0,
    "enable_internal_charge": 0,
    "budget_controller_role": roles.BUDGET_CONTROLLER,
    "require_budget_controller_review": 1,
    "lock_on_workflow_state": "Approved",
    "enforce_mode": "Both",
    "allow_budget_overrun_role": None,
    "allow_reclass_override_role": None,
    "internal_charge_required_before_er_approval": 1,
    "internal_charge_posting_mode": "Auto JE on PI Submit",
    "dimension_mode": "Native (Cost Center + Account)",
}


@dataclass
class Dimensions:
    company: str | None
    fiscal_year: str | None
    cost_center: str | None
    account: str | None
    project: str | None = None
    branch: str | None = None

    def as_filters(self) -> dict[str, Any]:
        filters = {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "cost_center": self.cost_center,
            "account": self.account,
        }

        if self.project:
            filters["project"] = self.project

        if self.branch:
            filters["branch"] = self.branch

        return filters


def _get_settings_doc():
    try:
        return frappe.get_cached_doc("Budget Control Settings")
    except Exception:
        try:
            return frappe.get_single("Budget Control Settings")
        except Exception:
            return None


def get_settings():
    settings = DEFAULT_SETTINGS.copy()
    if not getattr(frappe, "db", None):
        return settings

    if not frappe.db.exists("DocType", "Budget Control Settings"):
        return settings

    record = _get_settings_doc()
    if not record:
        return settings

    for key in settings.keys():
        settings[key] = getattr(record, key, settings[key])

    return settings


def is_feature_enabled(flag: str) -> bool:
    settings = get_settings()
    return bool(settings.get(flag, 0))


def resolve_company_from_cost_center(cost_center: str | None) -> str | None:
    if not cost_center or not getattr(frappe, "db", None):
        return None

    try:
        return frappe.db.get_value("Cost Center", cost_center, "company")
    except Exception:
        return None


def resolve_fiscal_year(fiscal_year: str | None) -> str | None:
    if fiscal_year:
        return fiscal_year

    defaults = getattr(frappe, "defaults", None)
    if defaults and hasattr(defaults, "get_user_default"):
        try:
            value = defaults.get_user_default("fiscal_year")
            if value:
                return value
        except Exception:
            pass

    if defaults and hasattr(defaults, "get_global_default"):
        try:
            value = defaults.get_global_default("fiscal_year")
            if value:
                return value
        except Exception:
            pass

    if getattr(frappe, "db", None):
        try:
            value = frappe.db.get_single_value("System Settings", "fiscal_year")
            if value:
                return value
        except Exception:
            pass

        try:
            value = frappe.db.get_single_value("System Settings", "current_fiscal_year")
            if value:
                return value
        except Exception:
            pass

    return None


def allow_branch(dim_mode: str) -> bool:
    return dim_mode in ("Native + Branch (optional)",)


def allow_project(dim_mode: str) -> bool:
    return dim_mode in ("Native + Project (optional)",)
