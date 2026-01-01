import sys
import types

import pytest


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
frappe.db = getattr(frappe, "db", types.SimpleNamespace())
frappe.db.get_value = getattr(frappe.db, "get_value", lambda *args, **kwargs: None)
frappe.get_doc = getattr(frappe, "get_doc", lambda *args, **kwargs: None)
frappe.get_all = getattr(frappe, "get_all", lambda *args, **kwargs: [])
frappe.enqueue = getattr(frappe, "enqueue", lambda *args, **kwargs: None)
frappe.throw = getattr(frappe, "throw", lambda msg, title=None: (_ for _ in ()).throw(Exception(msg)))
frappe._ = getattr(frappe, "_", lambda msg: msg)
frappe.whitelist = getattr(frappe, "whitelist", lambda *args, **kwargs: (lambda f: f))

frappe.utils = types.SimpleNamespace(
    cint=lambda x: int(x or 0),
    flt=lambda x: float(x),
    format_value=lambda v, *_args, **_kwargs: v,
    get_site_path=lambda path: path,
)
sys.modules.setdefault("frappe.utils", frappe.utils)
sys.modules.setdefault("frappe.utils.formatters", types.SimpleNamespace(format_value=lambda v, *_a, **_k: v))
ValidationError = type("ValidationError", (Exception,), {})
frappe.exceptions = types.SimpleNamespace(ValidationError=ValidationError)
sys.modules.setdefault("frappe.exceptions", frappe.exceptions)


from imogi_finance import accounting  # noqa: E402
from imogi_finance.events import purchase_invoice  # noqa: E402
from imogi_finance import tax_invoice_ocr  # noqa: E402
from imogi_finance.tax_invoice_ocr import verify_tax_invoice  # noqa: E402


class ThrowCalled(Exception):
    pass


def test_purchase_invoice_submit_requires_verified(monkeypatch):
    monkeypatch.setattr(
        purchase_invoice,
        "get_settings",
        lambda: {"enable_tax_invoice_ocr": 1, "require_verification_before_submit_pi": 1},
    )

    def fake_throw(msg, title=None):
        raise ThrowCalled(msg)

    monkeypatch.setattr(frappe, "throw", fake_throw)

    doc = types.SimpleNamespace(ti_verification_status="Needs Review")

    with pytest.raises(ThrowCalled):
        purchase_invoice.validate_before_submit(doc)


def test_purchase_invoice_submit_allows_when_ocr_disabled(monkeypatch):
    monkeypatch.setattr(
        purchase_invoice,
        "get_settings",
        lambda: {"enable_tax_invoice_ocr": 0, "require_verification_before_submit_pi": 1},
    )

    def fake_throw(msg, title=None):
        raise ThrowCalled(msg)

    monkeypatch.setattr(frappe, "throw", fake_throw)

    doc = types.SimpleNamespace(ti_verification_status=None)

    purchase_invoice.validate_before_submit(doc)


def test_create_purchase_invoice_requires_verified_tax_invoice(monkeypatch):
    request = types.SimpleNamespace(
        docstatus=1,
        status="Approved",
        request_type="Expense",
        cost_center="CC-1",
        supplier="Supp-1",
        request_date="2024-01-01",
        supplier_invoice_date="2024-01-02",
        supplier_invoice_no="INV-1",
        currency="IDR",
        name="ER-TEST",
        project=None,
        is_ppn_applicable=0,
        is_pph_applicable=0,
        ppn_template=None,
        pph_type=None,
        items=[types.SimpleNamespace(amount=100, expense_account="EA-1")],
        ti_verification_status="Needs Review",
        linked_purchase_invoice=None,
        pending_purchase_invoice=None,
    )

    monkeypatch.setattr(frappe, "get_doc", lambda doctype, name: request)
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "COMP" if args[0] == "Cost Center" else None)
    monkeypatch.setattr(
        accounting,
        "get_settings",
        lambda: {
            "enable_tax_invoice_ocr": 1,
            "require_verification_before_create_pi_from_expense_request": 1,
        },
    )

    def fake_throw(msg, title=None):
        raise ThrowCalled(msg)

    monkeypatch.setattr(frappe, "throw", fake_throw)

    with pytest.raises(ThrowCalled):
        accounting.create_purchase_invoice_from_request("ER-TEST")


def test_create_purchase_invoice_allows_when_ocr_disabled(monkeypatch):
    request = types.SimpleNamespace(
        docstatus=1,
        status="Approved",
        request_type="Expense",
        cost_center="CC-1",
        supplier="Supp-1",
        request_date="2024-01-01",
        supplier_invoice_date="2024-01-02",
        supplier_invoice_no="INV-1",
        currency="IDR",
        name="ER-TEST",
        project=None,
        is_ppn_applicable=0,
        is_pph_applicable=0,
        ppn_template=None,
        pph_type=None,
        items=[types.SimpleNamespace(amount=100, expense_account="EA-1")],
        ti_verification_status=None,
        linked_purchase_invoice=None,
        pending_purchase_invoice=None,
    )

    monkeypatch.setattr(frappe, "get_doc", lambda doctype, name: request)
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "COMP" if args[0] == "Cost Center" else None)
    monkeypatch.setattr(
        accounting,
        "get_settings",
        lambda: {
            "enable_tax_invoice_ocr": 0,
            "require_verification_before_create_pi_from_expense_request": 1,
        },
    )

    created_items = []

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return types.SimpleNamespace(
            name="PI-NEW",
            docstatus=0,
            append=lambda field, row: created_items.append((field, row)),
            set_taxes=lambda: None,
            insert=lambda ignore_permissions=True: None,
        )

    monkeypatch.setattr(frappe, "new_doc", fake_new_doc, raising=False)
    monkeypatch.setattr(frappe, "msgprint", lambda *args, **kwargs: None, raising=False)

    result = accounting.create_purchase_invoice_from_request("ER-TEST")

    assert result == "PI-NEW"
    assert request.pending_purchase_invoice == "PI-NEW"
    assert not request.linked_purchase_invoice


def test_duplicate_detection_marks_flag(monkeypatch):
    doc = types.SimpleNamespace(
        name="PI-1",
        ti_fp_no="010203",
        company="Comp",
        supplier="Supp",
        taxes=[],
        ti_fp_ppn_type="Standard",
        ti_fp_dpp=100,
        ti_fp_ppn=50,
    )

    saved = {}

    def fake_save(ignore_permissions=False):
        saved["status"] = doc.ti_verification_status
        saved["notes"] = getattr(doc, "ti_verification_notes", "")

    doc.save = fake_save

    monkeypatch.setattr(
        tax_invoice_ocr,
        "get_settings",
        lambda: {"block_duplicate_fp_no": 1, "tolerance_idr": 10, "npwp_normalize": 1},
    )
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "010203")
    monkeypatch.setattr(frappe, "get_all", lambda *args, **kwargs: ["PI-OTHER"])

    result = verify_tax_invoice(doc, doctype="Purchase Invoice")

    assert result["status"] == "Needs Review"
    assert getattr(doc, "ti_duplicate_flag", 0) == 1


def test_sales_invoice_verification_uses_output_fields(monkeypatch):
    doc = types.SimpleNamespace(
        name="SI-1",
        out_fp_no="020304",
        company="Comp",
        customer="Cust",
        taxes=[],
        out_fp_ppn_type="Standard",
        out_fp_dpp=100,
        out_fp_ppn=20,
    )

    saved = {}

    def fake_save(ignore_permissions=False):
        saved["status"] = getattr(doc, "out_fp_status", None)
        saved["notes"] = getattr(doc, "out_fp_verification_notes", "")
        saved["duplicate"] = getattr(doc, "out_fp_duplicate_flag", 0)
        saved["npwp_match"] = getattr(doc, "out_fp_npwp_match", 0)

    doc.save = fake_save

    monkeypatch.setattr(
        tax_invoice_ocr,
        "get_settings",
        lambda: {"block_duplicate_fp_no": 1, "tolerance_idr": 10, "npwp_normalize": 1},
    )

    def fake_get_value(doctype, name, field):
        if doctype == "Customer" and field in ("tax_id", "npwp"):
            return "554433"
        return None

    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    def fake_get_all(doctype, *args, **kwargs):
        if doctype in {"Purchase Invoice", "Sales Invoice"}:
            return ["EXISTING"]
        return []

    monkeypatch.setattr(frappe, "get_all", fake_get_all)

    result = verify_tax_invoice(doc, doctype="Sales Invoice")

    assert result["status"] == "Needs Review"
    assert saved["duplicate"] == 1
    assert saved["npwp_match"] == 0
