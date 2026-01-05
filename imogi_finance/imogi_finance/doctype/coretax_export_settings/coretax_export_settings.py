# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance import tax_operations


class CoretaxExportSettings(Document):
    """Configurable column mappings for CoreTax exports."""

    def validate(self):
        if not self.column_mappings:
            frappe.throw(_("Add at least one column mapping for CoreTax Export Settings."))

        if self.direction not in {"Input", "Output"}:
            frappe.throw(_("Direction must be either Input or Output."))

        tax_operations.validate_coretax_required_mappings(self)
