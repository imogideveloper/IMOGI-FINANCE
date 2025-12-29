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
        "Expense Request", request, ["linked_payment_entry"], as_dict=True
    )
    updates = {"linked_asset": None}

    if not request_info or not request_info.linked_payment_entry:
        updates["status"] = "Approved"

    frappe.db.set_value(
        "Expense Request",
        request,
        updates,
    )
