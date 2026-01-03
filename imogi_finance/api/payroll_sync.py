from __future__ import annotations

import re
from typing import Iterable

import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.tax_operations import _get_gl_total, _get_tax_profile

PAYROLL_APP = "payroll_indonesia"


def _get_installed_apps() -> list[str]:
    getter = getattr(frappe, "get_installed_apps", None)
    if not callable(getter):
        return []

    try:
        installed = getter()
    except Exception:
        return []

    return installed or []


def is_payroll_installed() -> bool:
    return PAYROLL_APP in set(_get_installed_apps())


def _table_exists(table: str) -> bool:
    exists = getattr(getattr(frappe, "db", None), "table_exists", None)
    if callable(exists):
        try:
            return bool(exists(table))
        except Exception:
            return False
    return False


def _get_salary_slips(company: str, date_from=None, date_to=None) -> list[dict]:
    if not getattr(frappe, "get_all", None):
        return []

    filters: dict[str, object] = {"company": company, "docstatus": 1}
    if date_from and date_to:
        filters["posting_date"] = ["between", [date_from, date_to]]
    elif date_from:
        filters["posting_date"] = [">=", date_from]
    elif date_to:
        filters["posting_date"] = ["<=", date_to]

    return frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=["name", "employee", "employee_name", "posting_date", "company"],
        order_by="posting_date asc",
    )


def _collect_bpjs_amounts_from_details(slip_name: str) -> tuple[float, float]:
    if not _table_exists("Salary Detail") or not getattr(frappe, "get_all", None):
        return 0.0, 0.0

    details = frappe.get_all(
        "Salary Detail",
        filters={"parent": slip_name, "salary_component": ["like", "%BPJS%"]},
        fields=["salary_component", "amount", "parentfield"],
    )

    employee_share = 0.0
    employer_share = 0.0
    for row in details:
        amount = flt(row.get("amount"))
        parentfield = (row.get("parentfield") or "").lower()
        if parentfield == "deductions":
            employee_share += amount
        else:
            employer_share += amount

    return employee_share, employer_share


def get_bpjs_contributions(company: str, date_from=None, date_to=None) -> dict:
    """Return BPJS contribution rows from payroll if available, falling back to GL totals."""
    profile = _get_tax_profile(company)
    bpjs_account = getattr(profile, "bpjs_payable_account", None)

    gl_total = _get_gl_total(company, [bpjs_account], date_from, date_to) if bpjs_account else 0.0
    summary = {
        "account": bpjs_account,
        "gl_total": gl_total,
        "rows": [],
        "total_employee": 0.0,
        "total_employer": 0.0,
        "source": "GL",
    }

    if not is_payroll_installed():
        return summary

    salary_slips = _get_salary_slips(company, date_from, date_to)
    for slip in salary_slips:
        employee_share, employer_share = _collect_bpjs_amounts_from_details(slip["name"])
        total = employee_share + employer_share
        if not total:
            continue

        summary["rows"].append(
            {
                "salary_slip": slip["name"],
                "employee": slip.get("employee"),
                "employee_name": slip.get("employee_name"),
                "posting_date": slip.get("posting_date"),
                "employer_share": employer_share,
                "employee_share": employee_share,
                "total": total,
                "source": "Payroll",
            }
        )
        summary["total_employee"] += employee_share
        summary["total_employer"] += employer_share

    if summary["rows"]:
        summary["source"] = "Payroll"

    return summary


def get_bpjs_total(company: str, date_from=None, date_to=None) -> float:
    contributions = get_bpjs_contributions(company, date_from, date_to)
    total = flt(contributions.get("total_employee")) + flt(contributions.get("total_employer"))
    if total:
        return total
    return flt(contributions.get("gl_total"))


def _resolve_pph21_account(profile) -> str | None:
    for row in getattr(profile, "pph_accounts", []) or []:
        pph_type = (row.pph_type or "").replace(" ", "").lower()
        if pph_type == "pph21":
            return row.payable_account
    return None


def _iter_salary_details(doc: object) -> Iterable[dict]:
    for child_table in ("earnings", "deductions"):
        for row in getattr(doc, child_table, []) or []:
            yield {
                "salary_component": getattr(row, "salary_component", None),
                "amount": flt(getattr(row, "amount", 0)),
                "parentfield": child_table,
            }


def _build_salary_component_gl_rows(doc, profile) -> list[dict]:
    rows: list[dict] = []
    bpjs_account = getattr(profile, "bpjs_payable_account", None)
    pph21_account = _resolve_pph21_account(profile)

    for detail in _iter_salary_details(doc):
        component = (detail.get("salary_component") or "").lower()
        amount = flt(detail.get("amount"))
        parentfield = detail.get("parentfield") or ""

        if not amount:
            continue

        if "bpjs" in component and bpjs_account:
            rows.append(
                {
                    "account": bpjs_account,
                    "component": detail.get("salary_component"),
                    "share": "employee" if parentfield == "deductions" else "employer",
                    "amount": amount,
                }
            )
            continue

        compact_component = re.sub(r"\s+", "", component)
        if "pph21" in compact_component and pph21_account:
            rows.append(
                {
                    "account": pph21_account,
                    "component": detail.get("salary_component"),
                    "share": "withholding",
                    "amount": amount,
                }
            )

    return rows


def sync_salary_components_with_gl(doc):
    if not is_payroll_installed() or not getattr(doc, "company", None):
        return

    try:
        profile = _get_tax_profile(doc.company)
    except Exception:
        return
    rows = _build_salary_component_gl_rows(doc, profile)
    if not rows:
        return

    accounts = sorted({row["account"] for row in rows if row.get("account")})
    message = _("Captured payroll liabilities for GL sync: {0}").format(", ".join(accounts))
    try:
        doc.add_comment("Info", message)
    except Exception:
        pass


def handle_salary_slip_submit(doc, method=None):
    sync_salary_components_with_gl(doc)


def handle_salary_slip_cancel(doc, method=None):
    sync_salary_components_with_gl(doc)
