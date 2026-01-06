from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt


def _safe_throw(message: str):
    marker = getattr(frappe, "ThrowMarker", None)
    throw_fn = getattr(frappe, "throw", None)

    if callable(throw_fn):
        try:
            throw_fn(message)
            return
        except BaseException as exc:  # noqa: BLE001
            if (
                marker
                and isinstance(marker, type)
                and issubclass(marker, BaseException)
                and not isinstance(exc, marker)
            ):
                Combined = type("CombinedThrowMarker", (exc.__class__, marker), {})  # noqa: N806
                raise Combined(str(exc))
            raise

    if marker:
        raise marker(message)
    raise Exception(message)


class FinanceValidator:
    """Shared finance validations for amounts and tax fields."""

    @staticmethod
    def ensure_items(items: Iterable[Any]):
        if not items:
            _safe_throw(_("Please add at least one item."))

    @staticmethod
    def validate_amounts(items: Iterable[Any]) -> tuple[float, tuple[str, ...]]:
        total = 0.0
        accounts: list[str] = []
        for item in items or []:
            qty = flt(getattr(item, "qty", 0)) or 0
            rate = flt(getattr(item, "rate", 0)) or flt(getattr(item, "amount", 0))
            amount = flt(getattr(item, "amount", qty * rate))
            total += amount
            account = getattr(item, "expense_account", None)
            if account:
                accounts.append(account)
        accounts_tuple = tuple(sorted({acc for acc in accounts if acc}))
        return total, accounts_tuple

    @staticmethod
    def validate_tax_fields(doc):
        items = getattr(doc, "items", None) or []

        is_ppn_applicable = getattr(doc, "is_ppn_applicable", 0)
        if is_ppn_applicable and not getattr(doc, "ppn_template", None):
            _safe_throw(_("Please select a PPN Template when PPN is applicable."))

        item_pph_applicable = [item for item in items if getattr(item, "is_pph_applicable", 0)]
        is_pph_applicable = getattr(doc, "is_pph_applicable", 0) or bool(item_pph_applicable)
        if is_pph_applicable:
            if not getattr(doc, "pph_type", None):
                _safe_throw(_("Please select a PPh Type when PPh is applicable."))

            if getattr(doc, "is_pph_applicable", 0) and not item_pph_applicable:
                base_amount = getattr(doc, "pph_base_amount", None)
                if not base_amount or base_amount <= 0:
                    _safe_throw(_("Please enter a PPh Base Amount greater than zero when PPh is applicable."))

            for item in item_pph_applicable:
                base_amount = getattr(item, "pph_base_amount", None)
                if not base_amount or base_amount <= 0:
                    _safe_throw(
                        _("Please enter a PPh Base Amount greater than zero for item {0}.").format(
                            getattr(item, "description", None)
                            or getattr(item, "expense_account", None)
                            or getattr(item, "idx", None)
                        )
                    )


def validate_document_tax_fields(doc, method=None):
    """DocEvent wrapper to enforce PPN/PPh requirements on tax-bearing documents."""
    FinanceValidator.validate_tax_fields(doc)
