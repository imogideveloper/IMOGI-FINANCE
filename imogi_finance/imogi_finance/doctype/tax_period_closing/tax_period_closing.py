# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from imogi_finance.tax_operations import (
    _get_period_bounds,
    build_register_snapshot,
    create_vat_netting_entry,
    generate_coretax_export,
)


class TaxPeriodClosing(Document):
    """Monthly tax closing that locks faktur pajak edits and tracks exports."""

    def validate(self):
        self._set_period_dates()
        self._ensure_status_default()
        self._ensure_tax_profile()

    def before_submit(self):
        self.status = "Closed"
        if not self.register_snapshot:
            self.generate_snapshot()
        self._update_totals_from_snapshot()

    def _ensure_status_default(self):
        if not self.status:
            self.status = "Draft"

    def _set_period_dates(self):
        if not self.period_month or not self.period_year:
            return

        date_from, date_to = _get_period_bounds(int(self.period_month), int(self.period_year))
        self.date_from = date_from
        self.date_to = date_to

    def _ensure_tax_profile(self):
        if self.tax_profile:
            return

        if not self.company:
            return

        profile = frappe.db.get_value("Tax Profile", {"company": self.company})
        if profile:
            self.tax_profile = profile

    def generate_snapshot(self, save: bool = True):
        if not self.company:
            frappe.throw(_("Company is required before generating tax register snapshots."))

        snapshot = build_register_snapshot(self.company, self.date_from, self.date_to)
        self.register_snapshot = json.dumps(snapshot, indent=2)
        self._update_totals_from_snapshot()

        if save:
            self.save(ignore_permissions=True)
        return snapshot

    def _update_totals_from_snapshot(self):
        if not self.register_snapshot:
            return

        try:
            data = json.loads(self.register_snapshot)
        except Exception:
            data = {}

        self.input_vat_total = flt(data.get("input_vat_total"))
        self.output_vat_total = flt(data.get("output_vat_total"))
        self.vat_net = flt(data.get("vat_net"))
        self.pph_total = flt(data.get("pph_total"))
        self.pb1_total = flt(data.get("pb1_total"))

    def generate_exports(self, save: bool = True):
        if not self.tax_profile:
            self._ensure_tax_profile()

        if self.coretax_settings_input:
            self.coretax_input_export = generate_coretax_export(
                company=self.company,
                date_from=self.date_from,
                date_to=self.date_to,
                direction="Input",
                settings_name=self.coretax_settings_input,
                filename=f"coretax-input-{self.company}-{self.period_year}-{self.period_month}",
            )

        if self.coretax_settings_output:
            self.coretax_output_export = generate_coretax_export(
                company=self.company,
                date_from=self.date_from,
                date_to=self.date_to,
                direction="Output",
                settings_name=self.coretax_settings_output,
                filename=f"coretax-output-{self.company}-{self.period_year}-{self.period_month}",
            )

        if save:
            self.save(ignore_permissions=True)

        return {
            "input_export": self.coretax_input_export,
            "output_export": self.coretax_output_export,
        }

    def _get_tax_profile_doc(self):
        if not self.tax_profile:
            self._ensure_tax_profile()
        if not self.tax_profile:
            frappe.throw(_("Tax Profile is required to create VAT Netting Journal Entry."))
        return frappe.get_cached_doc("Tax Profile", self.tax_profile)

    def create_vat_netting_journal_entry(self, save: bool = True) -> str:
        frappe.only_for(("System Manager", "Accounts Manager", "Tax Reviewer"))
        profile = self._get_tax_profile_doc()

        if not self.input_vat_total and not self.output_vat_total:
            self._update_totals_from_snapshot()

        payable_account = self.netting_payable_account or profile.get("ppn_payable_account")
        input_account = profile.get("ppn_input_account")
        output_account = profile.get("ppn_output_account")

        if not (input_account and output_account and payable_account):
            frappe.throw(
                _("Please set PPN Input, PPN Output, and PPN Payable accounts on Tax Profile or this closing.")
            )

        posting_date = self.netting_posting_date or self.date_to or nowdate()

        je_name = create_vat_netting_entry(
            company=self.company,
            period_month=int(self.period_month),
            period_year=int(self.period_year),
            input_vat_total=self.input_vat_total or 0,
            output_vat_total=self.output_vat_total or 0,
            input_account=input_account,
            output_account=output_account,
            payable_account=payable_account,
            posting_date=posting_date,
            reference=self.name,
        )

        self.vat_netting_journal_entry = je_name
        self.netting_posting_date = posting_date

        if save:
            self.save(ignore_permissions=True)

        return je_name


@frappe.whitelist()
def refresh_tax_registers(closing_name: str):
    closing = frappe.get_doc("Tax Period Closing", closing_name)
    frappe.only_for(("System Manager", "Accounts Manager", "Tax Reviewer"))
    return closing.generate_snapshot()


@frappe.whitelist()
def generate_coretax_exports(closing_name: str):
    closing = frappe.get_doc("Tax Period Closing", closing_name)
    frappe.only_for(("System Manager", "Accounts Manager", "Tax Reviewer"))
    return closing.generate_exports()


@frappe.whitelist()
def create_vat_netting_entry_for_closing(closing_name: str):
    closing = frappe.get_doc("Tax Period Closing", closing_name)
    frappe.only_for(("System Manager", "Accounts Manager", "Tax Reviewer"))
    return closing.create_vat_netting_journal_entry()
