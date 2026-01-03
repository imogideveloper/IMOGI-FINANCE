from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.api.payroll_sync import get_bpjs_contributions, is_payroll_installed


def execute(filters=None):
    filters = filters or {}
    company = filters.get("company")
    if not company:
        frappe.throw(_("Please select a Company to build the BPJS report."))

    date_from = filters.get("from_date")
    date_to = filters.get("to_date")
    summary = get_bpjs_contributions(company, date_from, date_to)

    columns = [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 120},
        {"label": _("Salary Slip"), "fieldname": "salary_slip", "fieldtype": "Link", "options": "Salary Slip", "width": 150},
        {"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": _("Employer Share"), "fieldname": "employer_share", "fieldtype": "Currency", "width": 140},
        {"label": _("Employee Share"), "fieldname": "employee_share", "fieldtype": "Currency", "width": 140},
        {"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "width": 140},
        {"label": _("Source"), "fieldname": "source", "fieldtype": "Data", "width": 100},
    ]

    data = []
    for row in summary.get("rows") or []:
        data.append(
            {
                "posting_date": row.get("posting_date"),
                "salary_slip": row.get("salary_slip"),
                "employee": row.get("employee"),
                "employee_name": row.get("employee_name"),
                "employer_share": flt(row.get("employer_share")),
                "employee_share": flt(row.get("employee_share")),
                "total": flt(row.get("total")),
                "source": row.get("source"),
            }
        )

    if not data and summary.get("gl_total"):
        data.append(
            {
                "posting_date": date_to or date_from,
                "salary_slip": None,
                "employee": None,
                "employee_name": _("Finance (GL Accrual)"),
                "employer_share": flt(summary.get("gl_total")),
                "employee_share": 0.0,
                "total": flt(summary.get("gl_total")),
                "source": "GL",
            }
        )

    if summary.get("source") != "Payroll" or not is_payroll_installed():
        frappe.msgprint(
            _("Payroll Indonesia is not installed; showing Finance GL fallback for BPJS."),
            alert=True,
        )

    return columns, data
