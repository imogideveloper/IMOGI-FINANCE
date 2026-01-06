from __future__ import annotations

import re
from typing import Iterable

import frappe
from frappe import _

from imogi_finance.tax_invoice_ocr import normalize_npwp

SYNC_PENDING = "Pending Sync"
SYNC_ERROR = "Error"
SYNC_SUCCESS = "Synced"

ValidationError = getattr(frappe, "ValidationError", Exception)


class TaxInvoiceSyncError(ValidationError):
    """Raised when tax invoice sync validation fails."""


TAX_INVOICE_NO_PATTERN = re.compile(r"\d{16}")


def _normalize(value: str | None) -> str | None:
    return normalize_npwp(value or "") if value else None


def _safe_getattr(obj, key: str):
    return getattr(obj, key, None) if obj else None


def _get_sales_invoice_npwp(si) -> str | None:
    candidates: Iterable[str] = (
        _safe_getattr(si, "out_fp_npwp"),
        _safe_getattr(si, "out_buyer_tax_id"),
        _safe_getattr(si, "tax_id"),
    )
    for candidate in candidates:
        if candidate:
            return _normalize(candidate)
    return None


def _update_document_fields(doc, updates: dict[str, object]):
    if not doc:
        return

    for field, value in updates.items():
        try:
            setattr(doc, field, value)
        except Exception:
            pass

    try:
        frappe.db.set_value(doc.doctype, doc.name, updates, update_modified=True)
    except Exception:
        pass


def _validate_linked_sales_invoice(upload):
    if not upload.linked_sales_invoice:
        frappe.throw(_("Linked Sales Invoice is required for sync."))

    if not frappe.db.exists("Sales Invoice", upload.linked_sales_invoice):
        frappe.throw(_("Linked Sales Invoice {0} was not found.").format(upload.linked_sales_invoice))


def _validate_npwp_matches(upload, sales_invoice):
    upload_npwp = _normalize(upload.customer_npwp)
    sales_npwp = _get_sales_invoice_npwp(sales_invoice)

    if sales_npwp and upload_npwp and sales_npwp != upload_npwp:
        raise TaxInvoiceSyncError(_("Customer NPWP does not match the Sales Invoice record."))


def _prepare_sales_invoice_updates(upload) -> dict[str, object]:
    return {
        "synch_status": SYNC_SUCCESS,
        "out_fp_no": upload.tax_invoice_no,
        "out_fp_date": upload.tax_invoice_date,
        "out_fp_npwp": upload.customer_npwp,
        "out_buyer_tax_id": upload.customer_npwp,
        "out_fp_dpp": upload.dpp,
        "out_fp_ppn": upload.ppn,
        "out_fp_tax_invoice_pdf": upload.invoice_pdf,
    }


def _mark_upload_status(upload, status: str, message: str | None = None):
    updates = {"status": status, "sync_error": message or None}
    _update_document_fields(upload, updates)


def _mark_sales_invoice_status(sales_invoice, status: str):
    _update_document_fields(sales_invoice, {"synch_status": status})


def _get_upload_doc(upload) -> object:
    if hasattr(upload, "doctype"):
        return upload
    return frappe.get_doc("Tax Invoice Upload", upload)


def _validate_upload_fields(upload):
    if not upload.tax_invoice_no:
        frappe.throw(_("Tax Invoice Number is required."))

    if not TAX_INVOICE_NO_PATTERN.fullmatch(upload.tax_invoice_no or ""):
        frappe.throw(_("Tax Invoice Number must be exactly 16 digits."))

    if not upload.tax_invoice_date:
        frappe.throw(_("Tax Invoice Date is required."))

    if not upload.customer_npwp:
        frappe.throw(_("Customer NPWP is required."))

    if not upload.invoice_pdf:
        frappe.throw(_("Tax Invoice PDF is required."))


def _ensure_flags():
    if not hasattr(frappe, "flags") or frappe.flags is None:
        frappe.flags = frappe._dict()


def sync_tax_invoice_with_sales(upload, *, fail_silently: bool = False) -> dict[str, object] | None:
    upload_doc = _get_upload_doc(upload)
    _ensure_flags()
    previous_flag = getattr(frappe.flags, "in_tax_invoice_upload_sync", False)
    frappe.flags.in_tax_invoice_upload_sync = True
    sales_invoice = None
    try:
        _validate_linked_sales_invoice(upload_doc)
        _validate_upload_fields(upload_doc)
        sales_invoice = frappe.get_doc("Sales Invoice", upload_doc.linked_sales_invoice)
        _mark_sales_invoice_status(sales_invoice, SYNC_PENDING)
        _validate_npwp_matches(upload_doc, sales_invoice)
        updates = _prepare_sales_invoice_updates(upload_doc)
        _update_document_fields(sales_invoice, updates)
        _mark_upload_status(upload_doc, SYNC_SUCCESS, None)
        return {
            "upload": upload_doc.name,
            "sales_invoice": sales_invoice.name,
            "status": SYNC_SUCCESS,
        }
    except Exception as exc:
        _mark_upload_status(upload_doc, SYNC_ERROR, str(exc))
        if sales_invoice:
            _mark_sales_invoice_status(sales_invoice, SYNC_ERROR)
        if fail_silently:
            return {
                "upload": upload_doc.name,
                "sales_invoice": getattr(sales_invoice, "name", upload_doc.linked_sales_invoice),
                "status": SYNC_ERROR,
                "error": str(exc),
            }
        raise
    finally:
        frappe.flags.in_tax_invoice_upload_sync = previous_flag


def _get_latest_upload_name(sales_invoice: str) -> str | None:
    return frappe.db.get_value(
        "Tax Invoice Upload",
        {"linked_sales_invoice": sales_invoice},
        "name",
        order_by="modified desc",
    )


@frappe.whitelist()
def check_sales_invoice_tax_invoice_status(sales_invoice: str) -> dict[str, object]:
    if not sales_invoice:
        frappe.throw(_("Sales Invoice is required."))

    upload_name = _get_latest_upload_name(sales_invoice)
    if not upload_name:
        return {
            "sales_invoice": sales_invoice,
            "status": SYNC_PENDING,
            "message": _("No Tax Invoice Upload found for this Sales Invoice."),
        }

    sync_tax_invoice_with_sales(upload_name, fail_silently=True)
    upload = frappe.get_doc("Tax Invoice Upload", upload_name)
    status = upload.status or SYNC_PENDING
    synch_status = frappe.db.get_value("Sales Invoice", sales_invoice, "synch_status")

    return {
        "upload": upload.name,
        "sales_invoice": sales_invoice,
        "status": status,
        "synch_status": synch_status or status,
        "tax_invoice_no": upload.tax_invoice_no,
        "tax_invoice_date": upload.tax_invoice_date,
        "customer_npwp": upload.customer_npwp,
        "invoice_pdf": upload.invoice_pdf,
        "sync_error": upload.sync_error,
    }


def sync_pending_tax_invoices():
    pending_uploads = frappe.get_all(
        "Tax Invoice Upload",
        filters={"status": ["in", ["Draft", SYNC_ERROR]]},
        pluck="name",
    )

    for upload_name in pending_uploads:
        try:
            sync_tax_invoice_with_sales(upload_name, fail_silently=True)
        except Exception:
            frappe.log_error(
                title="Tax Invoice Upload sync failed",
                message=frappe.get_traceback(),
            )
