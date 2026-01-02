from __future__ import annotations

import frappe
from frappe import _

from imogi_finance.tax_invoice_ocr import run_ocr, verify_tax_invoice


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
def verify_purchase_invoice_tax_invoice(pi_name: str, force: bool = False):
    doc = frappe.get_doc("Purchase Invoice", pi_name)
    frappe.only_for(("Accounts Manager", "Accounts User", "System Manager"))
    return verify_tax_invoice(doc, doctype="Purchase Invoice", force=bool(force))


@frappe.whitelist()
def verify_expense_request_tax_invoice(er_name: str, force: bool = False):
    doc = frappe.get_doc("Expense Request", er_name)
    frappe.only_for(("Accounts Manager", "System Manager"))
    return verify_tax_invoice(doc, doctype="Expense Request", force=bool(force))


@frappe.whitelist()
def verify_branch_expense_request_tax_invoice(ber_name: str, force: bool = False):
    doc = frappe.get_doc("Branch Expense Request", ber_name)
    frappe.only_for(("Accounts Manager", "System Manager"))
    return verify_tax_invoice(doc, doctype="Branch Expense Request", force=bool(force))


@frappe.whitelist()
def verify_sales_invoice_tax_invoice(si_name: str, force: bool = False):
    doc = frappe.get_doc("Sales Invoice", si_name)
    frappe.only_for(("Accounts Manager", "Accounts User", "System Manager"))
    return verify_tax_invoice(doc, doctype="Sales Invoice", force=bool(force))
