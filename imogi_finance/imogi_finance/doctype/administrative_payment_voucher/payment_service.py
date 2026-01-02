from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from imogi_finance.branching import apply_branch, doc_supports_branch

if TYPE_CHECKING:
    from imogi_finance.imogi_finance.doctype.administrative_payment_voucher.administrative_payment_voucher import (
        AdministrativePaymentVoucher,
        AccountDetails,
    )


def ensure_payment_entry(
    apv: "AdministrativePaymentVoucher", *, allow_draft: bool = False
) -> Tuple[Document, bool]:
    """
    Create or reuse a Payment Entry for an APV.

    Returns a tuple of (payment_entry_doc, created_flag).
    """

    apv_name = apv.name
    if not apv_name:
        apv_name = apv.insert().name

    _lock_apv(apv_name)
    apv.sync_status_with_workflow_state()
    apv._assert_payment_entry_context(allow_draft=allow_draft)

    account_map, bank_details, target_details = _get_account_map(apv)
    existing = _find_existing_payment_entry(apv)
    if existing:
        _validate_payment_entry_alignment(existing, apv, account_map)
        _submit_if_draft(existing)
        _link_payment_entry(apv, existing, created=False)
        return existing, False

    payment_entry = _build_payment_entry(apv, account_map, bank_details, target_details)
    payment_entry.insert()
    payment_entry.submit()
    _link_payment_entry(apv, payment_entry, created=True)
    return payment_entry, True


def _lock_apv(name: str) -> None:
    if not getattr(frappe, "db", None) or not getattr(frappe.db, "sql", None):
        return

    try:
        frappe.db.sql(
            "select name from `tabAdministrative Payment Voucher` where name=%s for update",
            (name,),
        )
    except Exception:
        # Locking best effort; fall back silently if database/driver does not support FOR UPDATE.
        pass


def _get_account_map(apv: "AdministrativePaymentVoucher"):
    from imogi_finance.imogi_finance.doctype.administrative_payment_voucher import (
        administrative_payment_voucher as apv_module,
    )

    bank_details = apv._get_account(apv.bank_cash_account)
    target_details = apv._get_account(apv.target_gl_account)
    account_map = apv_module.map_payment_entry_accounts(
        apv.direction, apv.amount, bank_details.name, target_details.name
    )
    return account_map, bank_details, target_details


def _find_existing_payment_entry(apv: "AdministrativePaymentVoucher") -> Optional[Document]:
    db_exists = getattr(getattr(frappe, "db", None), "exists", None)
    get_all = getattr(frappe, "get_all", None)
    get_doc = getattr(frappe, "get_doc", None)

    if apv.payment_entry and db_exists and db_exists("Payment Entry", apv.payment_entry):
        payment_entry = get_doc("Payment Entry", apv.payment_entry)
        if payment_entry.docstatus != 2:
            return payment_entry

    if get_all:
        filters = {"imogi_administrative_payment_voucher": apv.name, "docstatus": ["!=", 2]}
        existing = get_all("Payment Entry", filters=filters, limit=1)
        if existing:
            return get_doc("Payment Entry", existing[0].get("name"))

        alt_filters = {"reference_no": apv.name, "docstatus": ["!=", 2]}
        alt = get_all("Payment Entry", filters=alt_filters, limit=1)
        if alt:
            return get_doc("Payment Entry", alt[0].get("name"))

    return None


def _validate_payment_entry_alignment(payment_entry: Document, apv, account_map) -> None:
    mismatches = []
    if getattr(payment_entry, "paid_from", None) != account_map.paid_from:
        mismatches.append(_("Paid From mismatch"))
    if getattr(payment_entry, "paid_to", None) != account_map.paid_to:
        mismatches.append(_("Paid To mismatch"))
    if float(getattr(payment_entry, "paid_amount", 0) or 0) != float(account_map.paid_amount):
        mismatches.append(_("Paid Amount mismatch"))
    if float(getattr(payment_entry, "received_amount", 0) or 0) != float(account_map.received_amount):
        mismatches.append(_("Received Amount mismatch"))
    if getattr(payment_entry, "company", None) and getattr(payment_entry, "company", None) != apv.company:
        mismatches.append(_("Company mismatch"))
    if getattr(payment_entry, "posting_date", None) and getattr(payment_entry, "posting_date", None) != apv.posting_date:
        mismatches.append(_("Posting Date mismatch"))
    if getattr(payment_entry, "mode_of_payment", None) and apv.mode_of_payment:
        if getattr(payment_entry, "mode_of_payment") != apv.mode_of_payment:
            mismatches.append(_("Mode of Payment mismatch"))

    if mismatches:
        frappe.throw(
            _("Existing Payment Entry {0} does not match voucher details: {1}").format(
                payment_entry.name, ", ".join(mismatches)
            ),
            title=_("Payment Entry Conflict"),
        )


def _build_payment_entry(
    apv: "AdministrativePaymentVoucher",
    account_map,
    bank_details: "AccountDetails",
    target_details: "AccountDetails",
):
    from imogi_finance.imogi_finance.doctype.administrative_payment_voucher import (
        administrative_payment_voucher as apv_module,
    )

    payment_entry = frappe.new_doc("Payment Entry")
    payment_entry.payment_type = account_map.payment_type
    payment_entry.company = apv.company
    payment_entry.posting_date = apv.posting_date
    payment_entry.paid_from = account_map.paid_from
    payment_entry.paid_to = account_map.paid_to
    payment_entry.paid_amount = account_map.paid_amount
    payment_entry.received_amount = account_map.received_amount
    payment_entry.mode_of_payment = apv.mode_of_payment
    payment_entry.reference_no = apv.name
    payment_entry.reference_date = apv.posting_date
    payment_entry.remarks = apv._build_remarks()

    if apv_module.party_required(target_details):
        payment_entry.party_type = apv.party_type
        payment_entry.party = apv.party
        if hasattr(payment_entry, "party_account"):
            payment_entry.party_account = target_details.name

    apv_module.apply_optional_dimension(payment_entry, "cost_center", apv.cost_center)

    branch = getattr(apv, "branch", None)
    if doc_supports_branch(payment_entry.doctype):
        apply_branch(payment_entry, branch)
    elif branch:
        apv_module.apply_optional_dimension(payment_entry, "branch", branch)

    if apv.reference_doctype and apv.reference_name:
        payment_entry.append(
            "references",
            {
                "reference_doctype": apv.reference_doctype,
                "reference_name": apv.reference_name,
                "allocated_amount": apv.amount,
                "cost_center": apv.cost_center,
            },
        )

    if hasattr(payment_entry, "imogi_administrative_payment_voucher"):
        payment_entry.imogi_administrative_payment_voucher = apv.name

    if hasattr(payment_entry, "set_missing_values"):
        payment_entry.set_missing_values()

    return payment_entry


def _submit_if_draft(payment_entry: Document) -> None:
    if payment_entry.docstatus == 0 and hasattr(payment_entry, "submit"):
        payment_entry.submit()


def _link_payment_entry(apv: "AdministrativePaymentVoucher", payment_entry: Document, *, created: bool) -> None:
    apv.payment_entry = payment_entry.name
    session = getattr(frappe, "session", frappe._dict(user=None))
    apv.posted_by = getattr(session, "user", None)
    apv.posted_on = now_datetime()
    updates = {"payment_entry": payment_entry.name, "posted_by": apv.posted_by, "posted_on": apv.posted_on}
    if apv.docstatus != 2:
        apv.status = "Posted"
        apv.workflow_state = "Posted"
        updates.update({"status": apv.status, "workflow_state": apv.workflow_state})
    apv.db_set(updates)

    message = (
        _("Posted Administrative Payment Voucher and created Payment Entry {0}.").format(
            payment_entry.name
        )
        if created
        else _("Linked to existing Payment Entry {0}.").format(payment_entry.name)
    )
    apv._add_timeline_comment(
        message,
        reference_doctype="Payment Entry",
        reference_name=payment_entry.name,
    )
