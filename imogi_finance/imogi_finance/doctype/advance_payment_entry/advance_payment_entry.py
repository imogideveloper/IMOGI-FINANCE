# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class AdvancePaymentEntry(Document):
    def validate(self):
        self._set_defaults()
        self._set_amounts()
        self._validate_allocations()
        self._update_status()

    def on_submit(self):
        self._update_status()

    def on_cancel(self):
        self.status = "Cancelled"

    def allocate_reference(
        self,
        invoice_doctype: str,
        invoice_name: str,
        allocated_amount: float,
        reference_currency: str | None = None,
        reference_exchange_rate: float | None = None,
    ) -> None:
        allocated_amount = flt(allocated_amount)
        if allocated_amount <= 0:
            frappe.throw(_("Allocated amount must be greater than zero."))

        if not invoice_doctype or not invoice_name:
            frappe.throw(_("Invoice reference is required to create an allocation."))

        existing_row = next(
            (
                row
                for row in self.references
                if row.invoice_doctype == invoice_doctype and row.invoice_name == invoice_name
            ),
            None,
        )

        if existing_row:
            existing_row.allocated_amount = flt(existing_row.allocated_amount) + allocated_amount
            if reference_currency:
                existing_row.reference_currency = reference_currency
            if reference_exchange_rate:
                existing_row.reference_exchange_rate = reference_exchange_rate
        else:
            self.append(
                "references",
                {
                    "invoice_doctype": invoice_doctype,
                    "invoice_name": invoice_name,
                    "allocated_amount": allocated_amount,
                    "reference_currency": reference_currency or self.currency,
                    "reference_exchange_rate": reference_exchange_rate or self.exchange_rate,
                },
            )

        self._set_amounts()
        self._validate_allocations()
        self._update_status()

    def clear_reference_allocations(self, invoice_doctype: str, invoice_name: str) -> None:
        self.set(
            "references",
            [
                row
                for row in self.references
                if not (row.invoice_doctype == invoice_doctype and row.invoice_name == invoice_name)
            ],
        )
        self._set_amounts()
        self._update_status()

    def _set_defaults(self) -> None:
        if not self.status:
            self.status = "Draft"

        if not self.exchange_rate:
            self.exchange_rate = 1.0

        if not self.currency:
            self.currency = self._get_default_currency()

        if self.party_type and self.party:
            self.party_name = self._get_party_name()

    def _set_amounts(self) -> None:
        self.base_advance_amount = flt(self.advance_amount) * flt(self.exchange_rate)
        total_allocated = sum(flt(row.allocated_amount) for row in self.references)
        self.allocated_amount = total_allocated
        self.unallocated_amount = flt(self.advance_amount) - total_allocated
        self.base_allocated_amount = flt(total_allocated) * flt(self.exchange_rate)
        self.base_unallocated_amount = flt(self.base_advance_amount) - self.base_allocated_amount

        remaining = max(self.unallocated_amount, 0)
        for row in self.references:
            row.remaining_amount = remaining
            if not row.reference_currency:
                row.reference_currency = self.currency
            if not row.reference_exchange_rate:
                row.reference_exchange_rate = self.exchange_rate

    def _validate_allocations(self) -> None:
        if not self.party_type:
            frappe.throw(_("Party Type is required."))

        if not self.party:
            frappe.throw(_("Party is required for {0}.").format(self.party_type))

        precision = self.precision("advance_amount") or 2
        if flt(self.unallocated_amount, precision) < -0.005:
            frappe.throw(
                _("Total allocated amount ({0}) cannot exceed the advance amount ({1}).").format(
                    frappe.bold(frappe.format_value(self.allocated_amount, {"fieldtype": "Currency", "currency": self.currency})),
                    frappe.bold(frappe.format_value(self.advance_amount, {"fieldtype": "Currency", "currency": self.currency})),
                )
            )

        for row in self.references:
            if flt(row.allocated_amount) <= 0:
                frappe.throw(_("Allocated Amount must be greater than zero in row {0}.").format(row.idx))
            if not row.invoice_doctype or not row.invoice_name:
                frappe.throw(_("Invoice Reference and Doctype are mandatory in row {0}.").format(row.idx))

    def _update_status(self) -> None:
        if self.docstatus == 2:
            self.status = "Cancelled"
            return

        if self.docstatus == 0:
            self.status = "Draft"
            return

        if flt(self.unallocated_amount) <= 0:
            self.status = "Reconciled"
        elif self.payment_entry:
            self.status = "Paid"
        else:
            self.status = "Submitted"

    def _get_default_currency(self) -> str | None:
        if self.company:
            currency = frappe.db.get_value("Company", self.company, "default_currency")
            if currency:
                return currency
        return frappe.db.get_default("currency")

    def _get_party_name(self) -> str | None:
        fieldname = None
        if self.party_type == "Supplier":
            fieldname = "supplier_name"
        elif self.party_type == "Employee":
            fieldname = "employee_name"

        if fieldname:
            return frappe.db.get_value(self.party_type, self.party, fieldname) or self.party
        return self.party

    @property
    def available_unallocated(self) -> float:
        precision = self.precision("unallocated_amount") or 2
        return max(flt(self.unallocated_amount, precision), 0)
