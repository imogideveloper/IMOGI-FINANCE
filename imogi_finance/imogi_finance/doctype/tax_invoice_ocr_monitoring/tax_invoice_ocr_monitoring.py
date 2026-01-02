# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.tax_invoice_ocr import get_tax_invoice_ocr_monitoring


class TaxInvoiceOCRMonitoring(Document):
    @frappe.whitelist()
    def refresh_status(self):
        if not self.target_doctype or not self.target_name:
            frappe.throw(_("Target DocType and Target Name are required to refresh status."))

        result = get_tax_invoice_ocr_monitoring(self.target_name, self.target_doctype)
        doc_info = result.get("doc") or {}
        job_info = result.get("job") or {}

        self.job_name = result.get("job_name")
        self.provider = result.get("provider")
        self.max_retry = result.get("max_retry")

        self.ocr_status = doc_info.get("ocr_status")
        self.verification_status = doc_info.get("verification_status")
        self.ocr_confidence = doc_info.get("ocr_confidence")
        self.notes = doc_info.get("notes")
        self.fp_no = doc_info.get("fp_no")
        self.npwp = doc_info.get("npwp")
        self.tax_invoice_pdf = doc_info.get("tax_invoice_pdf")
        self.ocr_raw_json_present = 1 if doc_info.get("ocr_raw_json_present") else 0

        self.job_queue = job_info.get("queue")
        self.job_status = job_info.get("status")
        self.job_exc_info = job_info.get("exc_info")

        job_kwargs = job_info.get("kwargs")
        if isinstance(job_kwargs, str):
            self.job_kwargs = job_kwargs
        elif job_kwargs is not None:
            self.job_kwargs = json.dumps(job_kwargs, indent=2, ensure_ascii=False, default=str)
        else:
            self.job_kwargs = None

        self.enqueued_at = job_info.get("enqueued_at")
        self.started_at = job_info.get("started_at")
        self.ended_at = job_info.get("ended_at")

        return result
