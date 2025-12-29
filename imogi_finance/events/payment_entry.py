import frappe
from frappe import _

from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
)


def on_submit(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request = get_approved_expense_request(
        request, _("Payment Entry"), allowed_statuses=frozenset({"Linked"})
    )

    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry:
        frappe.throw(
            _("Expense Request already linked to Payment Entry {0}").format(
                linked_payment_entry
            )
        )

    existing_payment_entry = frappe.db.exists(
        "Payment Entry",
        {"imogi_expense_request": request.name, "docstatus": ["!=", 2]},
    )
    if existing_payment_entry:
        frappe.throw(
            _("An active Payment Entry {0} already exists for Expense Request {1}").format(
                existing_payment_entry, request.name
            )
        )

    has_purchase_invoice = getattr(request, "linked_purchase_invoice", None)
    has_asset_link = request.request_type == "Asset" and getattr(
        request, "linked_asset", None
    )
    if has_purchase_invoice:
        pi_docstatus = frappe.db.get_value("Purchase Invoice", has_purchase_invoice, "docstatus")
        if pi_docstatus != 1:
            frappe.throw(
                _("Linked Purchase Invoice {0} must be submitted before creating Payment Entry.").format(
                    has_purchase_invoice
                )
            )
    if has_asset_link:
        asset_docstatus = frappe.db.get_value("Asset", has_asset_link, "docstatus")
        if asset_docstatus != 1:
            frappe.throw(
                _("Linked Asset {0} must be submitted before creating Payment Entry.").format(
                    has_asset_link
                )
            )
    if not has_purchase_invoice and not has_asset_link:
        frappe.throw(
            _(
                "Expense Request must be linked to a Purchase Invoice{0} before submitting Payment Entry."
            ).format(
                _(" or Asset") if request.request_type == "Asset" else ""
            )
        )

    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"linked_payment_entry": doc.name, "status": "Closed"},
    )


def on_cancel(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    updates = get_cancel_updates(request, "linked_payment_entry")

    frappe.db.set_value("Expense Request", request, updates)
