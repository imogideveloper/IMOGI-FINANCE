"""Accounting helpers for IMOGI Finance."""

from __future__ import annotations

import frappe
from frappe import _

PURCHASE_INVOICE_REQUEST_TYPES = {"Expense", "Asset"}
PURCHASE_INVOICE_ALLOWED_STATUSES = frozenset({"Approved"})


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

    pi.append(
        "items",
        {
            "item_name": request.asset_name or request.description or request.expense_account,
            "description": request.description,
            "expense_account": request.expense_account,
            "cost_center": request.cost_center,
            "project": request.project,
            "qty": 1,
            "rate": request.amount,
            "amount": request.amount,
        },
    )

    if request.is_ppn_applicable and request.ppn_template:
        pi.taxes_and_charges = request.ppn_template
        pi.set_taxes()

    pi.insert(ignore_permissions=True)

    _update_request_purchase_invoice_links(request, pi)

    return pi.name
