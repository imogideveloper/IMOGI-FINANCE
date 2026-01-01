from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable

import frappe
from frappe import _

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.receipt_control.utils import get_receipt_control_settings
from imogi_finance.receipt_control.validators import (
    PaymentEntryInfo,
    PaymentReference,
    ReceiptAllocationValidator,
    ReceiptControlSettings,
    ReceiptInfo,
    ReceiptItem,
    ReceiptValidationError,
)


def validate_customer_receipt_link(doc, method=None):
    settings_doc = get_receipt_control_settings()
    branch_settings = get_branch_settings()
    settings = ReceiptControlSettings(
        enable_customer_receipt=settings_doc.enable_customer_receipt,
        receipt_mode=settings_doc.receipt_mode,
        allow_mixed_payment=settings_doc.allow_mixed_payment,
    )

    open_receipts = []
    if settings.enable_customer_receipt and settings.receipt_mode == "Mandatory Strict":
        open_receipts = _get_open_receipts(doc)

    validator = ReceiptAllocationValidator(settings, open_receipts)
    payment_entry = _as_payment_entry_info(doc)

    if validator.require_receipt_link(payment_entry) and not payment_entry.customer_receipt:
        frappe.throw(
            _(
                "Customer Receipt is required because open receipts exist for this customer in strict mode."
            )
        )

    if not payment_entry.customer_receipt:
        return

    receipt = _get_receipt_info(payment_entry.customer_receipt)
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            payment_entry.branch,
            receipt.branch,
            label=_("Payment Entry branch"),
        )
    validator.reference_consumption = _get_reference_consumption(receipt.name)

    try:
        validator.validate_against_receipt(payment_entry, receipt)
    except ReceiptValidationError as exc:
        frappe.throw(str(exc))


def record_payment_entry(doc, method=None):
    if not getattr(doc, "customer_receipt", None):
        return

    receipt = frappe.get_doc("Customer Receipt", doc.customer_receipt)
    payments = receipt.get("payments") or []
    existing = None
    for row in payments:
        if row.payment_entry == doc.name:
            existing = row
            break

    new_paid_amount = getattr(doc, "paid_amount", 0) or getattr(doc, "received_amount", 0)
    if existing:
        existing.paid_amount = new_paid_amount
        existing.posting_date = doc.posting_date
    else:
        receipt.append(
            "payments",
            {
                "payment_entry": doc.name,
                "paid_amount": new_paid_amount,
                "posting_date": doc.posting_date,
            },
        )
    receipt.recompute_payment_state()
    receipt.flags.ignore_validate = True
    receipt.save(ignore_permissions=True)


def remove_payment_entry(doc, method=None):
    if not getattr(doc, "customer_receipt", None):
        return

    receipt = frappe.get_doc("Customer Receipt", doc.customer_receipt)
    current = receipt.get("payments") or []
    remaining = [row for row in current if row.payment_entry != doc.name]
    receipt.set("payments", remaining)
    receipt.recompute_payment_state()
    receipt.flags.ignore_validate = True
    receipt.save(ignore_permissions=True)


def _get_reference_consumption(receipt: str) -> Dict[str, Decimal]:
    payment_entries = frappe.get_all(
        "Payment Entry",
        filters={"customer_receipt": receipt, "docstatus": 1},
        pluck="name",
    )
    if not payment_entries:
        return {}

    rows = frappe.get_all(
        "Payment Entry Reference",
        fields=["reference_name", "sum(allocated_amount) as allocated_amount"],
        filters={
            "docstatus": 1,
            "parentfield": "references",
            "parenttype": "Payment Entry",
            "parent": ("in", payment_entries),
        },
        group_by="reference_name",
    )
    consumption = {}
    for row in rows:
        consumption[row.reference_name] = Decimal(row.allocated_amount or 0)
    return consumption


def _as_payment_entry_info(doc) -> PaymentEntryInfo:
    references = []
    for ref in doc.get("references", []) or []:
        references.append(
            PaymentReference(
                reference_doctype=getattr(ref, "reference_doctype", None),
                reference_name=getattr(ref, "reference_name", None),
                allocated_amount=Decimal(getattr(ref, "allocated_amount", 0) or 0),
            )
        )
    return PaymentEntryInfo(
        name=doc.name,
        customer_receipt=getattr(doc, "customer_receipt", None),
        customer=getattr(doc, "party", None),
        company=getattr(doc, "company", None),
        branch=getattr(doc, "branch", None),
        party_type=getattr(doc, "party_type", None),
        payment_type=getattr(doc, "payment_type", None),
        paid_amount=Decimal(getattr(doc, "paid_amount", 0) or getattr(doc, "received_amount", 0) or 0),
        references=references,
    )


def _get_receipt_info(receipt_name: str) -> ReceiptInfo:
    receipt_doc = frappe.get_doc("Customer Receipt", receipt_name)
    items = []
    allowed_doctype = "Sales Invoice" if receipt_doc.receipt_purpose == "Billing (Sales Invoice)" else "Sales Order"
    for row in receipt_doc.get("items") or []:
        reference = row.sales_invoice if allowed_doctype == "Sales Invoice" else row.sales_order
        items.append(
            ReceiptItem(
                reference_doctype=allowed_doctype,
                reference_name=reference,
                amount_to_collect=Decimal(row.amount_to_collect or 0),
            )
        )
    return ReceiptInfo(
        name=receipt_doc.name,
        customer=receipt_doc.customer,
        company=receipt_doc.company,
        branch=getattr(receipt_doc, "branch", None),
        receipt_purpose=receipt_doc.receipt_purpose,
        total_amount=Decimal(receipt_doc.total_amount or 0),
        paid_amount=Decimal(receipt_doc.paid_amount or 0),
        outstanding_amount=Decimal(receipt_doc.outstanding_amount or 0),
        status=receipt_doc.status,
        docstatus=receipt_doc.docstatus,
        items=items,
    )


def _get_open_receipts(doc) -> Iterable[str]:
    filters = {
        "customer": getattr(doc, "party", None),
        "company": getattr(doc, "company", None),
        "status": ("in", ["Issued", "Partially Paid"]),
        "docstatus": 1,
        "outstanding_amount": (">", 0),
    }
    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and getattr(doc, "branch", None):
        filters["branch"] = getattr(doc, "branch", None)

    return frappe.get_all(
        "Customer Receipt",
        filters=filters,
        pluck="name",
    )
