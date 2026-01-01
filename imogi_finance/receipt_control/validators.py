from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

import frappe
from frappe import _


@dataclass
class ReceiptControlSettings:
    enable_customer_receipt: int = 0
    receipt_mode: str = "OFF"
    allow_mixed_payment: int = 0


@dataclass
class ReceiptItem:
    reference_doctype: str
    reference_name: str
    amount_to_collect: Decimal


@dataclass
class ReceiptInfo:
    name: str
    customer: str
    company: str
    receipt_purpose: str
    total_amount: Decimal
    paid_amount: Decimal
    status: str
    docstatus: int
    items: List[ReceiptItem] = field(default_factory=list)
    outstanding_amount: Optional[Decimal] = None

    def allowed_doctype(self) -> str:
        return "Sales Invoice" if self.receipt_purpose == "Billing (Sales Invoice)" else "Sales Order"

    def remaining(self) -> Decimal:
        if self.outstanding_amount is not None:
            return Decimal(self.outstanding_amount)
        return Decimal(self.total_amount) - Decimal(self.paid_amount)


@dataclass
class PaymentReference:
    reference_doctype: str
    reference_name: str
    allocated_amount: Decimal


@dataclass
class PaymentEntryInfo:
    name: str
    customer_receipt: Optional[str]
    customer: Optional[str]
    company: Optional[str]
    paid_amount: Decimal
    references: List[PaymentReference] = field(default_factory=list)
    party_type: Optional[str] = None
    payment_type: Optional[str] = None


class ReceiptValidationError(Exception):
    """Raised when payment entry validation fails against a receipt."""


class ReceiptAllocationValidator:
    def __init__(
        self,
        settings: ReceiptControlSettings,
        open_receipts: Optional[Iterable[str]] = None,
        reference_consumption: Optional[Dict[str, Decimal]] = None,
    ) -> None:
        self.settings = settings
        self.open_receipts = list(open_receipts or [])
        self.reference_consumption = reference_consumption or {}

    def require_receipt_link(self, payment_entry: PaymentEntryInfo) -> bool:
        """Return True if strict mode requires a receipt link for this entry."""

        if not self.settings.enable_customer_receipt:
            return False
        if self.settings.receipt_mode != "Mandatory Strict":
            return False
        if payment_entry.party_type and payment_entry.party_type != "Customer":
            return False
        if payment_entry.payment_type and payment_entry.payment_type != "Receive":
            return False
        return bool(self.open_receipts)

    def validate_against_receipt(self, payment_entry: PaymentEntryInfo, receipt: ReceiptInfo) -> None:
        if receipt.docstatus == 2 or receipt.status == "Cancelled":
            raise ReceiptValidationError(_("Customer Receipt {0} is cancelled.").format(receipt.name))

        if receipt.customer != payment_entry.customer:
            raise ReceiptValidationError(
                _("Customer Receipt {0} belongs to Customer {1}." ).format(receipt.name, receipt.customer)
            )

        if receipt.company != payment_entry.company:
            raise ReceiptValidationError(
                _("Customer Receipt {0} is for Company {1}.").format(receipt.name, receipt.company)
            )

        paid_amount = Decimal(payment_entry.paid_amount or 0)
        if not self.settings.allow_mixed_payment and paid_amount > receipt.remaining():
            raise ReceiptValidationError(
                _("Payment amount {0} exceeds receipt outstanding {1}.").format(
                    frappe_format_currency(paid_amount), frappe_format_currency(receipt.remaining())
                )
            )

        allowed_doctype = receipt.allowed_doctype()
        allocated_by_reference = self._allocation_by_reference(payment_entry.references, allowed_doctype)
        available = self._available_by_reference(receipt.items, allowed_doctype)

        for reference, amount in allocated_by_reference.items():
            if reference not in available:
                if self.settings.allow_mixed_payment:
                    continue
                raise ReceiptValidationError(
                    _("Reference {0} is not part of Customer Receipt {1}.").format(reference, receipt.name)
                )
            remaining = available[reference] - self.reference_consumption.get(reference, Decimal("0"))
            if amount > remaining:
                raise ReceiptValidationError(
                    _("Allocated amount for {0} exceeds remaining {1}.").format(
                        reference, frappe_format_currency(remaining)
                    )
                )

    def _allocation_by_reference(
        self, references: Iterable[PaymentReference], allowed_doctype: str
    ) -> Dict[str, Decimal]:
        allocations: Dict[str, Decimal] = {}
        for ref in references or []:
            if ref.reference_doctype and ref.reference_doctype != allowed_doctype:
                raise ReceiptValidationError(
                    _("Only {0} references are allowed for this receipt.").format(allowed_doctype)
                )
            if not ref.reference_name:
                continue
            allocations.setdefault(ref.reference_name, Decimal("0"))
            allocations[ref.reference_name] += Decimal(ref.allocated_amount or 0)
        return allocations

    def _available_by_reference(
        self, items: Iterable[ReceiptItem], allowed_doctype: str
    ) -> Dict[str, Decimal]:
        available: Dict[str, Decimal] = {}
        for item in items or []:
            if item.reference_doctype != allowed_doctype:
                raise ReceiptValidationError(
                    _("Receipt items do not match expected doctype {0}.").format(allowed_doctype)
                )
            available[item.reference_name] = Decimal(item.amount_to_collect or 0)
        return available


def frappe_format_currency(value: Decimal) -> str:
    import frappe

    formatter = getattr(getattr(frappe, "utils", None), "fmt_money", None)
    if formatter:
        return formatter(value)
    return f"{value:.2f}"
