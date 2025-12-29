"""Approval helpers for IMOGI Finance."""

from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _


def _normalize_accounts(accounts: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(accounts, str):
        return (accounts,)

    if isinstance(accounts, Iterable):
        normalized = tuple(sorted({account for account in accounts if account}))
        if normalized:
            return normalized

    raise frappe.ValidationError(_("At least one expense account is required for approval routing."))


def _get_route_for_account(cost_center: str, account: str, amount: float) -> dict:
    setting_name = frappe.db.get_value(
        "Expense Approval Setting", {"cost_center": cost_center, "is_active": 1}, "name"
    )
    if not setting_name:
        raise frappe.DoesNotExistError(
            _("No active Expense Approval Setting found for Cost Center {0}").format(cost_center)
        )

    filters = {
        "parent": setting_name,
        "expense_account": account,
        "min_amount": ["<=", amount],
        "max_amount": [">=", amount],
    }
    approval_line = frappe.get_all(
        "Expense Approval Line",
        filters=filters,
        fields=[
            "level_1_role",
            "level_1_user",
            "level_2_role",
            "level_2_user",
            "level_3_role",
            "level_3_user",
        ],
        order_by="min_amount desc, max_amount asc",
        limit=1,
    )

    if not approval_line:
        raise frappe.ValidationError(
            _("No approval rule matches account {0} and amount {1}".format(account, amount))
        )

    data = approval_line[0]
    return {
        "level_1": {"role": data.get("level_1_role"), "user": data.get("level_1_user")},
        "level_2": {"role": data.get("level_2_role"), "user": data.get("level_2_user")},
        "level_3": {"role": data.get("level_3_role"), "user": data.get("level_3_user")},
    }


def get_approval_route(cost_center: str, accounts: str | Iterable[str], amount: float) -> dict:
    """Return approval route based on cost center, account(s) and amount.

    Args:
        cost_center: Target cost center for the request.
        accounts: Expense account(s) being charged.
        amount: Total requested amount.

    Returns:
        dict: Approval mapping per level, with ``role`` and ``user`` keys.

    Raises:
        frappe.DoesNotExistError: If no active rule exists for the cost center.
        frappe.ValidationError: If no approval line matches or routes differ per account.
    """

    normalized_accounts = _normalize_accounts(accounts)
    resolved_route = None

    for account in normalized_accounts:
        route = _get_route_for_account(cost_center, account, amount)

        if resolved_route is None:
            resolved_route = route
            continue

        if resolved_route != route:
            raise frappe.ValidationError(
                _("All expense accounts on the request must share the same approval route.")
            )

    return resolved_route or {}
