# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from imogi_finance.tax_operations import (
    _get_period_bounds,
    compute_tax_totals,
    create_tax_payment_journal_entry,
)


class TaxPaymentBatch(Document):
    """Collects tax liabilities for a period and builds native Journal Entry drafts."""

    def validate(self):
        self._set_period_dates()
        self._ensure_tax_profile()
        self._refresh_amount_if_needed()

    def _set_period_dates(self):
        if not self.period_month or not self.period_year:
            return

        date_from, date_to = _get_period_bounds(int(self.period_month), int(self.period_year))
        self.date_from = date_from
        self.date_to = date_to

    def _ensure_tax_profile(self):
        if self.tax_profile or not self.company:
            return
        profile = frappe.db.get_value("Tax Profile", {"company": self.company})
        if profile:
            self.tax_profile = profile

    def _refresh_amount_if_needed(self):
        if self.amount:
            return
        self.pull_amounts()

    def pull_amounts(self):
        totals = None
        if self.source_closing:
            closing = frappe.get_doc("Tax Period Closing", self.source_closing)
            closing._update_totals_from_snapshot()
            totals = {
                "input_vat_total": closing.input_vat_total,
                "output_vat_total": closing.output_vat_total,
                "vat_net": closing.vat_net,
                "pph_total": closing.pph_total,
                "pb1_total": closing.pb1_total,
            }
        else:
            totals = compute_tax_totals(self.company, self.date_from, self.date_to)

        if self.tax_type == "PPN":
            self.amount = flt(totals.get("vat_net"))
        elif self.tax_type == "PPh":
            self.amount = flt(totals.get("pph_total"))
        elif self.tax_type == "PB1":
            self.amount = flt(totals.get("pb1_total"))

        if self.amount and self.amount < 0:
            self.amount = 0

    def create_journal_entry(self):
        frappe.only_for(("Accounts Manager", "System Manager"))
        if not self.posting_date:
            self.posting_date = nowdate()
        return create_tax_payment_journal_entry(self)


@frappe.whitelist()
def refresh_tax_payment_amount(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for(("Accounts Manager", "System Manager"))
    batch.pull_amounts()
    batch.save(ignore_permissions=True)
    return batch.amount


@frappe.whitelist()
def create_tax_payment_entry(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for(("Accounts Manager", "System Manager"))
    je_name = batch.create_journal_entry()
    batch.save(ignore_permissions=True)
    return je_name
