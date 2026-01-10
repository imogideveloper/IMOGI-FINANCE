"""Approval helpers for IMOGI Finance."""

from __future__ import annotations

import json
from collections.abc import Iterable

import frappe
from frappe import _
from frappe.utils import flt


def _normalize_accounts(accounts: str | Iterable[str]) -> tuple[str, ...]:
    """Normalize accounts to tuple."""
    if isinstance(accounts, str):
        return (accounts,)

    if isinstance(accounts, Iterable):
        normalized = tuple(sorted({account for account in accounts if account}))
        if normalized:
            return normalized

    return ()


def get_active_setting_meta(cost_center: str) -> dict | None:
    """Return active approval setting metadata, or None if not found."""
    if not cost_center:
        return None
        
    setting = frappe.db.get_value(
        "Expense Approval Setting",
        {"cost_center": cost_center, "is_active": 1},
        ["name", "modified"],
        as_dict=True,
    )
    
    if not setting:
        return None

    if isinstance(setting, str):
        return {"name": setting, "modified": None}

    return setting


def _empty_route() -> dict:
    """Return empty route for auto-approve scenarios."""
    return {
        "level_1": {"role": None, "user": None},
        "level_2": {"role": None, "user": None},
        "level_3": {"role": None, "user": None},
    }


def _get_route_for_account(setting_name: str, account: str, amount: float) -> dict | None:
    """Get approval route for a specific account.
    
    Matches by expense_account first, falls back to is_default.
    Then filters levels by amount range.
    """
    # Try to find specific account line
    approval_line = frappe.get_all(
        "Expense Approval Line",
        filters={
            "parent": setting_name,
            "expense_account": account,
        },
        fields=[
            "level_1_role", "level_1_user", "level_1_min_amount", "level_1_max_amount",
            "level_2_role", "level_2_user", "level_2_min_amount", "level_2_max_amount",
            "level_3_role", "level_3_user", "level_3_min_amount", "level_3_max_amount",
        ],
        limit=1,
    )

    # Fall back to default line
    if not approval_line:
        approval_line = frappe.get_all(
            "Expense Approval Line",
            filters={
                "parent": setting_name,
                "is_default": 1,
            },
            fields=[
                "level_1_role", "level_1_user", "level_1_min_amount", "level_1_max_amount",
                "level_2_role", "level_2_user", "level_2_min_amount", "level_2_max_amount",
                "level_3_role", "level_3_user", "level_3_min_amount", "level_3_max_amount",
            ],
            limit=1,
        )

    if not approval_line:
        return None

    data = approval_line[0]
    route = {
        "level_1": {"role": None, "user": None},
        "level_2": {"role": None, "user": None},
        "level_3": {"role": None, "user": None},
    }

    # Filter each level by amount range
    for level in (1, 2, 3):
        role = data.get(f"level_{level}_role")
        user = data.get(f"level_{level}_user")
        min_amount = data.get(f"level_{level}_min_amount")
        max_amount = data.get(f"level_{level}_max_amount")

        # Skip if no approver configured for this level
        if not role and not user:
            continue

        # Skip if amount range not configured
        if min_amount is None or max_amount is None:
            continue

        min_amount = flt(min_amount)
        max_amount = flt(max_amount)

        # Check if amount falls within this level's range
        if min_amount <= amount <= max_amount:
            route[f"level_{level}"] = {"role": role, "user": user}

    return route


def get_approval_route(
    cost_center: str, accounts: str | Iterable[str], amount: float, *, setting_meta: dict | None = None
) -> dict:
    """Return approval route based on cost center, account(s) and amount.
    
    Returns empty route (for auto-approve) if no setting exists or no matching rules.
    """
    amount = flt(amount or 0)
    
    # Normalize accounts
    try:
        normalized_accounts = _normalize_accounts(accounts)
    except Exception:
        normalized_accounts = ()
    
    if not normalized_accounts:
        return _empty_route()
    
    # Get setting
    try:
        route_setting = setting_meta if setting_meta is not None else get_active_setting_meta(cost_center)
    except Exception:
        route_setting = None
        
    if not route_setting:
        return _empty_route()
    
    setting_name = route_setting.get("name") if isinstance(route_setting, dict) else None
    if not setting_name:
        return _empty_route()
    
    resolved_route = None

    for account in normalized_accounts:
        route = _get_route_for_account(setting_name, account, amount)
        
        if route is None:
            continue

        if resolved_route is None:
            resolved_route = route
            continue

        # Check route consistency across accounts
        if resolved_route != route:
            raise frappe.ValidationError(
                _("All expense accounts on the request must share the same approval route.")
            )

    if not resolved_route:
        return _empty_route()

    return resolved_route


def approval_setting_required_message(cost_center: str | None = None) -> str:
    """Return user-friendly message when approval setting is missing."""
    if cost_center:
        return _(
            "Approval route could not be determined. Please configure an Expense Approval Setting for Cost Center {0}."
        ).format(cost_center)

    return _("Approval route could not be determined. Please configure an Expense Approval Setting.")


def log_route_resolution_error(exc: Exception, *, cost_center: str | None = None, accounts=None, amount=None):
    """Log approval route resolution errors."""
    logger = getattr(frappe, "log_error", None)
    if logger:
        try:
            logger(
                title=_("Expense Request Approval Route Resolution Failed"),
                message={
                    "cost_center": cost_center,
                    "accounts": accounts,
                    "amount": amount,
                    "error": repr(exc),
                },
            )
        except Exception:
            pass


@frappe.whitelist()
def check_expense_request_route(
    cost_center: str,
    items=None,
    expense_accounts=None,
    amount: float | None = None,
    docstatus: int | None = None,
):
    """API to check approval route for expense request."""
    parsed_items = json.loads(items) if isinstance(items, str) else items
    parsed_accounts = json.loads(expense_accounts) if isinstance(expense_accounts, str) else expense_accounts

    if not parsed_items and not parsed_accounts:
        return {
            "ok": False,
            "message": _("Please add expense items or accounts before checking the approval route."),
        }

    total = amount
    if parsed_items and not parsed_accounts:
        total, parsed_accounts = frappe.get_module("imogi_finance.accounting").summarize_request_items(
            parsed_items,
            skip_invalid_items=True,
        )

    if not parsed_accounts:
        return {
            "ok": False,
            "message": _("Please add expense accounts before checking the approval route."),
        }

    target_amount = amount if amount is not None else total

    route = get_approval_route(cost_center, parsed_accounts or [], target_amount or 0)
    
    # Check if route has any approvers
    has_approvers = any([
        route.get("level_1", {}).get("role"),
        route.get("level_1", {}).get("user"),
        route.get("level_2", {}).get("role"),
        route.get("level_2", {}).get("user"),
        route.get("level_3", {}).get("role"),
        route.get("level_3", {}).get("user"),
    ])
    
    if not has_approvers:
        return {
            "ok": True,
            "route": route,
            "message": _("No approval required. Request will be auto-approved."),
            "auto_approve": True,
        }
    
    return {"ok": True, "route": route, "auto_approve": False}