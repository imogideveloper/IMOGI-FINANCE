import frappe


def on_submit(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    frappe.db.set_value(
        "Expense Request",
        request,
        {"linked_journal_entry": doc.name, "status": "Linked"},
    )


def on_cancel(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request_info = frappe.db.get_value(
        "Expense Request", request, ["linked_payment_entry"], as_dict=True
    )
    updates = {"linked_journal_entry": None}

    if not request_info or not request_info.linked_payment_entry:
        updates["status"] = "Approved"

    frappe.db.set_value(
        "Expense Request",
        request,
        updates,
    )
