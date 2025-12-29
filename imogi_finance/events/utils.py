from __future__ import annotations

import frappe
from frappe import _


def get_approved_expense_request(request_name: str, target_label: str):
    request = frappe.get_doc("Expense Request", request_name)
    if request.docstatus != 1 or request.status != "Approved":
        frappe.throw(
            _("Expense Request must be Approved before linking to {0}").format(target_label)
        )
    return request
