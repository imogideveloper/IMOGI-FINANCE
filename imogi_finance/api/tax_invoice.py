from __future__ import annotations

import frappe
from frappe import _
from imogi_finance import roles

from imogi_finance.tax_invoice_ocr import (
    get_tax_invoice_upload_context,
    get_tax_invoice_ocr_monitoring,
    run_ocr,
    sync_tax_invoice_upload,
    verify_tax_invoice,
)


@frappe.whitelist()
def run_ocr_for_purchase_invoice(pi_name: str):
    return run_ocr(pi_name, "Purchase Invoice")


@frappe.whitelist()
def run_ocr_for_expense_request(er_name: str):
    return run_ocr(er_name, "Expense Request")


@frappe.whitelist()
def run_ocr_for_branch_expense_request(ber_name: str):
    return run_ocr(ber_name, "Branch Expense Request")


@frappe.whitelist()
def run_ocr_for_sales_invoice(si_name: str):
    return run_ocr(si_name, "Sales Invoice")


@frappe.whitelist()
def run_ocr_for_upload(upload_name: str):
    return run_ocr(upload_name, "Tax Invoice OCR Upload")


@frappe.whitelist()
def verify_purchase_invoice_tax_invoice(pi_name: str, force: bool = False):
    doc = frappe.get_doc("Purchase Invoice", pi_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER))
    return verify_tax_invoice(doc, doctype="Purchase Invoice", force=bool(force))


@frappe.whitelist()
def verify_expense_request_tax_invoice(er_name: str, force: bool = False):
    doc = frappe.get_doc("Expense Request", er_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    return verify_tax_invoice(doc, doctype="Expense Request", force=bool(force))


@frappe.whitelist()
def verify_branch_expense_request_tax_invoice(ber_name: str, force: bool = False):
    doc = frappe.get_doc("Branch Expense Request", ber_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    return verify_tax_invoice(doc, doctype="Branch Expense Request", force=bool(force))


@frappe.whitelist()
def verify_sales_invoice_tax_invoice(si_name: str, force: bool = False):
    doc = frappe.get_doc("Sales Invoice", si_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER))
    return verify_tax_invoice(doc, doctype="Sales Invoice", force=bool(force))


@frappe.whitelist()
def verify_tax_invoice_upload(upload_name: str, force: bool = False):
    doc = frappe.get_doc("Tax Invoice OCR Upload", upload_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER, roles.TAX_REVIEWER))
    return verify_tax_invoice(doc, doctype="Tax Invoice OCR Upload", force=bool(force))


@frappe.whitelist()
def monitor_tax_invoice_ocr(docname: str, doctype: str):
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER, roles.TAX_REVIEWER))
    return get_tax_invoice_ocr_monitoring(docname, doctype)


@frappe.whitelist()
def get_tax_invoice_upload_context_api(target_doctype: str, target_name: str | None = None):
    return get_tax_invoice_upload_context(target_doctype=target_doctype, target_name=target_name)


@frappe.whitelist()
def apply_tax_invoice_upload(target_doctype: str, target_name: str, upload_name: str | None = None):
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER))
    doc = frappe.get_doc(target_doctype, target_name)
    return sync_tax_invoice_upload(doc, target_doctype, upload_name)
