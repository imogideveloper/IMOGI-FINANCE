from __future__ import annotations

import frappe
from frappe import _


def execute(filters: dict | None = None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns() -> list[dict]:
    return [
        {"label": _("Advance Payment"), "fieldname": "advance_payment_entry", "fieldtype": "Link", "options": "Advance Payment Entry", "width": 200},
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 110},
        {"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 150},
        {"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
        {"label": _("Advance Amount"), "fieldname": "advance_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Allocated Amount"), "fieldname": "allocated_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Unallocated Amount"), "fieldname": "unallocated_amount", "fieldtype": "Currency", "width": 140},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": _("Reference Doctype"), "fieldname": "reference_doctype", "fieldtype": "Data", "width": 150},
        {"label": _("Reference Name"), "fieldname": "reference_name", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 180},
        {"label": _("Reference Allocated"), "fieldname": "reference_allocated", "fieldtype": "Currency", "width": 140},
        {"label": _("Remaining After Allocation"), "fieldname": "reference_remaining", "fieldtype": "Currency", "width": 170},
    ]


def get_data(filters: dict) -> list[dict]:
    conditions = ["ape.docstatus < 2"]
    params: dict[str, str] = {}

    if filters.get("company"):
        conditions.append("ape.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("party_type"):
        conditions.append("ape.party_type = %(party_type)s")
        params["party_type"] = filters["party_type"]

    if filters.get("party"):
        conditions.append("ape.party = %(party)s")
        params["party"] = filters["party"]

    if filters.get("currency"):
        conditions.append("ape.currency = %(currency)s")
        params["currency"] = filters["currency"]

    if filters.get("from_date"):
        conditions.append("ape.posting_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("ape.posting_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT
            ape.name AS advance_payment_entry,
            ape.posting_date,
            ape.party_type,
            ape.party,
            ape.currency,
            ape.advance_amount,
            ape.allocated_amount,
            ape.unallocated_amount,
            ape.status,
            ref.invoice_doctype AS reference_doctype,
            ref.invoice_name AS reference_name,
            ref.allocated_amount AS reference_allocated,
            ref.remaining_amount AS reference_remaining
        FROM `tabAdvance Payment Entry` ape
        LEFT JOIN `tabAdvance Payment Reference` ref
            ON ref.parent = ape.name
        WHERE {where_clause}
        ORDER BY ape.posting_date DESC, ape.name DESC
    """

    return frappe.db.sql(query, params, as_dict=True)
