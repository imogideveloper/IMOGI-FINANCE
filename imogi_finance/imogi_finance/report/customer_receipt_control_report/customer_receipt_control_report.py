from __future__ import annotations

from typing import Dict, List, Tuple

import frappe
from frappe import _


def execute(filters: Dict | None = None) -> Tuple[List[Dict], List[Dict]]:
    filters = filters or {}
    columns = _get_columns()
    data = _get_data(filters)
    return columns, data


def _get_columns() -> List[Dict]:
    return [
        {"fieldname": "receipt_no", "label": _("Receipt No"), "fieldtype": "Link", "options": "Customer Receipt", "width": 160},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 200},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
        {"fieldname": "receipt_purpose", "label": _("Purpose"), "fieldtype": "Data", "width": 130},
        {"fieldname": "customer_reference_no", "label": _("Customer Ref"), "fieldtype": "Data", "width": 160},
        {"fieldname": "sales_order_no", "label": _("Sales Order"), "fieldtype": "Data", "width": 200},
        {"fieldname": "sales_invoice_no", "label": _("Sales Invoice"), "fieldtype": "Data", "width": 200},
        {"fieldname": "total_amount", "label": _("Total Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "paid_amount", "label": _("Paid Amount"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "stamp_mode", "label": _("Stamp Mode"), "fieldtype": "Data", "width": 110},
        {"fieldname": "digital_stamp_status", "label": _("Digital Stamp Status"), "fieldtype": "Data", "width": 160},
        {"fieldname": "payment_entries", "label": _("Payment Entry"), "fieldtype": "Data", "width": 220},
    ]


def _get_conditions(filters: Dict) -> Tuple[str, Dict]:
    conditions = []
    params: Dict[str, str] = {}

    mapping = {
        "date_from": ("cr.posting_date", ">="),
        "date_to": ("cr.posting_date", "<="),
        "receipt_no": ("cr.name", "="),
        "status": ("cr.status", "="),
        "customer": ("cr.customer", "="),
        "customer_reference_no": ("cr.customer_reference_no", "="),
        "sales_order_no": ("cri.sales_order", "="),
        "billing_no": ("cri.sales_invoice", "="),
        "receipt_purpose": ("cr.receipt_purpose", "="),
        "stamp_mode": ("cr.stamp_mode", "="),
        "digital_stamp_status": ("cr.digital_stamp_status", "="),
    }

    for key, (field, operator) in mapping.items():
        if filters.get(key):
            conditions.append(f"{field} {operator} %({key})s")
            params[key] = filters[key]

    if filters.get("sales_invoice_no"):
        conditions.append("cri.sales_invoice = %(sales_invoice_no)s")
        params["sales_invoice_no"] = filters["sales_invoice_no"]

    where = " and ".join(conditions) if conditions else "1=1"
    return where, params


def _get_data(filters: Dict) -> List[Dict]:
    where, params = _get_conditions(filters)
    query = f"""
        select
            cr.name as receipt_no,
            cr.posting_date,
            cr.customer,
            cr.status,
            cr.receipt_purpose,
            cr.customer_reference_no,
            group_concat(distinct cri.sales_order separator ', ') as sales_order_no,
            group_concat(distinct cri.sales_invoice separator ', ') as sales_invoice_no,
            cr.total_amount,
            cr.paid_amount,
            cr.outstanding_amount,
            cr.stamp_mode,
            cr.digital_stamp_status,
            group_concat(distinct crp.payment_entry separator ', ') as payment_entries
        from `tabCustomer Receipt` cr
        left join `tabCustomer Receipt Item` cri on cri.parent = cr.name
        left join `tabCustomer Receipt Payment` crp on crp.parent = cr.name
        where {where}
        group by cr.name
        order by cr.posting_date desc, cr.name desc
    """
    return frappe.db.sql(query, params, as_dict=True)
