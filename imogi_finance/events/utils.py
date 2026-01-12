from __future__ import annotations

import frappe
from frappe import _


EXPENSE_REQUEST_LINK_FIELDS = (
    "linked_payment_entry",
    "linked_purchase_invoice",
    "linked_asset",
)
EXPENSE_REQUEST_PENDING_FIELDS = ("pending_purchase_invoice",)


def get_approved_expense_request(
    request_name: str, target_label: str, allowed_statuses: frozenset[str] | set[str] | None = None
):
    request = frappe.get_doc("Expense Request", request_name)
    allowed_statuses = allowed_statuses or {"Approved", "PI Created"}
    if request.docstatus != 1 or request.status not in allowed_statuses:
        frappe.throw(
            _(
                "Expense Request must have docstatus 1 and status {0} before linking to {1}"
            ).format(", ".join(sorted(allowed_statuses)), target_label)
        )
    return request


def get_expense_request_links(request_name: str, *, include_pending: bool = False):
    fields = EXPENSE_REQUEST_LINK_FIELDS + (EXPENSE_REQUEST_PENDING_FIELDS if include_pending else ())
    return frappe.db.get_value(
        "Expense Request", request_name, fields, as_dict=True
    ) or {}


def has_active_links(request_links, exclude: frozenset[str] | None = None):
    excluded_links = exclude or frozenset()
    return any(
        request_links.get(field)
        for field in EXPENSE_REQUEST_LINK_FIELDS
        if field not in excluded_links
    )


def get_expense_request_status(request_links: dict, *, check_pi_docstatus: bool = False) -> str:
    """Determine Expense Request status based on linked documents.
    
    Args:
        request_links: Dict with linked_payment_entry, linked_purchase_invoice, linked_asset
        check_pi_docstatus: If True, verify PI is submitted before returning PI Created
    """
    if request_links.get("linked_payment_entry"):
        return "Paid"
    
    linked_pi = request_links.get("linked_purchase_invoice")
    linked_asset = request_links.get("linked_asset")
    
    if linked_pi and check_pi_docstatus:
        # Only return PI Created if PI is actually submitted
        import frappe
        pi_docstatus = frappe.db.get_value("Purchase Invoice", linked_pi, "docstatus")
        if pi_docstatus == 1:
            return "PI Created"
        # PI is draft or cancelled - status should be Approved
        return "Approved"
    
    if linked_pi or linked_asset:
        return "PI Created"
    
    return "Approved"


def get_cancel_updates(request_name: str, cleared_link_field: str, *, include_pending: bool = False):
    request_links = get_expense_request_links(request_name, include_pending=include_pending)
    remaining_links = {field: request_links.get(field) for field in request_links if field != cleared_link_field}
    next_status = get_expense_request_status(remaining_links)
    return {cleared_link_field: None, "status": next_status, "workflow_state": next_status}
