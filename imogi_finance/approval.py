"""Approval helpers for IMOGI Finance."""

from __future__ import annotations

import frappe
from frappe import _


def get_approval_route(cost_center: str, account: str, amount: float) -> dict:
    """Return approval route based on cost center, account and amount.

    Args:
        cost_center: Target cost center for the request.
        account: Expense account being charged.
        amount: Total requested amount.

    Returns:
        dict: Approval mapping per level, with ``role`` and ``user`` keys.

    Raises:
        frappe.DoesNotExistError: If no active rule exists for the cost center.
        frappe.ValidationError: If no approval line matches the account and amount.
    """

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
