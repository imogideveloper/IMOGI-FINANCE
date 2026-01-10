from __future__ import annotations

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from imogi_finance.services.letter_template_service import render_payment_letter_html


class CustomSalesInvoice(SalesInvoice):
    def get_payment_letter_html(self):
        return render_payment_letter_html(self)


@frappe.whitelist()
def get_sales_invoice_payment_letter(name: str):
    doc = frappe.get_doc("Sales Invoice", name)
    return doc.get_payment_letter_html()
