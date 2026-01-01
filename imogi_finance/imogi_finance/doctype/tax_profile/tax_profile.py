# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TaxProfile(Document):
    """Stores tax liability accounts and export defaults per company."""

    def autoname(self):
        if self.company:
            self.name = self.company

    def validate(self):
        self._validate_unique_company()
        self._validate_accounts()

    def _validate_unique_company(self):
        if not self.company:
            frappe.throw(_("Company is required."))

        existing = frappe.db.exists("Tax Profile", {"company": self.company, "name": ["!=", self.name]})
        if existing:
            frappe.throw(
                _("A Tax Profile already exists for company {0} ({1}).").format(self.company, existing),
                title=_("Duplicate Tax Profile"),
            )

    def _validate_accounts(self):
        accounts = [
            acct
            for acct in [
                self.ppn_input_account,
                self.ppn_output_account,
                self.pb1_payable_account,
                *(row.payable_account for row in self.pph_accounts or [] if row.payable_account),
            ]
            if acct
        ]

        duplicates = {acc for acc in accounts if accounts.count(acc) > 1}
        if duplicates:
            frappe.throw(
                _("The same account is referenced multiple times: {0}. Please review the Tax Profile.").format(
                    ", ".join(sorted(set(duplicates)))
                )
            )
