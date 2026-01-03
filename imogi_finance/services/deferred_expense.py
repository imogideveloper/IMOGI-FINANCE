from __future__ import annotations

from datetime import date
from typing import List

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate


@frappe.whitelist()
def generate_amortization_schedule(amount: float, periods: int, start_date) -> list[dict]:
    """Generate an amortization schedule for deferred expenses.

    Args:
        amount: Total deferred amount.
        periods: Number of amortization periods (months).
        start_date: Start date for amortization (string, date, or datetime).

    Returns:
        List of dicts with ``period``, ``posting_date``, and ``amount`` keys.
    """
    amount = flt(amount)
    if periods is None or int(periods) <= 0:
        frappe.throw(_("Deferred Periods must be greater than zero."))

    if not start_date:
        frappe.throw(_("Deferred Start Date is required for Deferred Expense."))

    start: date = getdate(start_date)

    periods = int(periods)
    base_amount = amount / periods
    schedule: List[dict] = []
    remaining = amount

    for idx in range(periods):
        # Adjust the final period to absorb rounding differences.
        period_amount = remaining if idx == periods - 1 else flt(base_amount)
        posting_date = add_months(start, idx)
        schedule.append(
            {
                "period": idx + 1,
                "posting_date": posting_date,
                "amount": period_amount,
            }
        )
        remaining -= period_amount

    return schedule
