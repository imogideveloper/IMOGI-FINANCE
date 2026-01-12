from __future__ import annotations

from typing import List, Optional

import frappe
from frappe.model.document import Document

from imogi_finance.api import reporting as reporting_api


class CashBankDailyReport(Document):
    """Persistent wrapper around the daily cash/bank report.

    A document stores the input parameters (date, optional branches filter)
    and a JSON snapshot of the generated report so it can be printed or
    re-opened later without recomputing everything.
    """

    def validate(self):
        # Global "view only" switch from Finance Control Settings
        if self.is_new() and self._is_view_only_mode():
            frappe.throw(
                frappe._(
                    "Cash/Bank Daily Report is currently in view-only mode. New reports cannot be created."
                )
            )
        # Ensure one report per date + bank account
        self._validate_unique_per_account_and_date()
        # Ensure we don't skip previous dates that already have transactions
        self._validate_no_gaps_in_transaction_dates()

    def before_insert(self):
        # Auto-generate snapshot on first insert if report_date is set
        if self.report_date:
            self.generate_snapshot()

    def on_update(self):
        # If user changes the date or branches on an existing doc, refresh
        if self.has_value_changed("report_date") or self.has_value_changed("branches"):
            if self.report_date:
                self.generate_snapshot()

    def _parse_branches_filter(self) -> Optional[List[str]]:
        if not self.branches:
            return None
        # Simple comma-separated list of branch names
        items = [b.strip() for b in (self.branches or "").split(",")]
        return [b for b in items if b]

    def _is_view_only_mode(self) -> bool:
        try:
            settings = frappe.get_cached_doc("Finance Control Settings")
        except Exception:
            return False
        return bool(getattr(settings, "daily_report_view_only", 0))

    def _validate_unique_per_account_and_date(self) -> None:
        if not self.report_date or not self.bank_account:
            return

        existing = frappe.db.exists(
            "Cash Bank Daily Report",
            {
                "report_date": self.report_date,
                "bank_account": self.bank_account,
                "name": ("!=", self.name) if self.name else ("!=" , ""),
            },
        )
        if existing:
            frappe.throw(
                frappe._(
                    "Daily report for account {0} on {1} already exists (document: {2})."
                ).format(
                    self.bank_account,
                    frappe.utils.format_date(self.report_date),
                    existing,
                )
            )

    def _validate_no_gaps_in_transaction_dates(self) -> None:
        """Block creating a report for a date if the immediately previous
        transaction date for this account does not yet have a report.

        This enforces sequential daily reports whenever there are
        consecutive Bank Transactions.
        """

        if not self.report_date or not self.bank_account or not getattr(frappe, "db", None):
            return

        # Find the latest Bank Transaction date before this report date
        prev_tx = frappe.get_all(
            "Bank Transaction",
            filters={
                "bank_account": self.bank_account,
                "transaction_date": ("<", self.report_date),
            },
            fields=["transaction_date"],
            order_by="transaction_date desc",
            limit=1,
        )

        if not prev_tx:
            return

        prev_date = prev_tx[0].get("transaction_date")
        if not prev_date:
            return

        has_prev_report = frappe.db.exists(
            "Cash Bank Daily Report",
            {"bank_account": self.bank_account, "report_date": prev_date},
        )
        if not has_prev_report:
            frappe.throw(
                frappe._(
                    "Cannot create daily report for {0} on {1} because there is no report for the previous transaction date {2}."
                ).format(
                    self.bank_account,
                    frappe.utils.format_date(self.report_date),
                    frappe.utils.format_date(prev_date),
                )
            )

    def generate_snapshot(self):
        branches = self._parse_branches_filter()
        report_date_str = (
            self.report_date if isinstance(self.report_date, str) else self.report_date.isoformat()
        )

        payload = reporting_api.preview_daily_report(
            branches=branches,
            bank_account=self.bank_account or None,
            report_date=report_date_str,
        )

        # Store full JSON snapshot for print formats / APIs
        self.snapshot_json = frappe.as_json(payload)
        self.status = "Generated"

        # Also copy consolidated totals into top-level currency fields (if present)
        consolidated = (payload or {}).get("consolidated") or {}
        self.opening_balance = consolidated.get("opening_balance") or 0
        self.inflow = consolidated.get("inflow") or 0
        self.outflow = consolidated.get("outflow") or 0
        self.closing_balance = consolidated.get("closing_balance") or 0


@frappe.whitelist()
def regenerate(name: str):
    """Explicit API to regenerate a report snapshot for an existing document.

    Can be wired to a custom button on the DocType.
    """

    doc = frappe.get_doc("Cash Bank Daily Report", name)
    if not doc.report_date:
        frappe.throw("Report Date is required to regenerate the snapshot")

    doc.generate_snapshot()
    doc.save()
    return doc