from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.tax_invoice_ocr import get_settings


def execute(filters=None):
    filters = filters or {}
    settings = get_settings()

    columns = [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 150},
        {"label": _("Supplier NPWP"), "fieldname": "ti_fp_npwp", "fieldtype": "Data", "width": 140},
        {"label": _("Tax Invoice No"), "fieldname": "ti_fp_no", "fieldtype": "Data", "width": 160},
        {"label": _("Tax Invoice Date"), "fieldname": "ti_fp_date", "fieldtype": "Date", "width": 110},
        {"label": _("DPP"), "fieldname": "ti_fp_dpp", "fieldtype": "Currency", "width": 120},
        {"label": _("PPN"), "fieldname": "ti_fp_ppn", "fieldtype": "Currency", "width": 120},
        {"label": _("PPN (Tax Row)"), "fieldname": "tax_row_amount", "fieldtype": "Currency", "width": 140},
        {"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
    ]

    conditions = {
        "docstatus": 1,
        "ti_verification_status": "Verified",
    }

    if filters.get("company"):
        conditions["company"] = filters.get("company")

    if filters.get("from_date"):
        conditions["posting_date"] = [">=", filters.get("from_date")]

    if filters.get("to_date"):
        conditions.setdefault("posting_date", [">=", None])
        conditions["posting_date"] = ["between", [filters.get("from_date") or "2000-01-01", filters.get("to_date")]]

    if filters.get("supplier"):
        conditions["supplier"] = filters.get("supplier")

    invoices = frappe.get_all(
        "Purchase Invoice",
        filters=conditions,
        fields=[
            "name",
            "posting_date",
            "supplier",
            "company",
            "ti_fp_npwp",
            "ti_fp_no",
            "ti_fp_date",
            "ti_fp_dpp",
            "ti_fp_ppn",
        ],
        order_by="posting_date asc",
    )

    data = []
    account_filter = settings.get("ppn_input_account")
    for invoice in invoices:
        tax_amount = _get_tax_amount(invoice.name, account_filter)
        data.append(
            {
                **invoice,
                "tax_row_amount": tax_amount,
            }
        )

    return columns, data


def _get_tax_amount(invoice_name: str, account_filter: str | None) -> float:
    if not account_filter:
        frappe.msgprint(
            _("PPN Input Account is not configured. Tax amounts will be shown as 0 until it is set."),
            alert=True,
        )
        return 0

    tax_rows = frappe.get_all(
        "Purchase Taxes and Charges",
        filters={"parent": invoice_name, "account_head": account_filter},
        fields=[["sum", "tax_amount", "total"]],
    )

    if tax_rows and tax_rows[0].get("total") is not None:
        return flt(tax_rows[0].get("total"))

    return 0
