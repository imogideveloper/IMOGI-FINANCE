# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.services.tax_invoice_service import sync_tax_invoice_with_sales
from imogi_finance.tax_invoice_ocr import NPWP_REGEX, normalize_npwp


def _validate_tax_invoice_no(tax_invoice_no: str | None):
    if not tax_invoice_no:
        frappe.throw(_("Tax Invoice Number is required."))

    if not re.fullmatch(r"\d{16}", tax_invoice_no or ""):
        frappe.throw(_("Tax Invoice Number must be exactly 16 digits."))


def _validate_npwp(npwp: str | None):
    if not npwp:
        frappe.throw(_("Customer NPWP is required."))

    if not NPWP_REGEX.fullmatch(npwp):
        normalized = normalize_npwp(npwp)
        if not normalized or not re.fullmatch(r"\d{15,20}", normalized):
            frappe.throw(_("Customer NPWP is not valid."))


def _ensure_file_exists(file_url: str | None):
    if not file_url:
        frappe.throw(_("Tax Invoice PDF is required."))

    if frappe.db.exists("File", {"file_url": file_url, "attached_to_doctype": "Tax Invoice Upload"}):
        return

    if frappe.db.exists("File", {"file_url": file_url}):
        return

    frappe.throw(_("Tax Invoice PDF could not be found. Please re-upload the file."))


def _ensure_unique_tax_invoice_no(doc: Document):
    existing = frappe.db.exists(
        "Tax Invoice Upload",
        {
            "tax_invoice_no": doc.tax_invoice_no,
            "name": ["!=", doc.name or ""],
        },
    )
    if existing:
        frappe.throw(_("Tax Invoice Number already exists on Tax Invoice Upload {0}.").format(existing))


class TaxInvoiceUpload(Document):
    def validate(self):
        self.tax_invoice_no = (self.tax_invoice_no or "").strip()
        _validate_tax_invoice_no(self.tax_invoice_no)
        _validate_npwp(self.customer_npwp)
        _ensure_unique_tax_invoice_no(self)
        _ensure_file_exists(self.invoice_pdf)

    def _should_attempt_sync(self) -> bool:
        return bool(self.linked_sales_invoice) and (self.status or "Draft") != "Synced"

    def _sync_on_change(self):
        if getattr(frappe.flags, "in_tax_invoice_upload_sync", False):
            return
        if not self._should_attempt_sync():
            return

        sync_tax_invoice_with_sales(self, fail_silently=True)

    def after_insert(self):
        self._sync_on_change()

    def on_update(self):
        self._sync_on_change()

    @frappe.whitelist()
    def sync_now(self):
        return sync_tax_invoice_with_sales(self)
