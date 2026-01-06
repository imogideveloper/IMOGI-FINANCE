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
frappe.utils.background_jobs = types.SimpleNamespace(get_info=lambda **_kwargs: [])
sys.modules.setdefault("frappe.utils.background_jobs", frappe.utils.background_jobs)
frappe.model = types.SimpleNamespace(document=types.SimpleNamespace(Document=type("Document", (), {})))
sys.modules.setdefault("frappe.model", frappe.model)
sys.modules.setdefault("frappe.model.document", frappe.model.document)
ValidationError = type("ValidationError", (Exception,), {})
frappe.exceptions = types.SimpleNamespace(ValidationError=ValidationError)
sys.modules.setdefault("frappe.exceptions", frappe.exceptions)


from imogi_finance import accounting  # noqa: E402
from imogi_finance.events import purchase_invoice  # noqa: E402
from imogi_finance import tax_invoice_ocr  # noqa: E402
from imogi_finance.tax_invoice_ocr import (  # noqa: E402
    get_linked_tax_invoice_uploads,
    get_tax_invoice_upload_context,
    get_tax_invoice_ocr_monitoring,
    validate_tax_invoice_upload_link,
    verify_tax_invoice,
)
from imogi_finance.imogi_finance.doctype.tax_invoice_ocr_monitoring import (  # noqa: E402
    tax_invoice_ocr_monitoring,
)
from imogi_finance.imogi_finance.doctype.tax_invoice_ocr_monitoring.tax_invoice_ocr_monitoring import (  # noqa: E402
    TaxInvoiceOCRMonitoring,
)


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


def test_purchase_invoice_submit_ignores_string_zero(monkeypatch):
    monkeypatch.setattr(
        purchase_invoice,
        "get_settings",
        lambda: {"enable_tax_invoice_ocr": "0", "require_verification_before_submit_pi": 1},
    )

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
    monkeypatch.setattr(accounting, "resolve_branch", lambda **_kwargs: None, raising=False)

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
    monkeypatch.setattr(accounting, "resolve_branch", lambda **_kwargs: None, raising=False)

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


def test_create_purchase_invoice_ignores_string_zero(monkeypatch):
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
            "enable_tax_invoice_ocr": "0",
            "require_verification_before_create_pi_from_expense_request": 1,
        },
    )
    monkeypatch.setattr(accounting, "resolve_branch", lambda **_kwargs: None, raising=False)

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


def test_run_ocr_validates_provider_before_queue(monkeypatch):
    monkeypatch.setattr(
        tax_invoice_ocr,
        "get_settings",
        lambda: {"enable_tax_invoice_ocr": 1, "ocr_provider": "Manual Only"},
    )

    called = {"enqueue": False, "get_doc": False}

    def fake_enqueue(*args, **kwargs):
        called["enqueue"] = True

    def fake_get_doc(*args, **kwargs):
        called["get_doc"] = True
        return types.SimpleNamespace(name="PI-1")

    monkeypatch.setattr(frappe, "enqueue", fake_enqueue)
    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)

    with pytest.raises(tax_invoice_ocr.ValidationError):
        tax_invoice_ocr.run_ocr("PI-1", "Purchase Invoice")

    assert called["enqueue"] is False
    assert called["get_doc"] is False


def test_monitor_tax_invoice_ocr_returns_doc_and_job_info(monkeypatch):
    doc = types.SimpleNamespace(
        name="PI-1",
        ti_fp_no="010203",
        ti_fp_npwp="123",
        ti_fp_ppn=11,
        ti_fp_dpp=100,
        ti_fp_ppn_type="Standard",
        ti_verification_status="Needs Review",
        ti_verification_notes="error here",
        ti_duplicate_flag=0,
        ti_npwp_match=1,
        ti_ocr_status="Queued",
        ti_ocr_confidence=0.5,
        ti_ocr_raw_json=None,
        ti_tax_invoice_pdf="/files/ti.pdf",
    )

    monkeypatch.setattr(frappe, "get_doc", lambda *_args, **_kwargs: doc)
    monkeypatch.setattr(
        tax_invoice_ocr,
        "get_settings",
        lambda: {"ocr_provider": "Manual Only", "ocr_max_retry": 2},
    )

    job_name = "tax-invoice-ocr-Purchase Invoice-PI-1"
    expected_job_name = job_name

    def fake_get_job_info(job_name):
        assert job_name == expected_job_name
        return {
            "job_name": job_name,
            "queue": "long",
            "status": "queued",
            "exc_info": None,
            "kwargs": {"name": doc.name},
        }

    monkeypatch.setattr(tax_invoice_ocr, "_get_job_info", fake_get_job_info)

    result = get_tax_invoice_ocr_monitoring("PI-1", "Purchase Invoice")

    assert result["job"]["name"] == job_name
    assert result["doc"]["ocr_status"] == "Queued"
    assert result["provider"] == "Manual Only"


def test_monitor_tax_invoice_ocr_sets_done_when_verified_without_job(monkeypatch):
    doc = types.SimpleNamespace(
        name="PI-2",
        ti_fp_no="010203",
        ti_fp_npwp="123",
        ti_fp_ppn=11,
        ti_fp_dpp=100,
        ti_fp_ppn_type="Standard",
        ti_verification_status="Verified",
        ti_verification_notes=None,
        ti_duplicate_flag=0,
        ti_npwp_match=1,
        ti_ocr_status="Queued",
        ti_ocr_confidence=0.5,
        ti_ocr_raw_json=None,
        ti_tax_invoice_pdf="/files/ti.pdf",
    )

    monkeypatch.setattr(frappe, "get_doc", lambda *_args, **_kwargs: doc)
    monkeypatch.setattr(
        tax_invoice_ocr,
        "get_settings",
        lambda: {"ocr_provider": "Manual Only", "ocr_max_retry": 2},
    )
    monkeypatch.setattr(tax_invoice_ocr, "_get_job_info", lambda *_args, **_kwargs: None)

    result = get_tax_invoice_ocr_monitoring("PI-2", "Purchase Invoice")

    assert result["doc"]["ocr_status"] == "Done"
    assert doc.ti_ocr_status == "Done"


def test_monitor_doctype_refresh_status_updates_fields(monkeypatch):
    monitor = TaxInvoiceOCRMonitoring()
    monitor.target_doctype = "Purchase Invoice"
    monitor.target_name = "PI-1"

    expected_job_name = "tax-invoice-ocr-Purchase Invoice-PI-1"

    def fake_monitoring(name, doctype):
        assert name == "PI-1"
        assert doctype == "Purchase Invoice"
        return {
            "job_name": expected_job_name,
            "provider": "Manual Only",
            "max_retry": 2,
            "doc": {
                "ocr_status": "Processing",
                "verification_status": "Needs Review",
                "verification_notes": "Queueing",
                "ocr_confidence": 0.55,
                "fp_no": "010203",
                "fp_date": "2024-01-01",
                "npwp": "123",
                "dpp": 100,
                "ppn": 11,
                "ppnbm": 0,
                "ppn_type": "Standard",
                "duplicate_flag": 0,
                "npwp_match": 1,
                "tax_invoice_pdf": "/files/ti.pdf",
                "ocr_raw_json_present": True,
                "ocr_raw_json": '{"foo": "bar"}',
            },
            "job": {
                "queue": "long",
                "status": "started",
                "exc_info": None,
                "kwargs": {"name": "PI-1"},
                "enqueued_at": "2024-01-01 00:00:00",
                "started_at": "2024-01-01 00:00:10",
                "ended_at": None,
            },
        }

    monkeypatch.setattr(tax_invoice_ocr_monitoring, "get_tax_invoice_ocr_monitoring", fake_monitoring)

    result = monitor.refresh_status()

    assert monitor.job_name == expected_job_name
    assert monitor.ocr_status == "Processing"
    assert monitor.ocr_confidence == 0.55
    assert monitor.job_kwargs.strip().startswith("{")
    assert result["job"]["status"] == "started"
    assert monitor.verification_notes == "Queueing"


def test_sync_tax_invoice_upload_updates_target(monkeypatch):
    upload = types.SimpleNamespace(
        name="TI-UP-1",
        fp_no="010203",
        fp_date="2024-01-02",
        npwp="123",
        dpp=100.0,
        ppn=11.0,
        ppnbm=0,
        ppn_type="Standard",
        verification_status="Verified",
        verification_notes="All good",
        duplicate_flag=0,
        npwp_match=1,
        ocr_status="Done",
        ocr_confidence=0.9,
        ocr_raw_json="{}",
        tax_invoice_pdf="/files/ti.pdf",
    )

    target = types.SimpleNamespace(ti_tax_invoice_upload="TI-UP-1")

    def fake_get_doc(doctype, name):
        assert name == "TI-UP-1"
        return upload if doctype == "Tax Invoice OCR Upload" else target

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)

    result = tax_invoice_ocr.sync_tax_invoice_upload(target, "Purchase Invoice", save=False)

    assert target.ti_fp_no == "010203"
    assert target.ti_fp_npwp == "123"
    assert target.ti_fp_dpp == 100.0
    assert target.ti_fp_ppn == 11.0
    assert target.ti_verification_status == "Verified"
    assert result["upload"] == "TI-UP-1"


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


def test_get_linked_tax_invoice_uploads_includes_branch(monkeypatch):
    def fake_get_all(doctype, **kwargs):
        if doctype == "Purchase Invoice":
            return ["PI-UPLOAD"]
        if doctype == "Expense Request":
            return ["ER-UPLOAD"]
        if doctype == "Branch Expense Request":
            return ["BER-UPLOAD"]
        return []

    monkeypatch.setattr(frappe, "get_all", fake_get_all)

    linked = get_linked_tax_invoice_uploads()

    assert linked == {"PI-UPLOAD", "ER-UPLOAD", "BER-UPLOAD"}


def test_validate_tax_invoice_upload_link_blocks_reuse(monkeypatch):
    doc = types.SimpleNamespace(name="PI-1", ti_tax_invoice_upload="UPL-1", ti_fp_no="0101")

    monkeypatch.setattr(
        tax_invoice_ocr, "get_settings", lambda: {"enable_tax_invoice_ocr": 1, "ocr_provider": "Google Vision"}
    )
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "Verified")

    def fake_get_all(doctype, **kwargs):
        if doctype == "Expense Request":
            return ["ER-1"]
        return []

    monkeypatch.setattr(frappe, "get_all", fake_get_all)

    with pytest.raises(tax_invoice_ocr.ValidationError):
        validate_tax_invoice_upload_link(doc, "Purchase Invoice")


def test_validate_tax_invoice_upload_link_requires_verified(monkeypatch):
    doc = types.SimpleNamespace(name="PI-2", ti_tax_invoice_upload="UPL-2", ti_fp_no="0202")

    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "Needs Review")
    monkeypatch.setattr(frappe, "get_all", lambda *args, **kwargs: [])

    with pytest.raises(tax_invoice_ocr.ValidationError):
        validate_tax_invoice_upload_link(doc, "Purchase Invoice")


def test_get_tax_invoice_upload_context_reports_used_uploads(monkeypatch):
    monkeypatch.setattr(
        tax_invoice_ocr, "get_settings", lambda: {"enable_tax_invoice_ocr": 1, "ocr_provider": "Google Vision"}
    )
    monkeypatch.setattr(
        tax_invoice_ocr,
        "get_linked_tax_invoice_uploads",
        lambda exclude_doctype=None, exclude_name=None: {"UP-1", "UP-2"},
    )
    monkeypatch.setattr(
        frappe,
        "get_all",
        lambda doctype, **kwargs: [
            {
                "name": "UP-3",
                "fp_no": "0303",
                "fp_date": "2024-04-01",
                "npwp": "123",
                "dpp": 1000,
                "ppn": 110,
                "ppnbm": 0,
                "ppn_type": "Standard",
            }
        ]
        if doctype == "Tax Invoice OCR Upload"
        else [],
    )

    context = get_tax_invoice_upload_context("Purchase Invoice", "PI-CTX-1")

    assert context["enable_tax_invoice_ocr"] == 1
    assert context["ocr_provider"] == "Google Vision"
    assert set(context["used_uploads"]) == {"UP-1", "UP-2"}
    assert context["verified_uploads"] == [
        {
            "name": "UP-3",
            "fp_no": "0303",
            "fp_date": "2024-04-01",
            "npwp": "123",
            "dpp": 1000,
            "ppn": 110,
            "ppnbm": 0,
            "ppn_type": "Standard",
        }
    ]


def test_manual_mode_requires_upload_when_numbers_filled(monkeypatch):
    doc = types.SimpleNamespace(name="PI-4", ti_tax_invoice_upload=None, ti_fp_no="0404", ti_fp_dpp=100, ti_fp_ppn=10)

    monkeypatch.setattr(
        tax_invoice_ocr, "get_settings", lambda: {"enable_tax_invoice_ocr": 1, "ocr_provider": "Manual Only"}
    )

    with pytest.raises(tax_invoice_ocr.ValidationError):
        validate_tax_invoice_upload_link(doc, "Purchase Invoice")


def test_manual_mode_allows_with_upload(monkeypatch):
    doc = types.SimpleNamespace(name="PI-5", ti_tax_invoice_upload="UP-MAN", ti_fp_no="0505", ti_fp_dpp=100, ti_fp_ppn=10)

    monkeypatch.setattr(
        tax_invoice_ocr, "get_settings", lambda: {"enable_tax_invoice_ocr": 1, "ocr_provider": "Manual Only"}
    )
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "Verified")
    monkeypatch.setattr(frappe, "get_all", lambda *args, **kwargs: [])

    validate_tax_invoice_upload_link(doc, "Purchase Invoice")
