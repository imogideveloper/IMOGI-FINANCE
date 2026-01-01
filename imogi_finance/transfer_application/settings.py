from __future__ import annotations

from typing import Iterable, List

import frappe
from frappe.utils import flt


REFERENCE_DOCTYPES: List[str] = [
    "Purchase Invoice",
    "Expense Claim",
    "Salary Slip",
    "Payroll Entry",
    "Journal Entry",
    "Tax Payment",
    "Tax Payment Batch",
]


def get_transfer_application_settings():
    try:
        settings = frappe.get_cached_doc("Transfer Application Settings")
    except frappe.DoesNotExistError:
        settings = frappe.new_doc("Transfer Application Settings")
        settings.enable_bank_txn_matching = 1
        settings.enable_auto_create_payment_entry_on_strong_match = 0
        settings.matching_amount_tolerance = 0
        settings.insert(ignore_permissions=True)
    except Exception:
        frappe.clear_document_cache("Transfer Application Settings")
        raise

    ensure_settings_defaults(settings)
    return settings


def ensure_settings_defaults(settings):
    if settings.enable_bank_txn_matching is None:
        settings.enable_bank_txn_matching = 1
    if settings.enable_auto_create_payment_entry_on_strong_match is None:
        settings.enable_auto_create_payment_entry_on_strong_match = 0
    if settings.matching_amount_tolerance is None:
        settings.matching_amount_tolerance = 0


def get_reference_doctype_options() -> list[str]:
    existing = set(
        frappe.get_all("DocType", filters={"name": ("in", REFERENCE_DOCTYPES)}, pluck="name")
    )
    options: list[str] = [doctype for doctype in REFERENCE_DOCTYPES if doctype in existing]
    options.append("Other")
    return options


def get_amount_tolerance(settings=None) -> float:
    settings = settings or get_transfer_application_settings()
    return flt(settings.matching_amount_tolerance or 0)


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_account(value: str | None) -> str:
    return normalize_text(value).replace(" ", "").replace("-", "")
