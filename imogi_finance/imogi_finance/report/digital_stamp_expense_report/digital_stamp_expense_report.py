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
        {"label": _("Customer Receipt"), "fieldname": "customer_receipt", "fieldtype": "Link", "options": "Customer Receipt", "width": 180},
        {"label": _("Stamp Applied On"), "fieldname": "stamp_applied_on", "fieldtype": "Datetime", "width": 160},
        {"label": _("Payment Reference Type"), "fieldname": "payment_reference_doctype", "fieldtype": "Data", "width": 170},
        {"label": _("Payment Reference"), "fieldname": "payment_reference", "fieldtype": "Dynamic Link", "options": "payment_reference_doctype", "width": 170},
        {"label": _("Payment Status"), "fieldname": "payment_status", "fieldtype": "Data", "width": 120},
        {"label": _("Stamp Cost"), "fieldname": "stamp_cost", "fieldtype": "Currency", "width": 140},
    ]


def get_data(filters: dict) -> list[dict]:
    conditions = [
        "log.parenttype = 'Customer Receipt'",
        "log.parentfield = 'digital_stamp_logs'",
        "log.stamp_cost is not null",
    ]
    params: dict[str, str] = {}

    if filters.get("start_date"):
        conditions.append("DATE(COALESCE(log.timestamp, cr.digital_stamp_issue_datetime)) >= %(start_date)s")
        params["start_date"] = filters["start_date"]

    if filters.get("end_date"):
        conditions.append("DATE(COALESCE(log.timestamp, cr.digital_stamp_issue_datetime)) <= %(end_date)s")
        params["end_date"] = filters["end_date"]

    payment_status = filters.get("payment_status")
    if payment_status in {"Draft", "Paid", "Cancelled"}:
        status_map = {"Draft": 0, "Paid": 1, "Cancelled": 2}
        conditions.append("COALESCE(pe.docstatus, je.docstatus, 0) = %(payment_docstatus)s")
        params["payment_docstatus"] = status_map[payment_status]

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT
            cr.name AS customer_receipt,
            COALESCE(log.timestamp, cr.digital_stamp_issue_datetime) AS stamp_applied_on,
            log.payment_reference_doctype,
            log.payment_reference,
            CASE
                WHEN log.payment_reference_doctype = 'Payment Entry' THEN
                    CASE pe.docstatus WHEN 1 THEN 'Paid' WHEN 2 THEN 'Cancelled' ELSE 'Draft' END
                WHEN log.payment_reference_doctype = 'Journal Entry' THEN
                    CASE je.docstatus WHEN 1 THEN 'Paid' WHEN 2 THEN 'Cancelled' ELSE 'Draft' END
                ELSE 'Draft'
            END AS payment_status,
            log.stamp_cost
        FROM `tabCustomer Receipt Stamp Log` log
        INNER JOIN `tabCustomer Receipt` cr ON cr.name = log.parent
        LEFT JOIN `tabPayment Entry` pe
            ON log.payment_reference_doctype = 'Payment Entry' AND log.payment_reference = pe.name
        LEFT JOIN `tabJournal Entry` je
            ON log.payment_reference_doctype = 'Journal Entry' AND log.payment_reference = je.name
        WHERE {where_clause}
        ORDER BY stamp_applied_on DESC, customer_receipt DESC
    """

    return frappe.db.sql(query, params, as_dict=True)
