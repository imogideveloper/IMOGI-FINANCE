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

    request = get_approved_expense_request(request, _("Payment Entry"))

    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry:
        frappe.throw(
            _("Expense Request already linked to Payment Entry {0}").format(
                linked_payment_entry
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
