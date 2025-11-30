# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ExpenseApprovalLine(Document):
    """Child table to capture approval limits for a cost center."""

    def validate(self):
        if self.min_amount is not None and self.max_amount is not None and self.min_amount > self.max_amount:
            frappe.throw("Minimum Amount cannot exceed Maximum Amount for an approval line.")
