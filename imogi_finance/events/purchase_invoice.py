import frappe


def on_submit(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    frappe.db.set_value(
        "Expense Request",
        request,
        {"linked_purchase_invoice": doc.name, "status": "Linked"},
    )
