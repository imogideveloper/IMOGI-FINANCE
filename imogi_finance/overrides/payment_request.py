from __future__ import annotations

import frappe
from erpnext.accounts.doctype.payment_request.payment_request import PaymentRequest

from imogi_finance.services.letter_template_service import render_payment_letter_html


class CustomPaymentRequest(PaymentRequest):
    def get_payment_letter_html(self):
        return render_payment_letter_html(self, letter_type="Payment Request Letter")


@frappe.whitelist()
def get_payment_request_payment_letter(name: str):
    doc = frappe.get_doc("Payment Request", name)
    return doc.get_payment_letter_html()
