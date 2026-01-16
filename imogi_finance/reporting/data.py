from __future__ import annotations

from collections import defaultdict
from datetime import date
from importlib import util as importlib_util
from typing import Iterable, Mapping, Sequence

import sys
import types

from imogi_finance.reporting.service import _as_amount, _normalise_direction


def _get_frappe():
    existing = sys.modules.get("frappe")
    if existing:
        return existing

    if importlib_util.find_spec("frappe"):
        import frappe  # type: ignore

        return frappe

    # Light stub for tests/offline usage
    fallback = sys.modules.setdefault(
        "frappe",
        types.SimpleNamespace(
            _=lambda msg, *args, **kwargs: msg,
            db=None,
            get_all=lambda *args, **kwargs: [],
            get_cached_doc=lambda *args, **kwargs: types.SimpleNamespace(),
        ),
    )
    if not hasattr(fallback, "db"):
        fallback.db = None
    return fallback


frappe = _get_frappe()
_ = getattr(frappe, "_", lambda msg, *args, **kwargs: msg)


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def _coerce_list(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if v]


def fetch_bank_transactions(
    report_date: date | None,
    *,
    branches: Sequence[str] | None = None,
    bank_accounts: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Fetch bank transactions up to and including the report date."""

    if not getattr(frappe, "db", None):
        return []

    has_branch_column = True
    if hasattr(frappe.db, "has_column"):
        has_branch_column = frappe.db.has_column("Bank Transaction", "branch")

    filters = {}
    if report_date:
        filters["transaction_date"] = ("<=", report_date)
    branch_filter = _coerce_list(branches)
    if branch_filter and has_branch_column:
        filters["branch"] = ("in", branch_filter)
    bank_filter = _coerce_list(bank_accounts)
    if bank_filter:
        filters["bank_account"] = ("in", bank_filter)

    fields = [
        "name",
        "bank_account",
        "transaction_date",
        "deposit",
        "withdrawal",
        "reference_number",
    ]
    if has_branch_column:
        fields.insert(1, "branch")

    rows = frappe.get_all(
        "Bank Transaction",
        filters=filters,
        fields=fields,
        order_by="transaction_date asc",
    )

    transactions: list[dict[str, object]] = []
    for row in rows:
        branch = row.get("branch") or "Unassigned"
        direction = "in" if _as_amount(row.get("deposit")) > 0 else "out"
        amount = _as_amount(row.get("deposit") or row.get("withdrawal"))
        transactions.append(
            {
                "branch": branch,
                "amount": amount,
                "direction": direction,
                "reference": row.get("reference_number") or row.get("name"),
                "posting_date": row.get("transaction_date"),
                "bank_account": row.get("bank_account"),
            }
        )
    return transactions


def fetch_cash_ledger_entries(
    report_date: date | None,
    *,
    branches: Sequence[str] | None = None,
    cash_accounts: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Fetch cash ledger entries up to and including the report date."""

    if not getattr(frappe, "db", None):
        return []

    account_filter = _coerce_list(cash_accounts)
    if not account_filter:
        return []

    has_branch_column = True
    if hasattr(frappe.db, "has_column"):
        has_branch_column = frappe.db.has_column("GL Entry", "branch")

    has_is_cancelled = True
    if hasattr(frappe.db, "has_column"):
        has_is_cancelled = frappe.db.has_column("GL Entry", "is_cancelled")

    filters = {"account": ("in", account_filter)}
    if report_date:
        filters["posting_date"] = ("<=", report_date)
    if has_is_cancelled:
        filters["is_cancelled"] = 0
    branch_filter = _coerce_list(branches)
    if branch_filter and has_branch_column:
        filters["branch"] = ("in", branch_filter)

    fields = [
        "name",
        "account",
        "posting_date",
        "debit",
        "credit",
        "voucher_no",
    ]
    if has_branch_column:
        fields.insert(1, "branch")

    rows = frappe.get_all(
        "GL Entry",
        filters=filters,
        fields=fields,
        order_by="posting_date asc",
    )

    transactions: list[dict[str, object]] = []
    for row in rows:
        debit = _as_amount(row.get("debit"))
        credit = _as_amount(row.get("credit"))
        direction = "in" if debit > 0 else "out"
        amount = debit if debit > 0 else credit
        transactions.append(
            {
                "branch": row.get("branch") or "Unassigned",
                "amount": amount,
                "direction": direction,
                "reference": row.get("voucher_no") or row.get("name"),
                "posting_date": row.get("posting_date"),
                "bank_account": row.get("account"),
            }
        )
    return transactions


def derive_opening_balances(
    transactions: Iterable[Mapping[str, object]], *, report_date: date | None
) -> dict[str, float]:
    """Compute opening balances per branch from transactions prior to the report date."""

    if not report_date:
        return {}

    openings: dict[str, float] = defaultdict(float)
    for tx in transactions:
        posting_date = _parse_date(tx.get("posting_date"))
        if posting_date and posting_date >= report_date:
            continue

        branch = str(tx.get("branch") or "Unassigned")
        amount = _as_amount(tx.get("amount"))
        direction = _normalise_direction(tx.get("direction"))
        signed = amount if direction == "in" else -amount
        openings[branch] += signed
    return dict(openings)


def load_daily_inputs(
    report_date: date | None,
    branches: Sequence[str] | None = None,
    bank_accounts: Sequence[str] | None = None,
    cash_accounts: Sequence[str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, float]]:
    """Return (transactions_for_day, opening_balances) for daily reporting."""

    resolved_date = report_date or date.today()
    cash_filter = _coerce_list(cash_accounts)
    if cash_filter:
        all_transactions = fetch_cash_ledger_entries(
            resolved_date,
            branches=branches,
            cash_accounts=cash_filter,
        )
    else:
        all_transactions = fetch_bank_transactions(
            resolved_date,
            branches=branches,
            bank_accounts=bank_accounts,
        )

    day_transactions: list[dict[str, object]] = []
    for tx in all_transactions:
        posting_date = _parse_date(tx.get("posting_date"))
        if posting_date and posting_date != resolved_date:
            continue
        day_transactions.append(tx)

    openings = derive_opening_balances(all_transactions, report_date=resolved_date)
    return day_transactions, openings
