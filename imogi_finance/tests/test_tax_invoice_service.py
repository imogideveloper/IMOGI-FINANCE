import sys
import types

import pytest


frappe = sys.modules.setdefault("frappe", types.SimpleNamespace())
frappe.ValidationError = getattr(frappe, "ValidationError", type("ValidationError", (Exception,), {}))
frappe._ = getattr(frappe, "_", lambda msg: msg)
frappe.throw = getattr(frappe, "throw", lambda msg, title=None: (_ for _ in ()).throw(Exception(msg)))
frappe._dict = getattr(frappe, "_dict", lambda **kwargs: types.SimpleNamespace(**kwargs))
frappe.flags = getattr(frappe, "flags", types.SimpleNamespace())
frappe.get_traceback = getattr(frappe, "get_traceback", lambda: "traceback")

uploads = {}
sales_invoices = {}
last_logs = []


def fake_exists(doctype, name):
    if doctype == "Sales Invoice":
        return name in sales_invoices
    return False


def fake_set_value(doctype, name, values, update_modified=True):
    target = None
    if doctype == "Sales Invoice":
        target = sales_invoices.get(name)
    elif doctype == "Tax Invoice Upload":
        target = uploads.get(name)
    if target:
        for key, value in values.items():
            setattr(target, key, value)


def fake_get_value(doctype, filters, fieldname=None, order_by=None):
    if doctype == "Tax Invoice Upload" and isinstance(filters, dict):
        linked_invoice = filters.get("linked_sales_invoice")
        if linked_invoice:
            sorted_uploads = sorted(
                uploads.values(),
                key=lambda row: getattr(row, "modified", ""),
                reverse=True,
            )
            for row in sorted_uploads:
                if getattr(row, "linked_sales_invoice", None) == linked_invoice:
                    return row.name if fieldname == "name" else getattr(row, fieldname, None)
    if doctype == "Sales Invoice" and fieldname == "synch_status":
        if isinstance(filters, str):
            target = sales_invoices.get(filters)
        else:
            target = sales_invoices.get(filters.get("name"))
        return getattr(target, "synch_status", None) if target else None
    return None


def fake_get_all(doctype, filters=None, pluck=None, **kwargs):
    if doctype == "Tax Invoice Upload":
        allowed_statuses = set()
        if filters and isinstance(filters.get("status"), (list, tuple)):
            _, statuses = filters["status"]
            allowed_statuses = set(statuses)
        names = [
            name for name, row in uploads.items() if not allowed_statuses or getattr(row, "status", None) in allowed_statuses
        ]
        if pluck == "name":
            return names
        return [{"name": name} for name in names]
    return []


frappe.db = types.SimpleNamespace(
    exists=fake_exists,
    set_value=fake_set_value,
    get_value=fake_get_value,
    get_all=fake_get_all,
)
frappe.get_all = fake_get_all


def fake_get_doc(doctype, name):
    if doctype == "Tax Invoice Upload":
        return uploads[name]
    if doctype == "Sales Invoice":
        return sales_invoices[name]
    raise Exception(f"Unknown doctype {doctype}")


frappe.get_doc = fake_get_doc


def fake_log_error(title=None, message=None):
    last_logs.append({"title": title, "message": message})


frappe.log_error = getattr(frappe, "log_error", fake_log_error)

from imogi_finance.services import tax_invoice_service  # noqa: E402


def make_upload(name="UPLOAD-1", linked="SI-1", npwp="123456789012345"):
    upload = types.SimpleNamespace(
        doctype="Tax Invoice Upload",
        name=name,
        tax_invoice_no="1234567890123456",
        tax_invoice_date="2024-01-01",
        customer_npwp=npwp,
        dpp=100,
        ppn=11,
        invoice_pdf="/files/fp.pdf",
        linked_sales_invoice=linked,
        status="Draft",
        sync_error=None,
        modified="2024-01-01 00:00:00",
    )
    uploads[name] = upload
    return upload


def make_sales_invoice(name="SI-1", npwp=None):
    si = types.SimpleNamespace(
        doctype="Sales Invoice",
        name=name,
        synch_status=None,
        out_fp_npwp=npwp,
        out_buyer_tax_id=npwp,
    )
    sales_invoices[name] = si
    return si


def test_sync_updates_sales_invoice_fields():
    uploads.clear()
    sales_invoices.clear()
    upload = make_upload()
    sales_invoice = make_sales_invoice()

    result = tax_invoice_service.sync_tax_invoice_with_sales(upload)

    assert result["status"] == tax_invoice_service.SYNC_SUCCESS
    assert sales_invoice.out_fp_no == upload.tax_invoice_no
    assert sales_invoice.out_fp_npwp == upload.customer_npwp
    assert sales_invoice.out_buyer_tax_id == upload.customer_npwp
    assert sales_invoice.out_fp_tax_invoice_pdf == upload.invoice_pdf
    assert upload.status == tax_invoice_service.SYNC_SUCCESS
    assert upload.sync_error is None
    assert sales_invoice.synch_status == tax_invoice_service.SYNC_SUCCESS


def test_sync_marks_error_on_npwp_mismatch():
    uploads.clear()
    sales_invoices.clear()
    upload = make_upload()
    sales_invoice = make_sales_invoice(npwp="000000000000000")

    with pytest.raises(tax_invoice_service.TaxInvoiceSyncError):
        tax_invoice_service.sync_tax_invoice_with_sales(upload)

    assert upload.status == tax_invoice_service.SYNC_ERROR
    assert upload.sync_error
    assert sales_invoice.synch_status == tax_invoice_service.SYNC_ERROR


def test_check_status_handles_missing_upload():
    uploads.clear()
    sales_invoices.clear()
    make_sales_invoice()

    result = tax_invoice_service.check_sales_invoice_tax_invoice_status("SI-1")

    assert result["status"] == tax_invoice_service.SYNC_PENDING
    assert "No Tax Invoice Upload" in result["message"]


def test_sync_pending_tax_invoices_processes_queue():
    uploads.clear()
    sales_invoices.clear()
    upload = make_upload(npwp="999999999999999")
    sales_invoice = make_sales_invoice(npwp="999999999999999")

    tax_invoice_service.sync_pending_tax_invoices()

    assert upload.status == tax_invoice_service.SYNC_SUCCESS
    assert sales_invoice.synch_status == tax_invoice_service.SYNC_SUCCESS
