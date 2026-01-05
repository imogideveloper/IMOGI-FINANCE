# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
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
        self._require_core_accounts()
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

    def _require_core_accounts(self):
        missing = []
        if not getattr(self, "ppn_input_account", None):
            missing.append(_("PPN Input Account"))
        if not getattr(self, "ppn_output_account", None):
            missing.append(_("PPN Output Account"))
        if not getattr(self, "pb1_payable_account", None):
            missing.append(_("PB1 Payable Account"))
        if not getattr(self, "bpjs_payable_account", None):
            missing.append(_("BPJS Payable Account"))
        if not getattr(self, "pph_accounts", None):
            missing.append(_("Withholding Tax (PPh) payable accounts"))

        if missing:
            frappe.throw(
                _("Please complete the following on the Tax Profile for {0}: {1}.").format(
                    self.company or self.name, _(", ").join(missing)
                ),
                title=_("Incomplete Tax Profile"),
            )

    def _validate_accounts(self):
        accounts = [
            acct
            for acct in [
                self.ppn_input_account,
                self.ppn_output_account,
                self.pb1_payable_account,
                self.bpjs_payable_account,
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
