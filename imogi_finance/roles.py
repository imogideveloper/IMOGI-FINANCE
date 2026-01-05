from __future__ import annotations

import frappe

SYSTEM_MANAGER = "System Manager"
ACCOUNTS_MANAGER = "Accounts Manager"
ACCOUNTS_USER = "Accounts User"
BUDGET_CONTROLLER = "Budget Controller"
EXPENSE_APPROVER = "Expense Approver"
RECEIPT_MAKER = "Receipt Maker"
RECEIPT_APPROVER = "Receipt Approver"
RECEIPT_AUDITOR = "Receipt Auditor"
TAX_REVIEWER = "Tax Reviewer"

TAX_PRIVILEGED_ROLES = {SYSTEM_MANAGER, TAX_REVIEWER}


def session_roles() -> set[str]:
    """Return the current session's roles as a set."""
    if not hasattr(frappe, "get_roles"):
        return set()

    try:
        return set(frappe.get_roles())
    except Exception:
        return set()


def has_any_role(*roles: str) -> bool:
    """Check if the current session has any of the given roles."""
    flattened = {role for role in roles if role}
    return bool(session_roles() & flattened)
