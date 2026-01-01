from __future__ import annotations

from typing import List, Sequence

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from imogi_finance.transfer_application.payment_entries import (
    create_payment_entry_for_transfer_application,
)
from imogi_finance.transfer_application.settings import (
    get_amount_tolerance,
    get_transfer_application_settings,
    normalize_account,
    normalize_text,
)


def handle_bank_transaction(doc: Document, method=None):
    if frappe.flags.in_transfer_application_matching:
        return

    settings = get_transfer_application_settings()
    if not settings.enable_bank_txn_matching:
        return

    if doc.docstatus != 1:
        return

    frappe.flags.in_transfer_application_matching = True
    try:
        _match_transfer_application(doc, settings=settings)
    finally:
        frappe.flags.in_transfer_application_matching = False


def _match_transfer_application(doc: Document, *, settings):
    if getattr(doc, "transfer_application", None):
        return

    txn_status = getattr(doc, "status", None)
    if txn_status and txn_status not in {"Unreconciled", "Pending Reconciliation"}:
        return

    amount = _get_transaction_amount(doc)
    if not amount:
        return

    remark_text = _build_remark_text(doc)
    tolerance = get_amount_tolerance(settings)

    candidates = frappe.get_all(
        "Transfer Application",
        filters={
            "docstatus": ("<", 2),
            "payment_entry": ("is", "not set"),
            "status": ("in", ["Approved for Transfer", "Awaiting Bank Confirmation"]),
        },
        fields=[
            "name",
            "amount",
            "expected_amount",
            "account_number",
            "beneficiary_name",
            "bank_reference_hint",
        ],
    )

    strong_matches: List[dict] = []
    medium_matches: List[dict] = []
    weak_matches: List[dict] = []

    for candidate in candidates:
        expected = flt(candidate.expected_amount or candidate.amount)
        if abs(amount - expected) > tolerance:
            continue

        account_match = _account_matches(candidate.account_number, remark_text)
        hint_match = _text_matches(candidate.bank_reference_hint, remark_text)
        name_match = _text_matches(candidate.beneficiary_name, remark_text)
        ta_in_remark = _text_matches(candidate.name, remark_text)

        if account_match or hint_match or ta_in_remark:
            strong_matches.append(candidate)
        elif name_match:
            medium_matches.append(candidate)
        else:
            weak_matches.append(candidate)

    if len(strong_matches) == 1:
        _apply_strong_match(doc, strong_matches[0], amount, remark_text, settings=settings)
    elif len(strong_matches) > 1:
        _flag_manual_review(doc, strong_matches, confidence="Manual")
    elif medium_matches:
        _flag_manual_review(doc, medium_matches, confidence="Medium")
    elif weak_matches:
        _flag_manual_review(doc, weak_matches, confidence="Weak")


def _apply_strong_match(doc: Document, candidate: dict, amount: float, remark_text: str, *, settings):
    transfer_application = candidate.name
    note_parts = [_("Matched Transfer Application {0}").format(transfer_application)]

    account_match = _account_matches(candidate.get("account_number"), remark_text)
    if account_match:
        note_parts.append(_("Account number found in bank description."))
    if _text_matches(candidate.get("bank_reference_hint"), remark_text):
        note_parts.append(_("Reference hint present in bank description."))
    if _text_matches(candidate.get("beneficiary_name"), remark_text):
        note_parts.append(_("Beneficiary name present in bank description."))

    _update_bank_transaction_fields(
        doc,
        transfer_application=transfer_application,
        confidence="Strong",
        notes=" | ".join(note_parts),
    )

    ta_doc = frappe.get_doc("Transfer Application", transfer_application)
    ta_doc.add_comment(
        "Info",
        _("Linked from Bank Transaction {0} with a strong match (amount {1}).").format(
            doc.name, amount
        ),
        reference_doctype="Bank Transaction",
        reference_name=doc.name,
    )

    if not settings.enable_auto_create_payment_entry_on_strong_match:
        return

    if getattr(doc, "payment_entry", None) or getattr(doc, "payment_document", None):
        _append_match_note(doc, _("Skipped auto Payment Entry because a payment link already exists."))
        return

    if ta_doc.payment_entry:
        existing_status = frappe.db.get_value("Payment Entry", ta_doc.payment_entry, "docstatus")
        if existing_status and existing_status != 2:
            _append_match_note(
                doc,
                _(
                    "Skipped auto Payment Entry because Transfer Application already links to {0}."
                ).format(ta_doc.payment_entry),
            )
            return

    try:
        payment_entry = create_payment_entry_for_transfer_application(
            ta_doc,
            submit=True,
            posting_date=getattr(doc, "date", None) or getattr(doc, "posting_date", None),
            paid_amount=amount,
            ignore_permissions=True,
        )
    except Exception:
        frappe.log_error(
            title="Transfer Application auto Payment Entry failed",
            message=frappe.get_traceback(),
        )
        _append_match_note(doc, _("Auto Payment Entry failed; see error log."))
        return

    ta_doc.reload()
    ta_doc.db_set(
        {
            "payment_entry": payment_entry.name,
            "paid_amount": payment_entry.paid_amount,
            "paid_date": payment_entry.posting_date,
            "status": "Paid",
            "workflow_state": "Paid",
        }
    )

    ta_doc.add_comment(
        "Info",
        _(
            "Auto-created Payment Entry {0} from Bank Transaction {1}."
        ).format(payment_entry.name, doc.name),
        reference_doctype="Payment Entry",
        reference_name=payment_entry.name,
    )
    _append_match_note(
        doc,
        _(
            "Auto-created Payment Entry {0} from Transfer Application {1}."
        ).format(payment_entry.name, ta_doc.name),
    )


def _flag_manual_review(doc: Document, matches: Sequence[dict], *, confidence: str):
    names = [m.get("name") for m in matches]
    note = _(
        "Candidates: {0}. Matched by amount; review beneficiary/reference hints."
    ).format(", ".join(names))
    _update_bank_transaction_fields(
        doc,
        transfer_application=None,
        confidence=confidence,
        notes=note,
    )
    _append_match_note(doc, note)


def _update_bank_transaction_fields(doc: Document, *, transfer_application: str | None, confidence: str | None, notes: str | None):
    updates = {}
    if transfer_application:
        updates["transfer_application"] = transfer_application
    if confidence:
        updates["match_confidence"] = confidence
    if notes is not None:
        updates["match_notes"] = notes

    if updates:
        frappe.db.set_value("Bank Transaction", doc.name, updates, update_modified=False)


def _append_match_note(doc: Document, message: str):
    try:
        doc.add_comment("Info", message)
    except Exception:
        frappe.log_error(f"Failed to append note on Bank Transaction {doc.name}", frappe.get_traceback())


def _get_transaction_amount(doc: Document) -> float:
    withdrawal = flt(getattr(doc, "withdrawal", 0)) or flt(getattr(doc, "debit", 0))
    if withdrawal:
        return withdrawal

    amount = flt(getattr(doc, "amount", 0))
    if amount < 0:
        return abs(amount)

    return 0


def _build_remark_text(doc: Document) -> str:
    parts = [
        getattr(doc, "description", None),
        getattr(doc, "reference_number", None),
        getattr(doc, "party", None),
        getattr(doc, "transaction_id", None),
    ]
    text = " ".join([p for p in parts if p])
    return normalize_text(text)


def _account_matches(account_number: str | None, remark_text: str) -> bool:
    if not account_number:
        return False
    normalized = normalize_account(account_number)
    return bool(normalized and normalized in remark_text)


def _text_matches(value: str | None, remark_text: str) -> bool:
    value = normalize_text(value)
    return bool(value and value in remark_text)
