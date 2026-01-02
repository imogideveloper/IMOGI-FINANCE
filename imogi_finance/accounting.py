"""Accounting helpers for IMOGI Finance."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.tax_invoice_ocr import get_settings

PURCHASE_INVOICE_REQUEST_TYPES = {"Expense", "Asset"}
PURCHASE_INVOICE_ALLOWED_STATUSES = frozenset({"Approved"})


def _raise_verification_error(message: str):
    marker = getattr(frappe, "ThrowMarker", None)
    throw_fn = getattr(frappe, "throw", None)

    if callable(throw_fn):
        try:
            throw_fn(message, title=_("Verification Required"))
            return
        except Exception as exc:
            if marker and not isinstance(exc, marker) and exc.__class__.__name__ != "ThrowCalled":
                raise marker(message)
            raise

    if marker:
        raise marker(message)
    raise Exception(message)


def _get_item_value(item: object, field: str):
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def summarize_request_items(
    items: list[frappe.model.document.Document] | None,
    *,
    skip_invalid_items: bool = False,
) -> tuple[float, tuple[str, ...]]:
    if not items:
        if skip_invalid_items:
            return 0.0, ()
        frappe.throw(_("Please add at least one item."))

    total = 0.0
    accounts = set()

    for item in items:
        amount = _get_item_value(item, "amount")
        if amount is None or amount <= 0:
            if skip_invalid_items:
                continue
            frappe.throw(_("Each item must have an Amount greater than zero."))

        account = _get_item_value(item, "expense_account")
        if not account:
            if skip_invalid_items:
                continue
            frappe.throw(_("Each item must have an Expense Account."))

        accounts.add(account)
        total += float(amount)

    return total, tuple(sorted(accounts))


def _sync_request_amounts(
    request: frappe.model.document.Document, total: float, expense_accounts: tuple[str, ...]
) -> None:
    updates = {}
    primary_account = expense_accounts[0] if len(expense_accounts) == 1 else None

    if getattr(request, "amount", None) != total:
        updates["amount"] = total

    if getattr(request, "expense_account", None) != primary_account:
        updates["expense_account"] = primary_account

    if updates and hasattr(request, "db_set"):
        request.db_set(updates)

    for field, value in updates.items():
        setattr(request, field, value)
    setattr(request, "expense_accounts", expense_accounts)


def _get_pph_base_amount(request: frappe.model.document.Document) -> float:
    items = getattr(request, "items", []) or []
    item_bases = [
        getattr(item, "pph_base_amount", None)
        for item in items
        if getattr(item, "is_pph_applicable", 0) and getattr(item, "pph_base_amount", None)
    ]

    if item_bases:
        return float(sum(item_bases))

    if getattr(request, "is_pph_applicable", 0) and getattr(request, "pph_base_amount", None):
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
    is_submitted = getattr(purchase_invoice, "docstatus", 0) == 1
    pending_invoice = purchase_invoice.name if mark_pending and not is_submitted else None
    linked_invoice = purchase_invoice.name if is_submitted else None

    updates = {
        "linked_purchase_invoice": linked_invoice,
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

    branch = resolve_branch(
        company=company, cost_center=request.cost_center, explicit_branch=getattr(request, "branch", None)
    )

    request_items = getattr(request, "items", []) or []
    if not request_items:
        frappe.throw(_("Expense Request must have at least one item to create a Purchase Invoice."))

    total_amount, expense_accounts = summarize_request_items(request_items)
    _sync_request_amounts(request, total_amount, expense_accounts)

    settings = get_settings()
    enforce_mode = (settings.get("enforce_mode") or "").lower()
    if settings.get("enable_budget_lock") and enforce_mode in {"approval only", "both"}:
        lock_status = getattr(request, "budget_lock_status", None)
        if lock_status not in {"Locked", "Overrun Allowed"}:
            frappe.throw(
                _("Expense Request must be budget locked before creating a Purchase Invoice. Current status: {0}").format(
                    lock_status or _("Not Locked")
                )
            )

        if getattr(request, "allocation_mode", "Direct") == "Allocated via Internal Charge":
            ic_name = getattr(request, "internal_charge_request", None)
            if not ic_name:
                frappe.throw(_("Internal Charge Request is required before creating a Purchase Invoice."))

            ic_status = frappe.db.get_value("Internal Charge Request", ic_name, "status")
            if ic_status != "Approved":
                frappe.throw(_("Internal Charge Request {0} must be Approved.").format(ic_name))

    if (
        cint(settings.get("enable_tax_invoice_ocr"))
        and cint(settings.get("require_verification_before_create_pi_from_expense_request"))
        and getattr(request, "ti_verification_status", "") != "Verified"
    ):
        _raise_verification_error(
            _("Tax Invoice must be verified before creating a Purchase Invoice from this request.")
        )

    pph_items = [item for item in request_items if getattr(item, "is_pph_applicable", 0)]
    is_ppn_applicable = bool(getattr(request, "is_ppn_applicable", 0))
    is_pph_applicable = bool(getattr(request, "is_pph_applicable", 0) or pph_items)

    pi = frappe.new_doc("Purchase Invoice")
    pi.company = company
    pi.supplier = request.supplier
    pi.posting_date = request.request_date
    pi.bill_date = request.supplier_invoice_date
    pi.bill_no = request.supplier_invoice_no
    pi.currency = request.currency
    pi.imogi_expense_request = request.name
    pi.internal_charge_request = getattr(request, "internal_charge_request", None)
    pi.imogi_request_type = request.request_type
    pi.tax_withholding_category = request.pph_type if is_pph_applicable else None
    pi.imogi_pph_type = request.pph_type
    pi.apply_tds = 1 if is_pph_applicable else 0
    pi.withholding_tax_base_amount = _get_pph_base_amount(request) if is_pph_applicable else None

    item_wise_pph_detail = {}

    for idx, item in enumerate(request_items, start=1):
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

        if getattr(item, "is_pph_applicable", 0):
            base_amount = getattr(item, "pph_base_amount", None)
            if base_amount is not None:
                item_wise_pph_detail[str(idx)] = float(base_amount)

    if item_wise_pph_detail:
        pi.item_wise_tax_detail = item_wise_pph_detail

    if is_ppn_applicable and request.ppn_template:
        pi.taxes_and_charges = request.ppn_template
        pi.set_taxes()

    # map tax invoice metadata
    pi.ti_tax_invoice_pdf = getattr(request, "ti_tax_invoice_pdf", None)
    pi.ti_fp_no = getattr(request, "ti_fp_no", None)
    pi.ti_fp_date = getattr(request, "ti_fp_date", None)
    pi.ti_fp_npwp = getattr(request, "ti_fp_npwp", None)
    pi.ti_fp_dpp = getattr(request, "ti_fp_dpp", None)
    pi.ti_fp_ppn = getattr(request, "ti_fp_ppn", None)
    pi.ti_fp_ppn_type = getattr(request, "ti_fp_ppn_type", None)
    pi.ti_verification_status = getattr(request, "ti_verification_status", None)
    pi.ti_verification_notes = getattr(request, "ti_verification_notes", None)
    pi.ti_duplicate_flag = getattr(request, "ti_duplicate_flag", None)
    pi.ti_npwp_match = getattr(request, "ti_npwp_match", None)
    apply_branch(pi, branch)

    pi.insert(ignore_permissions=True)

    _update_request_purchase_invoice_links(request, pi)

    if getattr(pi, "docstatus", 0) == 0:
        notifier = getattr(frappe, "msgprint", None)
        if notifier:
            notifier(
                _(
                    "Purchase Invoice {0} was created in Draft. Please submit it before continuing to Payment Entry."
                ).format(pi.name),
                alert=True,
            )

    return pi.name
