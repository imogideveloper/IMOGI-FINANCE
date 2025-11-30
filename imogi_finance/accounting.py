"""Accounting helpers for IMOGI Finance."""

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def create_purchase_invoice_from_request(expense_request_name: str) -> str:
    """Create a Purchase Invoice from an Expense Request and return its name."""
    request = frappe.get_doc("Expense Request", expense_request_name)
    company = frappe.db.get_value("Cost Center", request.cost_center, "company")
    if not company:
        frappe.throw(_("Unable to resolve company from the selected Cost Center."))

    pi = frappe.new_doc("Purchase Invoice")
    pi.company = company
    pi.supplier = request.supplier
    pi.posting_date = request.request_date
    pi.bill_date = request.supplier_invoice_date
    pi.bill_no = request.supplier_invoice_no
    pi.currency = request.currency
    pi.imogi_expense_request = request.name
    pi.imogi_request_type = request.request_type
    pi.tax_withholding_category = request.pph_type if request.is_pph_applicable else None
    pi.imogi_pph_type = request.pph_type
    pi.apply_tds = 1 if request.is_pph_applicable else 0

    pi.append(
        "items",
        {
            "item_name": request.asset_name or request.description or request.expense_account,
            "description": request.description,
            "expense_account": request.expense_account,
            "cost_center": request.cost_center,
            "project": request.project,
            "qty": 1,
            "rate": request.amount,
            "amount": request.amount,
        },
    )

    if request.is_ppn_applicable and request.ppn_template:
        pi.taxes_and_charges = request.ppn_template
        pi.set_taxes()

    pi.insert(ignore_permissions=True)

    request.db_set({"linked_purchase_invoice": pi.name, "status": "Linked"})
    return pi.name


@frappe.whitelist()
def create_journal_entry_from_request(expense_request_name: str) -> str:
    """Create a Journal Entry from an Expense Request and return its name."""
    request = frappe.get_doc("Expense Request", expense_request_name)
    company = frappe.db.get_value("Cost Center", request.cost_center, "company")
    if not company:
        frappe.throw(_("Unable to resolve company from the selected Cost Center."))

    payable_account = frappe.db.get_value(
        "Supplier", request.supplier, "default_payable_account", cache=True
    ) or frappe.get_cached_value("Company", company, "default_payable_account")

    if not payable_account:
        frappe.throw(_("Default payable account is missing for this company."))

    je = frappe.new_doc("Journal Entry")
    je.company = company
    je.posting_date = request.request_date
    je.user_remark = request.description
    je.imogi_expense_request = request.name

    je.append(
        "accounts",
        {
            "account": request.expense_account,
            "cost_center": request.cost_center,
            "project": request.project,
            "debit_in_account_currency": request.amount,
        },
    )

    je.append(
        "accounts",
        {
            "account": payable_account,
            "credit_in_account_currency": request.amount,
            "party_type": "Supplier",
            "party": request.supplier,
        },
    )

    je.insert(ignore_permissions=True)
    request.db_set({"linked_journal_entry": je.name, "status": "Linked"})
    return je.name
