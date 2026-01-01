# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imogi_finance.tax_operations import (
    _get_period_bounds,
    build_register_snapshot,
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
