# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TaxProfilePPhAccount(Document):
    """Child table to map PPh types to payable accounts.
    
    Used in Tax Profile to configure which accounts are used to record
    Indonesian Withholding Tax (PPh) by category.
    """

    def validate(self):
        """Validate PPh account mapping configuration."""
        self.validate_pph_type()
        self.validate_payable_account()
    
    def validate_pph_type(self):
        """Ensure PPh Type is specified."""
        if not self.pph_type:
            frappe.throw(
                _("PPh Type is required for each withholding tax mapping row")
            )
    
    def validate_payable_account(self):
        """Ensure payable account is specified and valid."""
        if not self.payable_account:
            frappe.throw(
                _("Payable Account is required for PPh Type {0}").format(
                    frappe.bold(self.pph_type)
                )
            )
        
        # Verify account exists and is valid
        account = frappe.db.get_value(
            "Account",
            self.payable_account,
            ["root_type", "is_group"],
            as_dict=1
        )
        if not account:
            frappe.throw(
                _("Payable Account {0} does not exist").format(
                    frappe.bold(self.payable_account)
                )
            )
