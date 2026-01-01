# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CoretaxExportSettings(Document):
    """Configurable column mappings for CoreTax exports."""

    def validate(self):
        if not self.column_mappings:
            frappe.throw(_("Add at least one column mapping for CoreTax Export Settings."))

        if self.direction not in {"Input", "Output"}:
            frappe.throw(_("Direction must be either Input or Output."))
