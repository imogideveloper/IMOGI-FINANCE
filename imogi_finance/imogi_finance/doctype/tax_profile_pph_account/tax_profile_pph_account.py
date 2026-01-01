# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class TaxProfilePphAccount(Document):
    """Child table to map PPh types to payable accounts."""

    def validate(self):
        if not self.pph_type:
            frappe.throw(frappe._("PPh Type is required for each mapping row."))

        if not self.payable_account:
            frappe.throw(frappe._("Please set a payable account for PPh type {0}.").format(self.pph_type))
