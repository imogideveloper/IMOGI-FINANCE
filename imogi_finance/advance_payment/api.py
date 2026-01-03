from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.imogi_finance.doctype.advance_payment_entry.advance_payment_entry import (
    AdvancePaymentEntry,
)

SUPPORTED_REFERENCE_DOCTYPES = {"Purchase Invoice", "Expense Claim", "Payroll Entry"}


@frappe.whitelist()
def get_available_advances(party_type: str, party: str, company: str | None = None, currency: str | None = None):
    validate_party_inputs(party_type, party)
    filters = {
        "party_type": party_type,
        "party": party,
        "docstatus": 1,
    }
    if company:
        filters["company"] = company
    if currency:
        filters["currency"] = currency

    entries = frappe.get_all(
        "Advance Payment Entry",
        filters=filters,
        fields=[
            "name",
            "posting_date",
            "company",
            "party_type",
            "party",
            "currency",
            "advance_amount",
            "allocated_amount",
            "unallocated_amount",
            "status",
        ],
        order_by="posting_date desc, name desc",
    )

    for entry in entries:
        entry.unallocated_amount = flt(entry.unallocated_amount or (entry.advance_amount or 0) - (entry.allocated_amount or 0))
    return [entry for entry in entries if flt(entry.unallocated_amount) > 0]


@frappe.whitelist()
def get_allocations_for_reference(reference_doctype: str, reference_name: str):
    if not reference_doctype or not reference_name:
        frappe.throw(_("Reference DocType and name are required."))

    rows = frappe.get_all(
        "Advance Payment Reference",
        filters={"invoice_doctype": reference_doctype, "invoice_name": reference_name},
        fields=[
            "parent",
            "invoice_doctype",
            "invoice_name",
            "allocated_amount",
            "remaining_amount",
            "reference_currency",
        ],
        order_by="modified desc",
    )

    parent_map = {}
    for row in rows:
        if row.parent in parent_map:
            continue
        parent_map[row.parent] = frappe.db.get_value(
            "Advance Payment Entry",
            row.parent,
            ["currency", "unallocated_amount", "party_type", "party"],
            as_dict=True,
        )

    for row in rows:
        parent_info = parent_map.get(row.parent) or {}
        row.update(
            {
                "advance_currency": parent_info.get("currency"),
                "advance_unallocated": parent_info.get("unallocated_amount"),
                "party_type": parent_info.get("party_type"),
                "party": parent_info.get("party"),
            }
        )

    return rows


@frappe.whitelist()
def allocate_advances(
    reference_doctype: str,
    reference_name: str,
    allocations: list | str,
    party_type: str | None = None,
    party: str | None = None,
):
    if reference_doctype not in SUPPORTED_REFERENCE_DOCTYPES:
        frappe.throw(_("Advance reconciliation is not enabled for {0}.").format(reference_doctype))

    if not allocations:
        frappe.throw(_("Please choose at least one Advance Payment Entry."))

    allocations = frappe.parse_json(allocations)
    if not isinstance(allocations, (list, tuple)) or not allocations:
        frappe.throw(_("Please choose at least one Advance Payment Entry."))

    reference_doc = frappe.get_doc(reference_doctype, reference_name)
    resolved_party_type, resolved_party = resolve_reference_party(reference_doc, party_type, party)
    validate_party_inputs(resolved_party_type, resolved_party)
    validate_reference_allocation_capacity(reference_doc, allocations)

    applied_allocations = []
    for allocation in allocations:
        advance_name = allocation.get("advance_payment_entry") or allocation.get("name")
        amount = flt(allocation.get("allocated_amount"))
        if not advance_name or amount <= 0:
            continue

        advance_doc: AdvancePaymentEntry = frappe.get_doc("Advance Payment Entry", advance_name)
        validate_advance_for_party(advance_doc, resolved_party_type, resolved_party)

        if advance_doc.docstatus != 1:
            frappe.throw(_("Advance Payment Entry {0} must be submitted before it can be allocated.").format(advance_doc.name))

        advance_doc.flags.ignore_validate_update_after_submit = True
        advance_doc.allocate_reference(
            reference_doctype,
            reference_name,
            amount,
            reference_currency=getattr(reference_doc, "currency", None),
            reference_exchange_rate=allocation.get("reference_exchange_rate")
            or getattr(reference_doc, "conversion_rate", None)
            or advance_doc.exchange_rate,
        )
        advance_doc.save(ignore_permissions=True)

        applied_allocations.append(
            {
                "advance_payment_entry": advance_doc.name,
                "allocated_amount": amount,
                "unallocated_amount": advance_doc.available_unallocated,
            }
        )

    if not applied_allocations:
        frappe.throw(_("Please enter at least one allocation amount."))

    return {"allocations": applied_allocations}


def resolve_reference_party(document, party_type: str | None, party: str | None) -> tuple[str | None, str | None]:
    if party_type and party:
        return party_type, party

    mapping = {
        "Purchase Invoice": ("Supplier", "supplier"),
        "Expense Claim": ("Employee", "employee"),
        "Payroll Entry": ("Employee", "employee"),
    }
    if document.doctype in mapping:
        resolved_type, fieldname = mapping[document.doctype]
        return resolved_type, getattr(document, fieldname, None)

    return party_type, party


def validate_party_inputs(party_type: str | None, party: str | None) -> None:
    if not party_type:
        frappe.throw(_("Party Type is required for advance allocation."))
    if not party:
        frappe.throw(_("Party is required for advance allocation."))


def validate_advance_for_party(advance: AdvancePaymentEntry, party_type: str, party: str) -> None:
    if advance.party_type != party_type:
        frappe.throw(
            _("Advance Payment Entry {0} is for {1}, not {2}.").format(
                advance.name, advance.party_type or "-", party_type
            )
        )
    if advance.party != party:
        frappe.throw(
            _("Advance Payment Entry {0} is assigned to {1}, not {2}.").format(
                advance.name,
                advance.party or _("Unknown"),
                party,
            )
        )


def release_allocations(reference_doctype: str, reference_name: str) -> None:
    links = frappe.get_all(
        "Advance Payment Reference",
        filters={"invoice_doctype": reference_doctype, "invoice_name": reference_name},
        fields=["parent"],
    )
    if not links:
        return

    for link in links:
        advance_doc: AdvancePaymentEntry = frappe.get_doc("Advance Payment Entry", link.parent)
        advance_doc.flags.ignore_validate_update_after_submit = True
        advance_doc.clear_reference_allocations(reference_doctype, reference_name)
        advance_doc.save(ignore_permissions=True)


def refresh_linked_advances(reference_doctype: str, reference_name: str) -> None:
    links = frappe.get_all(
        "Advance Payment Reference",
        filters={"invoice_doctype": reference_doctype, "invoice_name": reference_name},
        fields=["parent"],
    )
    for link in links:
        advance_doc: AdvancePaymentEntry = frappe.get_doc("Advance Payment Entry", link.parent)
        advance_doc.flags.ignore_validate_update_after_submit = True
        advance_doc._set_amounts()
        advance_doc._validate_allocations()
        advance_doc._update_status()
        advance_doc.save(ignore_permissions=True)


def on_reference_cancel(doc, method=None):
    release_allocations(doc.doctype, doc.name)


def on_reference_update(doc, method=None):
    refresh_linked_advances(doc.doctype, doc.name)


def validate_reference_allocation_capacity(document, allocations: list[dict]) -> None:
    outstanding = get_reference_outstanding_amount(document)
    if outstanding is None:
        return

    total = sum(flt(item.get("allocated_amount")) for item in allocations)
    precision = getattr(document, "precision", lambda *_: 2)("grand_total") or 2
    if flt(total, precision) - flt(outstanding, precision) > 0.005:
        frappe.throw(
            _("{0} allocations of {1} exceed outstanding amount {2}.").format(
                document.doctype,
                frappe.format_value(total, {"fieldtype": "Currency", "currency": getattr(document, "currency", None)}),
                frappe.format_value(outstanding, {"fieldtype": "Currency", "currency": getattr(document, "currency", None)}),
            )
        )


def get_reference_outstanding_amount(document) -> float | None:
    if hasattr(document, "outstanding_amount"):
        return flt(getattr(document, "outstanding_amount") or 0)

    if document.doctype == "Expense Claim":
        total = flt(getattr(document, "grand_total", None) or getattr(document, "total_sanctioned_amount", None) or 0)
        reimbursed = flt(getattr(document, "total_amount_reimbursed", None) or 0)
        advances = flt(getattr(document, "total_advance_amount", None) or getattr(document, "total_advance", None) or 0)
        return total - reimbursed - advances

    if document.doctype == "Payroll Entry":
        return flt(getattr(document, "total_deduction", None) or getattr(document, "total_payment", None) or 0)

    return None
