import frappe
from frappe import _

from imogi_finance.events.utils import get_approved_expense_request


def on_submit(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request = get_approved_expense_request(request, _("Asset"))

    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"linked_asset": doc.name, "status": "Linked"},
    )


def on_cancel(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request_info = frappe.db.get_value(
        "Expense Request",
        request,
        ["linked_payment_entry", "linked_purchase_invoice"],
        as_dict=True,
    )
    has_active_links = request_info and (
        request_info.linked_payment_entry or request_info.linked_purchase_invoice
    )
    updates = {
        "linked_asset": None,
        "status": "Linked" if has_active_links else "Approved",
    }

    frappe.db.set_value(
        "Expense Request",
        request,
        updates,
    )
