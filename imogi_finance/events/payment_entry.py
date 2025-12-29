import frappe
from frappe import _

from imogi_finance.events.utils import get_approved_expense_request


def on_submit(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request = get_approved_expense_request(request, _("Payment Entry"))

    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"linked_payment_entry": doc.name, "status": "Closed"},
    )


def on_cancel(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request_links = frappe.db.get_value(
        "Expense Request",
        request,
        ["linked_purchase_invoice", "linked_journal_entry", "linked_asset"],
        as_dict=True,
    )

    new_status = "Approved"
    if request_links and (
        request_links.linked_purchase_invoice
        or request_links.linked_journal_entry
        or request_links.linked_asset
    ):
        new_status = "Linked"

    frappe.db.set_value(
        "Expense Request",
        request,
        {"linked_payment_entry": None, "status": new_status},
    )
