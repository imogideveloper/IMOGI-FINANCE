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

    updates = get_cancel_updates(request, "linked_asset")

    frappe.db.set_value("Expense Request", request, updates)
