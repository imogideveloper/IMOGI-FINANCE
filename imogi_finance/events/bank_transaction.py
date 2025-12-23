from __future__ import annotations

import frappe
from frappe import _


def before_cancel(doc, *_):
    if doc.status == "Unreconciled":
        frappe.throw(_("Unreconciled Bank Transactions cannot be cancelled."))
