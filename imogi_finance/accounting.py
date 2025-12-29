"""Accounting helpers for IMOGI Finance."""

from __future__ import annotations

import frappe
from frappe import _

PURCHASE_INVOICE_REQUEST_TYPES = {"Expense", "Asset"}
PURCHASE_INVOICE_ALLOWED_STATUSES = frozenset({"Approved"})


def summarize_request_items(items: list[frappe.model.document.Document] | None) -> tuple[float, str]:
    if not items:
        frappe.throw(_("Please add at least one item."))

    total = 0.0
    accounts = set()

    for item in items:
        amount = getattr(item, "amount", None)
        if amount is None or amount <= 0:
            frappe.throw(_("Each item must have an Amount greater than zero."))

        account = getattr(item, "expense_account", None)
        if not account:
            frappe.throw(_("Each item must have an Expense Account."))

        accounts.add(account)
        total += amount

    if len(accounts) > 1:
        frappe.throw(_("All items must use the same Expense Account to match the approval route."))

    return total, accounts.pop()


def _sync_request_amounts(
    request: frappe.model.document.Document, total: float, expense_account: str
) -> None:
    updates = {}

    if getattr(request, "amount", None) != total:
        updates["amount"] = total

    if getattr(request, "expense_account", None) != expense_account:
        updates["expense_account"] = expense_account

    if updates and hasattr(request, "db_set"):
        request.db_set(updates)

    for field, value in updates.items():
        setattr(request, field, value)


def _get_pph_base_amount(request: frappe.model.document.Document) -> float:
    if request.is_pph_applicable and request.pph_base_amount:
        return request.pph_base_amount
    return request.amount


def _validate_request_ready_for_link(request: frappe.model.document.Document) -> None:
    if request.docstatus != 1 or request.status not in PURCHASE_INVOICE_ALLOWED_STATUSES:
        frappe.throw(
            _("Expense Request must be submitted and have status {0} before creating accounting entries.").format(
                ", ".join(sorted(PURCHASE_INVOICE_ALLOWED_STATUSES))
            )
        )


def _validate_request_type(
    request: frappe.model.document.Document, allowed_types: set[str], action: str
) -> None:
    if request.request_type not in allowed_types:
        frappe.throw(
            _("{0} can only be created for request type(s): {1}").format(
                action, ", ".join(sorted(allowed_types))
            )
        )


def _validate_no_existing_purchase_invoice(request: frappe.model.document.Document) -> None:
    if request.linked_purchase_invoice:
        frappe.throw(
            _("Expense Request is already linked to Purchase Invoice {0}.").format(
                request.linked_purchase_invoice
            )
        )

    pending_pi = getattr(request, "pending_purchase_invoice", None)
    if pending_pi:
        frappe.throw(
            _("Expense Request already has draft Purchase Invoice {0}. Submit or cancel it before creating another.").format(
                pending_pi
            )
        )


def _update_request_purchase_invoice_links(
    request: frappe.model.document.Document,
    purchase_invoice: frappe.model.document.Document,
    mark_pending: bool = True,
) -> None:
    pending_invoice = None
    if mark_pending and getattr(purchase_invoice, "docstatus", 0) == 0:
        pending_invoice = purchase_invoice.name

    updates = {
        "linked_purchase_invoice": purchase_invoice.name,
        "pending_purchase_invoice": pending_invoice,
    }

    if hasattr(request, "db_set"):
        request.db_set(updates)

    for field, value in updates.items():
        setattr(request, field, value)


@frappe.whitelist()
def create_purchase_invoice_from_request(expense_request_name: str) -> str:
    """Create a Purchase Invoice from an Expense Request and return its name."""
    request = frappe.get_doc("Expense Request", expense_request_name)
    _validate_request_ready_for_link(request)
    _validate_request_type(request, PURCHASE_INVOICE_REQUEST_TYPES, _("Purchase Invoice"))
    _validate_no_existing_purchase_invoice(request)

    company = frappe.db.get_value("Cost Center", request.cost_center, "company")
    if not company:
        frappe.throw(_("Unable to resolve company from the selected Cost Center."))

    request_items = getattr(request, "items", []) or []
    if not request_items:
        frappe.throw(_("Expense Request must have at least one item to create a Purchase Invoice."))

    total_amount, expense_account = summarize_request_items(request_items)
    _sync_request_amounts(request, total_amount, expense_account)

    pi = frappe.new_doc("Purchase Invoice")
    pi.company = company
    pi.supplier = request.supplier
    pi.posting_date = request.request_date
    pi.bill_date = request.supplier_invoice_date
    pi.bill_no = request.supplier_invoice_no
    pi.currency = request.currency
    pi.imogi_expense_request = request.name
    pi.imogi_request_type = request.request_type
    pi.tax_withholding_category = request.pph_type if request.is_pph_applicable else None
    pi.imogi_pph_type = request.pph_type
    pi.apply_tds = 1 if request.is_pph_applicable else 0
    pi.withholding_tax_base_amount = _get_pph_base_amount(request) if request.is_pph_applicable else None

    for item in request_items:
        pi.append(
            "items",
            {
                "item_name": getattr(item, "asset_name", None)
                or getattr(item, "description", None)
                or getattr(item, "expense_account", None),
                "description": getattr(item, "asset_description", None)
                or getattr(item, "description", None),
                "expense_account": getattr(item, "expense_account", None),
                "cost_center": request.cost_center,
                "project": request.project,
                "qty": 1,
                "rate": getattr(item, "amount", None),
                "amount": getattr(item, "amount", None),
            },
        )

    if request.is_ppn_applicable and request.ppn_template:
        pi.taxes_and_charges = request.ppn_template
        pi.set_taxes()

    pi.insert(ignore_permissions=True)

    _update_request_purchase_invoice_links(request, pi)

    return pi.name
