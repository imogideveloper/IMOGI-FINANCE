# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from imogi_finance import roles
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from imogi_finance.api.payroll_sync import get_bpjs_total
from imogi_finance.tax_operations import (
    _get_period_bounds,
    compute_tax_totals,
    create_tax_payment_journal_entry as build_tax_payment_journal_entry,
    create_tax_payment_entry as build_payment_entry,
)


class TaxPaymentBatch(Document):
    """Collects tax liabilities for a period and builds native Journal Entry drafts."""

    def validate(self):
        self._set_period_dates()
        self._ensure_tax_profile()
        self._ensure_status()
        self._ensure_payable_account()
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

    def _ensure_status(self):
        if not self.status:
            self.status = "Draft"

    def _ensure_payable_account(self):
        if self.payable_account or not self.tax_profile:
            return

        profile = frappe.get_cached_doc("Tax Profile", self.tax_profile)
        if self.tax_type == "PPN" and profile.get("ppn_payable_account"):
            self.payable_account = profile.ppn_payable_account
        elif self.tax_type == "PB1" and profile.get("pb1_payable_account"):
            self.payable_account = profile.pb1_payable_account
        elif self.tax_type == "BPJS" and profile.get("bpjs_payable_account"):
            self.payable_account = profile.bpjs_payable_account
        elif self.tax_type == "PPh" and self.pph_type:
            for row in profile.get("pph_accounts", []) or []:
                if row.pph_type == self.pph_type and row.payable_account:
                    self.payable_account = row.payable_account
                    break

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
        elif self.tax_type == "BPJS":
            self.amount = flt(get_bpjs_total(self.company, self.date_from, self.date_to))

        if self.amount and self.amount < 0:
            self.amount = 0

    def create_journal_entry(self):
        frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
        if not self.posting_date:
            self.posting_date = nowdate()
        return build_tax_payment_journal_entry(self)

    def create_payment_entry(self):
        frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
        if not self.payment_date:
            self.payment_date = nowdate()
        return build_payment_entry(self)


@frappe.whitelist()
def refresh_tax_payment_amount(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    batch.pull_amounts()
    batch.save(ignore_permissions=True)
    return batch.amount


@frappe.whitelist()
def create_tax_payment_entry(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    je_name = batch.create_payment_entry()
    batch.save(ignore_permissions=True)
    return je_name


@frappe.whitelist()
def create_tax_payment_journal_entry(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    je_name = batch.create_journal_entry()
    batch.save(ignore_permissions=True)
    return je_name
