# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

try:
    from frappe.model.document import Document
except Exception:  # pragma: no cover - fallback for test stubs
    class Document:  # type: ignore
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


class InternalChargeLine(Document):
    """Child table capturing per-cost-center approvals for internal charge."""

    def validate(self):
        if not getattr(self, "expense_account", None):
            frappe.throw(_("Expense Account is required."))
        
        if getattr(self, "amount", 0) is None or float(self.amount) <= 0:
            frappe.throw(_("Line amount must be greater than zero."))
