from __future__ import annotations

from datetime import date
from importlib import util as importlib_util
import sys
import types

from imogi_finance.reporting import (
    ReportScheduler,
    build_dashboard_snapshot,
    build_daily_report,
    resolve_signers,
)
from imogi_finance.reporting.data import load_daily_inputs


existing = sys.modules.get("frappe")
if existing:
    frappe = existing
elif importlib_util.find_spec("frappe"):
    import frappe  # type: ignore
else:
    frappe = sys.modules.setdefault(
        "frappe",
        types.SimpleNamespace(
            whitelist=lambda *args, **kwargs: (lambda fn: fn),
            _=lambda msg, *args, **kwargs: msg,
            _dict=lambda value=None, **kwargs: {**(value or {}), **kwargs},
            utils=types.SimpleNamespace(nowdate=lambda: date.today().isoformat()),
            session=types.SimpleNamespace(user="system"),
        ),
    )

_ = frappe._


def _get_settings():
    try:
        if hasattr(frappe, "get_cached_doc"):
            return frappe.get_cached_doc("Finance Control Settings")
    except Exception:
        return {}
    return {}


def _extract_signers_from_settings(doc, bank_account: str | None = None) -> dict:
    """Return signer mapping, allowing per-account overrides.

    Priority:
    1) Per-account rule from Finance Control Settings.daily_report_signer_rules
    2) Global defaults on the same settings doc.
    """

    if not doc:
        return {}

    base = {
        "prepared_by": getattr(doc, "daily_report_preparer", None),
        "approved_by": getattr(doc, "daily_report_approver", None),
        "acknowledged_by": getattr(doc, "daily_report_acknowledger", None),
    }

    if not bank_account:
        return base

    # Look for a matching rule in the child table (if present)
    rules = getattr(doc, "daily_report_signer_rules", []) or []
    for row in rules:
        if getattr(row, "bank_account", None) == bank_account:
            overrides = {
                "prepared_by": getattr(row, "prepared_by", None) or base.get("prepared_by"),
                "approved_by": getattr(row, "approved_by", None) or base.get("approved_by"),
                "acknowledged_by": getattr(row, "acknowledged_by", None)
                or base.get("acknowledged_by"),
            }
            return overrides

    return base


@frappe.whitelist()
def preview_daily_report(branches=None, report_date=None, bank_account=None, cash_account=None):
    settings = _get_settings()
    signers = resolve_signers(_extract_signers_from_settings(settings, bank_account))
    report_date_obj = date.fromisoformat(report_date) if report_date else None
    branch_filter = branches or None
    bank_filter = bank_account or None
    cash_filter = cash_account or None
    transactions, opening_balances = load_daily_inputs(
        report_date_obj,
        branches=branch_filter,
        bank_accounts=[bank_filter] if isinstance(bank_filter, str) and bank_filter else bank_filter,
        cash_accounts=[cash_filter] if isinstance(cash_filter, str) and cash_filter else cash_filter,
    )
    bundle = build_daily_report(
        transactions,
        opening_balances=opening_balances,
        report_date=report_date_obj,
        signers=signers,
        allowed_branches=branch_filter,
        status="preview",
    )
    return bundle.to_dict()


@frappe.whitelist()
def get_dashboard_snapshot(branches=None, report_date=None, bank_account=None, cash_account=None):
    settings = _get_settings()
    signers = resolve_signers(_extract_signers_from_settings(settings, bank_account))
    report_date_obj = date.fromisoformat(report_date) if report_date else None
    branch_filter = branches or None
    bank_filter = bank_account or None
    cash_filter = cash_account or None
    transactions, opening_balances = load_daily_inputs(
        report_date_obj,
        branches=branch_filter,
        bank_accounts=[bank_filter] if isinstance(bank_filter, str) and bank_filter else bank_filter,
        cash_accounts=[cash_filter] if isinstance(cash_filter, str) and cash_filter else cash_filter,
    )
    snapshot = build_dashboard_snapshot(
        transactions=transactions,
        opening_balances=opening_balances,
        report_date=report_date_obj,
        allowed_branches=branch_filter,
        reconciliation=None,
        signers=signers,
    )
    return snapshot


@frappe.whitelist()
def plan_reporting_jobs(branches=None):
    scheduler = ReportScheduler(activate=False)

    def _daily_job(**kwargs):
        return {"status": "planned", "branches": kwargs.get("branches")}

    def _monthly_job():
        return {"status": "planned"}

    scheduler.schedule_daily_report(_daily_job, branches=branches or None)
    scheduler.schedule_monthly_reconciliation(_monthly_job)

    return frappe._dict(
        {
            "backend": scheduler.backend,
            "jobs": [job.to_dict() for job in scheduler.jobs],
        }
    )
