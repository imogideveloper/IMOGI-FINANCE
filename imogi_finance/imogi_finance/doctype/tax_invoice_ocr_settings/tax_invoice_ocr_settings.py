# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TaxInvoiceOCRSettings(Document):
    def validate(self):
        if self.ocr_provider == "Google Vision":
            if not self.google_vision_service_account_file:
                frappe.throw(_("Google Vision Service Account File is required when provider is Google Vision."))

        if self.ocr_provider == "Tesseract" and not self.tesseract_cmd:
            frappe.throw(_("Tesseract command/path is required when provider is Tesseract."))
