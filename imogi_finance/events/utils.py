from __future__ import annotations

import frappe
from frappe import _


def get_approved_expense_request(request_name: str, target_label: str):
    request = frappe.get_doc("Expense Request", request_name)
    allowed_statuses = {"Approved", "Linked"}
    if request.docstatus != 1 or request.status not in allowed_statuses:
        frappe.throw(
            _(
                "Expense Request must have docstatus 1 and status {0} before linking to {1}"
            ).format(", ".join(sorted(allowed_statuses)), target_label)
        )
    return request
