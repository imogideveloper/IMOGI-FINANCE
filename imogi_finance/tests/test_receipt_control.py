import sys
import types
from decimal import Decimal

import pytest


# Minimal frappe stub
frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
frappe._ = lambda msg: msg
frappe.utils = types.SimpleNamespace(fmt_money=lambda v: f"{Decimal(v):.2f}")

from imogi_finance.receipt_control import validators


def _payment_entry_info(**kwargs):
    defaults = {
        "name": "PE-TEST",
        "customer_receipt": None,
        "customer": "CUST-1",
        "company": "TC",
        "paid_amount": Decimal("100"),
        "references": [],
        "party_type": "Customer",
        "payment_type": "Receive",
    }
    defaults.update(kwargs)
    return validators.PaymentEntryInfo(**defaults)


def _receipt_info(**kwargs):
    items = kwargs.pop("items", [validators.ReceiptItem("Sales Invoice", "SINV-1", Decimal("100"))])
    defaults = {
        "name": "CR-1",
        "customer": "CUST-1",
        "company": "TC",
        "receipt_purpose": "Billing (Sales Invoice)",
        "total_amount": Decimal("100"),
        "paid_amount": Decimal("0"),
        "status": "Issued",
        "docstatus": 1,
        "items": items,
        "outstanding_amount": Decimal("100"),
    }
    defaults.update(kwargs)
    return validators.ReceiptInfo(**defaults)


def test_strict_mode_requires_receipt_link_when_open_receipts_exist():
    settings = validators.ReceiptControlSettings(enable_customer_receipt=1, receipt_mode="Mandatory Strict")
    validator = validators.ReceiptAllocationValidator(settings, open_receipts=["CR-OPEN"])

    assert validator.require_receipt_link(_payment_entry_info()) is True


def test_validate_against_receipt_rejects_over_allocation(monkeypatch):
    settings = validators.ReceiptControlSettings(enable_customer_receipt=1, receipt_mode="Mandatory Strict")
    validator = validators.ReceiptAllocationValidator(settings, reference_consumption={"SINV-1": Decimal("50")})
    pe = _payment_entry_info(references=[validators.PaymentReference("Sales Invoice", "SINV-1", Decimal("60"))])
    receipt = _receipt_info()

    with pytest.raises(validators.ReceiptValidationError):
        validator.validate_against_receipt(pe, receipt)


def test_mixed_payment_allows_external_references():
    settings = validators.ReceiptControlSettings(enable_customer_receipt=1, receipt_mode="Optional", allow_mixed_payment=1)
    validator = validators.ReceiptAllocationValidator(settings, reference_consumption={})
    pe = _payment_entry_info(
        paid_amount=Decimal("250"),
        references=[validators.PaymentReference("Sales Invoice", "SINV-OUTSIDE", Decimal("200"))],
    )
    receipt = _receipt_info()

    # Should not raise even though reference is outside receipt because mixed payments are allowed
    validator.validate_against_receipt(pe, receipt)
