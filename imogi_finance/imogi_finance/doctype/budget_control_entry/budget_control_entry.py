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


class BudgetControlEntry(Document):
    """Ledger record for budget reservations and allocation deltas."""

    VALID_ENTRY_TYPES = {"RESERVATION", "CONSUMPTION", "RELEASE", "RECLASS", "SUPPLEMENT", "REVERSAL"}
    VALID_DIRECTIONS = {"IN", "OUT"}

    def validate(self):
        if getattr(self, "amount", 0) is None or float(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero."))

        if getattr(self, "entry_type", None) not in self.VALID_ENTRY_TYPES:
            frappe.throw(_("Entry Type must be one of: {0}").format(", ".join(sorted(self.VALID_ENTRY_TYPES))))

        if getattr(self, "direction", None) not in self.VALID_DIRECTIONS:
            frappe.throw(_("Direction must be IN or OUT."))
