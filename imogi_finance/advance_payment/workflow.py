from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.advance_payment.api import release_allocations
from imogi_finance.imogi_finance.doctype.advance_payment_entry.advance_payment_entry import (
    AdvancePaymentEntry,
)

ALLOWED_PARTIES = {"Supplier", "Employee"}


def on_payment_entry_validate(doc, method=None):
    if not is_advance_payment(doc):
        return

    if not doc.party:
        frappe.throw(_("Party is required for advance payments."))

    if doc.party_type not in ALLOWED_PARTIES:
        frappe.throw(_("Advance Payment is only supported for Supplier or Employee."))

    amount = get_payment_amount(doc)
    if flt(amount) <= 0:
        frappe.throw(_("Advance Payment amount must be greater than zero."))


def on_payment_entry_submit(doc, method=None):
    if not is_advance_payment(doc):
        return

    upsert_advance_payment(doc)


def on_payment_entry_update_after_submit(doc, method=None):
    if not is_advance_payment(doc):
        return

    upsert_advance_payment(doc)


def on_payment_entry_cancel(doc, method=None):
    name = frappe.db.get_value("Advance Payment Entry", {"payment_entry": doc.name})
    if not name:
        return

    advance = frappe.get_doc("Advance Payment Entry", name)
    advance.flags.ignore_permissions = True
    advance.flags.ignore_validate_update_after_submit = True

    # Clear any allocations before cancelling the advance
    for row in list(advance.references or []):
        release_allocations(row.invoice_doctype, row.invoice_name)

    if advance.docstatus == 1:
        advance.cancel()
    else:
        advance.delete()


def upsert_advance_payment(doc) -> AdvancePaymentEntry:
    amount = get_payment_amount(doc)
    currency, exchange_rate = get_currency_and_rate(doc)

    existing_name = frappe.db.get_value("Advance Payment Entry", {"payment_entry": doc.name})
    if existing_name:
        advance: AdvancePaymentEntry = frappe.get_doc("Advance Payment Entry", existing_name)
        advance.flags.ignore_permissions = True
        advance.flags.ignore_validate_update_after_submit = True
        advance.posting_date = doc.posting_date
        advance.company = doc.company
        advance.party_type = doc.party_type
        advance.party = doc.party
        advance.currency = currency
        advance.exchange_rate = exchange_rate
        advance.advance_amount = amount
        advance._set_defaults()
        advance._set_amounts()
        advance._validate_allocations()
        advance._update_status()
        advance.save()
        if advance.docstatus == 0 and doc.docstatus == 1:
            advance.submit()
        return advance

    advance = frappe.get_doc(
        {
            "doctype": "Advance Payment Entry",
            "posting_date": doc.posting_date,
            "company": doc.company,
            "party_type": doc.party_type,
            "party": doc.party,
            "currency": currency,
            "exchange_rate": exchange_rate,
            "advance_amount": amount,
            "payment_entry": doc.name,
        }
    )
    advance.flags.ignore_permissions = True
    advance.insert()
    if doc.docstatus == 1:
        advance.submit()
    return advance


def is_advance_payment(doc) -> bool:
    if getattr(doc, "docstatus", 0) == 2:
        return False

    if doc.doctype != "Payment Entry":
        return False

    if doc.payment_type not in {"Pay", "Receive"}:
        return False

    if doc.party_type not in ALLOWED_PARTIES:
        return False

    # Treat payments without invoice references as advances
    references = getattr(doc, "references", None) or []
    has_reference_links = any(ref.get("reference_name") for ref in references)
    return not has_reference_links


def get_payment_amount(doc) -> float:
    if doc.payment_type == "Receive":
        return flt(getattr(doc, "received_amount", 0))
    return flt(getattr(doc, "paid_amount", 0))


def get_currency_and_rate(doc) -> tuple[str | None, float]:
    if doc.payment_type == "Receive":
        currency = getattr(doc, "paid_to_account_currency", None) or getattr(doc, "target_currency", None)
        rate = flt(getattr(doc, "target_exchange_rate", None) or getattr(doc, "conversion_rate", None) or 1)
    else:
        currency = getattr(doc, "paid_from_account_currency", None) or getattr(doc, "source_currency", None)
        rate = flt(getattr(doc, "source_exchange_rate", None) or getattr(doc, "conversion_rate", None) or 1)

    return currency or getattr(doc, "party_account_currency", None) or getattr(doc, "company_currency", None), rate or 1.0
