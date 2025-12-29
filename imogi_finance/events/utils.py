from __future__ import annotations

import frappe
from frappe import _


EXPENSE_REQUEST_LINK_FIELDS = (
    "linked_payment_entry",
    "linked_purchase_invoice",
    "linked_asset",
)


def get_approved_expense_request(
    request_name: str, target_label: str, allowed_statuses: frozenset[str] | set[str] | None = None
):
    request = frappe.get_doc("Expense Request", request_name)
    allowed_statuses = allowed_statuses or {"Approved", "Linked"}
    if request.docstatus != 1 or request.status not in allowed_statuses:
        frappe.throw(
            _(
                "Expense Request must have docstatus 1 and status {0} before linking to {1}"
            ).format(", ".join(sorted(allowed_statuses)), target_label)
        )
    return request


def get_expense_request_links(request_name: str):
    return frappe.db.get_value(
        "Expense Request", request_name, EXPENSE_REQUEST_LINK_FIELDS, as_dict=True
    ) or {}


def has_active_links(request_links, exclude: frozenset[str] | None = None):
    excluded_links = exclude or frozenset()
    return any(
        request_links.get(field)
        for field in EXPENSE_REQUEST_LINK_FIELDS
        if field not in excluded_links
    )


def get_cancel_updates(request_name: str, cleared_link_field: str):
    request_links = get_expense_request_links(request_name)
    remaining_links = has_active_links(
        request_links, exclude=frozenset({cleared_link_field})
    )

    return {
        cleared_link_field: None,
        "status": "Linked" if remaining_links else "Approved",
    }
