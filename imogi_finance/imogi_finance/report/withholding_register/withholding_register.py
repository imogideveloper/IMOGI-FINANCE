from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.tax_operations import _get_tax_profile


def execute(filters=None):
    filters = filters or {}
    company = filters.get("company")
    if not company:
        frappe.throw(_("Company is required"))

    profile = _get_tax_profile(company)
    accounts = filters.get("accounts") or [
        row.payable_account for row in getattr(profile, "pph_accounts", []) if row.payable_account
    ]
    if isinstance(accounts, str):
        accounts = [accounts]

    columns = [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 180},
        {"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 120},
        {"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 160},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 130},
        {"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "width": 110},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "width": 110},
        {"label": _("Net (Credit-Debit)"), "fieldname": "net_amount", "fieldtype": "Currency", "width": 140},
        {"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 200},
    ]

    entries = _get_entries(company, accounts, filters.get("from_date"), filters.get("to_date"))
    return columns, entries


def _get_entries(company: str, accounts: list[str], date_from: str | None, date_to: str | None) -> list[dict]:
    conditions: dict[str, object] = {
        "company": company,
        "is_cancelled": 0,
    }

    if accounts:
        conditions["account"] = ["in", accounts]

    if date_from and date_to:
        conditions["posting_date"] = ["between", [date_from, date_to]]
    elif date_from:
        conditions["posting_date"] = [">=", date_from]
    elif date_to:
        conditions["posting_date"] = ["<=", date_to]

    entries = frappe.get_all(
        "GL Entry",
        filters=conditions,
        fields=[
            "posting_date",
            "account",
            "party_type",
            "party",
            "voucher_type",
            "voucher_no",
            "debit",
            "credit",
            "remarks",
        ],
        order_by="posting_date asc, name asc",
    )

    for entry in entries:
        entry["net_amount"] = flt(entry.get("credit")) - flt(entry.get("debit"))

    return entries
