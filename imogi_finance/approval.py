"""Approval helpers for IMOGI Finance."""

from __future__ import annotations

import json
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


def get_active_setting_meta(cost_center: str) -> dict:
    setting = frappe.db.get_value(
        "Expense Approval Setting",
        {"cost_center": cost_center, "is_active": 1},
        ["name", "modified"],
        as_dict=True,
    )
    if not setting:
        raise frappe.DoesNotExistError(
            _("No active Expense Approval Setting found for Cost Center {0}").format(cost_center)
        )

    if isinstance(setting, str):
        return {"name": setting, "modified": None}

    return setting


def _normalize_route(route: dict) -> dict:
    normalized = dict(route)
    normalized["level_3"] = {"role": None, "user": None}
    return normalized


def _get_route_for_account(setting_name: str, account: str, amount: float) -> dict:
    def _get_matching_line(filters: dict):
        return frappe.get_all(
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

    filters = {
        "parent": setting_name,
        "expense_account": account,
        "min_amount": ["<=", amount],
        "max_amount": [">=", amount],
    }
    approval_line = _get_matching_line(filters)

    if not approval_line:
        approval_line = _get_matching_line(
            {
                "parent": setting_name,
                "is_default": 1,
                "min_amount": ["<=", amount],
                "max_amount": [">=", amount],
            }
        )

    if not approval_line:
        raise frappe.ValidationError(
            _("No approval rule matches account {0} and amount {1}".format(account, amount))
        )

    data = approval_line[0]
    return _normalize_route(
        {
            "level_1": {"role": data.get("level_1_role"), "user": data.get("level_1_user")},
            "level_2": {"role": data.get("level_2_role"), "user": data.get("level_2_user")},
            "level_3": {"role": data.get("level_3_role"), "user": data.get("level_3_user")},
        }
    )


def get_approval_route(
    cost_center: str, accounts: str | Iterable[str], amount: float, *, setting_meta: dict | None = None
) -> dict:
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
    route_setting = setting_meta or get_active_setting_meta(cost_center)
    setting_name = route_setting.get("name") if isinstance(route_setting, dict) else None
    if not setting_name:
        raise frappe.DoesNotExistError(
            _("No active Expense Approval Setting found for Cost Center {0}").format(cost_center)
        )
    resolved_route = None

    for account in normalized_accounts:
        route = _get_route_for_account(setting_name, account, amount)

        if resolved_route is None:
            resolved_route = route
            continue

        if resolved_route != route:
            raise frappe.ValidationError(
                _("All expense accounts on the request must share the same approval route.")
            )

    return _normalize_route(resolved_route) if resolved_route else {}


def approval_setting_required_message(cost_center: str | None = None) -> str:
    if cost_center:
        return _(
            "Approval route could not be determined. Please ask your System Manager to configure an Expense Approval Setting for Cost Center {0}."
        ).format(cost_center)

    return _(
        "Approval route could not be determined. Please ask your System Manager to configure an Expense Approval Setting."
    )


def log_route_resolution_error(exc: Exception, *, cost_center: str | None = None, accounts=None, amount=None):
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

    frappe_logger = getattr(frappe, "logger", None)
    if frappe_logger:
        try:
            frappe_logger("imogi_finance").warning(
                "Approval route resolution failed",
                extra={
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

    try:
        route = get_approval_route(cost_center, parsed_accounts or [], target_amount or 0)
        return {"ok": True, "route": route}
    except (frappe.DoesNotExistError, frappe.ValidationError) as exc:
        log_route_resolution_error(exc, cost_center=cost_center, accounts=parsed_accounts, amount=target_amount)
        if docstatus == 0:
            return {
                "ok": False,
                "message": _(
                    "Approval route could not be determined yet. Draft requests can still be edited; configure an Expense Approval Setting before submitting."
                ),
            }
        return {"ok": False, "message": approval_setting_required_message(cost_center)}
