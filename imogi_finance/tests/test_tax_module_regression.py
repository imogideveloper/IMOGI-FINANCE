import types
from importlib import import_module

import pytest

from imogi_finance.tests._tax_discovery import (
    DOCTYPE_PERIOD_CLOSING,
    DOCTYPE_TAX_PROFILE,
    FIELDS_ER,
    FIELDS_PI,
    FIELDS_SI,
    METHODS,
    REPORTS,
)

import frappe
from imogi_finance import accounting, tax_invoice_ocr, tax_operations
from imogi_finance.events import purchase_invoice
vat_input_report = import_module(
    "imogi_finance.imogi_finance.report.vat_input_register_verified.vat_input_register_verified"
)
vat_output_report = import_module(
    "imogi_finance.imogi_finance.report.vat_output_register_verified.vat_output_register_verified"
)


class AttrDict(dict):
    """Dict with attribute access used to mimic frappe._dict in tests."""

    __getattr__ = dict.get


def test_t1_purchase_invoice_submit_blocked_when_not_verified(monkeypatch):
    if not METHODS.get("verify_purchase_invoice_tax_invoice"):
        pytest.skip("Verification method missing; feature gap")

    monkeypatch.setattr(
        purchase_invoice,
        "get_settings",
        lambda: {"enable_tax_invoice_ocr": 1, "require_verification_before_submit_pi": 1},
    )
    doc = types.SimpleNamespace(**{FIELDS_PI["status"]: "Needs Review"})

    with pytest.raises(frappe.ThrowMarker):
        purchase_invoice.validate_before_submit(doc)


def test_t2_expense_request_create_pi_blocked_when_not_verified(monkeypatch):
    if not METHODS.get("create_purchase_invoice_from_request"):
        pytest.skip("Create PI from ER missing; feature gap")

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
        items=[types.SimpleNamespace(amount=100, expense_account="EA-1", is_pph_applicable=0)],
        ti_verification_status="Needs Review",
        linked_purchase_invoice=None,
        pending_purchase_invoice=None,
    )

    monkeypatch.setattr(frappe, "get_doc", lambda *_args, **_kwargs: request)
    monkeypatch.setattr(
        frappe.db, "get_value", lambda doctype, *_args, **_kwargs: "COMP" if doctype == "Cost Center" else None
    )
    monkeypatch.setattr(
        accounting,
        "get_settings",
        lambda: {
            "enable_tax_invoice_ocr": 1,
            "require_verification_before_create_pi_from_expense_request": 1,
        },
    )
    monkeypatch.setattr(accounting, "resolve_branch", lambda **_kwargs: None, raising=False)

    with pytest.raises(frappe.ThrowMarker):
        accounting.create_purchase_invoice_from_request("ER-TEST")


def test_t3_verified_er_creates_pi_and_maps_tax_fields(monkeypatch):
    if not METHODS.get("create_purchase_invoice_from_request"):
        pytest.skip("Create PI from ER missing; feature gap")

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
        name="ER-OK",
        project=None,
        is_ppn_applicable=1,
        is_pph_applicable=0,
        ppn_template="PPN-TEMPLATE",
        pph_type=None,
        items=[types.SimpleNamespace(amount=100, expense_account="EA-1", is_pph_applicable=0)],
        linked_purchase_invoice=None,
        pending_purchase_invoice=None,
        ti_tax_invoice_pdf="file.pdf",
        ti_fp_no="010203",
        ti_fp_date="2024-01-02",
        ti_fp_npwp="123",
        ti_fp_dpp=100,
        ti_fp_ppn=11,
        ti_fp_ppn_type="Standard",
        ti_verification_status="Verified",
        ti_verification_notes="ok",
        ti_duplicate_flag=0,
        ti_npwp_match=1,
    )

    monkeypatch.setattr(frappe, "get_doc", lambda *_args, **_kwargs: request)
    monkeypatch.setattr(
        frappe.db, "get_value", lambda doctype, *_args, **_kwargs: "COMP" if doctype == "Cost Center" else None
    )
    monkeypatch.setattr(
        accounting,
        "get_settings",
        lambda: {
            "enable_tax_invoice_ocr": 1,
            "require_verification_before_create_pi_from_expense_request": 1,
        },
    )
    monkeypatch.setattr(frappe, "msgprint", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(accounting, "resolve_branch", lambda **_kwargs: None, raising=False)

    created = {}

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"

        class _PI:
            def __init__(self):
                self.docstatus = 0
                self.name = "PI-NEW"
                self.taxes_set = False

            def append(self, field, row):
                rows = getattr(self, field, [])
                rows.append(row)
                setattr(self, field, rows)

            def set_taxes(self):
                self.taxes_set = True

            def insert(self, ignore_permissions=True):
                return self

        pi = _PI()
        created["pi"] = pi
        return pi

    monkeypatch.setattr(frappe, "new_doc", fake_new_doc, raising=False)

    result = accounting.create_purchase_invoice_from_request("ER-OK")
    pi = created.get("pi")

    assert result == "PI-NEW"
    assert getattr(pi, "taxes_set") is True
    assert getattr(pi, "taxes_and_charges") == "PPN-TEMPLATE"
    assert getattr(pi, FIELDS_PI["fp_no"]) == request.ti_fp_no
    assert getattr(pi, FIELDS_PI["fp_date"]) == request.ti_fp_date
    assert getattr(pi, FIELDS_PI["npwp"]) == request.ti_fp_npwp
    assert getattr(request, "pending_purchase_invoice") == "PI-NEW"


def test_t4_duplicate_detection_for_pi_and_si(monkeypatch):
    monkeypatch.setattr(
        tax_invoice_ocr, "get_settings", lambda: {"block_duplicate_fp_no": 1, "tolerance_idr": 10, "npwp_normalize": 1}
    )
    monkeypatch.setattr(
        frappe.db, "get_value", lambda *_args, **_kwargs: None, raising=False
    )

    def fake_get_all(doctype, filters=None, **_kwargs):
        fp_field = FIELDS_PI["fp_no"] if doctype != "Sales Invoice" else FIELDS_SI["fp_no"]
        if filters and filters.get(fp_field) in {"FP-PI", "FP-SI"}:
            return ["EXISTING"]
        return []

    monkeypatch.setattr(frappe, "get_all", fake_get_all)

    pi_doc = types.SimpleNamespace(
        name="PI-1",
        company="Comp",
        taxes=[],
        ti_fp_ppn_type="Standard",
        ti_fp_dpp=100,
        ti_fp_ppn=11,
    )
    setattr(pi_doc, FIELDS_PI["fp_no"], "FP-PI")
    pi_doc.save = lambda ignore_permissions=True: None
    pi_result = tax_invoice_ocr.verify_tax_invoice(pi_doc, doctype="Purchase Invoice")

    assert getattr(pi_doc, FIELDS_PI["duplicate"]) == 1
    assert pi_result["status"] == "Needs Review"

    si_doc = types.SimpleNamespace(
        name="SI-1",
        company="Comp",
        taxes=[],
        out_fp_ppn_type="Standard",
        out_fp_dpp=200,
        out_fp_ppn=22,
    )
    setattr(si_doc, FIELDS_SI["fp_no"], "FP-SI")
    si_doc.save = lambda ignore_permissions=True: None
    si_result = tax_invoice_ocr.verify_tax_invoice(si_doc, doctype="Sales Invoice")

    assert getattr(si_doc, FIELDS_SI["duplicate"]) == 1
    assert si_result["status"] == "Needs Review"


def test_t4_expense_request_duplicate_resolves_company(monkeypatch):
    seen_filters = []

    def fake_get_value(doctype, name=None, fieldname=None):
        if doctype == "Cost Center" and fieldname == "company":
            return "COMP-CC"
        return None

    def fake_get_all(doctype, filters=None, **_kwargs):
        if filters:
            seen_filters.append(filters)
        if filters and filters.get(FIELDS_ER["fp_no"]) == "FP-ER":
            return ["MATCH"]
        return []

    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)
    monkeypatch.setattr(frappe, "get_all", fake_get_all)
    monkeypatch.setattr(
        tax_invoice_ocr, "get_settings", lambda: {"block_duplicate_fp_no": 1, "tolerance_idr": 10, "npwp_normalize": 1}
    )

    er_doc = types.SimpleNamespace(
        name="ER-1",
        cost_center="CC-1",
        taxes=[],
        ti_fp_ppn_type="Standard",
        ti_fp_dpp=100,
        ti_fp_ppn=11,
    )
    setattr(er_doc, FIELDS_ER["fp_no"], "FP-ER")
    er_doc.save = lambda ignore_permissions=True: None

    result = tax_invoice_ocr.verify_tax_invoice(er_doc, doctype="Expense Request")

    assert any(f.get("company") == "COMP-CC" for f in seen_filters if f)
    assert getattr(er_doc, FIELDS_ER["duplicate"]) == 1
    assert result["status"] == "Needs Review"


def test_t5_input_vat_register_uses_account_filter(monkeypatch):
    if not REPORTS.get("vat_input_verified"):
        pytest.skip("VAT Input register missing; feature gap")

    monkeypatch.setattr(vat_input_report, "get_settings", lambda: {"ppn_input_account": "PPN In"})

    def fake_get_all(doctype, filters=None, fields=None, **kwargs):
        if doctype == "Purchase Invoice":
            return [
                AttrDict(
                    name="PI-1",
                    posting_date="2024-01-01",
                    supplier="Supp",
                    company="Comp",
                    ti_fp_npwp="123",
                    ti_fp_no="FP-1",
                    ti_fp_date="2024-01-01",
                    ti_fp_dpp=100,
                    ti_fp_ppn=11,
                )
            ]
        if doctype == "Purchase Taxes and Charges":
            return [{"total": 11}]
        return []

    monkeypatch.setattr(frappe, "get_all", fake_get_all)

    _columns, data = vat_input_report.execute({"company": "Comp"})
    assert data[0]["tax_row_amount"] == 11


def test_t6_output_vat_register_uses_account_filter(monkeypatch):
    if not REPORTS.get("vat_output_verified"):
        pytest.skip("VAT Output register missing; feature gap")

    monkeypatch.setattr(vat_output_report, "get_settings", lambda: {"ppn_output_account": "PPN Out"})

    def fake_get_all(doctype, filters=None, fields=None, **kwargs):
        if doctype == "Sales Invoice":
            return [
                AttrDict(
                    name="SI-1",
                    posting_date="2024-01-01",
                    customer="Cust",
                    company="Comp",
                    out_buyer_tax_id="321",
                    out_fp_no="FP-2",
                    out_fp_date="2024-01-01",
                    out_fp_dpp=200,
                    out_fp_ppn=22,
                )
            ]
        if doctype == "Sales Taxes and Charges":
            return [{"total": 22}]
        return []

    monkeypatch.setattr(frappe, "get_all", fake_get_all)

    _columns, data = vat_output_report.execute({"company": "Comp"})
    assert data[0]["tax_row_amount"] == 22


def test_t7_coretax_export_includes_verified_only(monkeypatch):
    if not METHODS.get("generate_coretax_export") or not DOCTYPE_TAX_PROFILE:
        pytest.skip("CoreTax export feature missing; feature gap")

    settings = types.SimpleNamespace(
        file_format="CSV",
        column_mappings=[types.SimpleNamespace(label="Name", source_type="Document Field", source="name")],
    )

    monkeypatch.setattr(frappe, "get_cached_doc", lambda *_args, **_kwargs: settings)
    captured_filters = {}

    def fake_get_list(doctype, filters=None, fields=None):
        nonlocal captured_filters
        captured_filters = filters or {}
        return [AttrDict(name="PI-VERIFIED", supplier="Supp")]

    monkeypatch.setattr(frappe, "get_list", fake_get_list)

    captured_rows = {}
    monkeypatch.setattr(
        tax_operations,
        "_serialize_rows",
        lambda rows, headers, file_format, filename: captured_rows.update({"rows": rows, "headers": headers}) or "file-url",
    )

    url = tax_operations.generate_coretax_export(
        company="Comp",
        date_from="2024-01-01",
        date_to="2024-01-31",
        direction="Input",
        settings_name="SET-1",
        filename="test",
    )

    assert captured_filters.get(FIELDS_PI["status"]) == "Verified"
    assert captured_rows["headers"] == ["Name"]
    assert captured_rows["rows"] == [["PI-VERIFIED"]]
    assert url == "file-url"


def test_t8_tax_payment_batch_creates_native_entries(monkeypatch):
    if not METHODS.get("create_tax_payment_entry"):
        pytest.skip("Tax Payment Batch payments missing; feature gap")

    updates = {}

    class Batch(types.SimpleNamespace):
        def get(self, key, default=None):
            return getattr(self, key, default)

        def db_set(self, key, value=None):
            if isinstance(key, dict):
                updates.update(key)
            else:
                updates[key] = value

    batch = Batch(
        name="BATCH-1",
        amount=1000,
        payable_account="2100",
        payment_account="1100",
        company="Comp",
        tax_type="PPN",
        period_month=1,
        period_year=2024,
        party_type="Supplier",
        party="Supp",
        references=[],
    )

    def fake_new_doc(doctype):
        if doctype == "Payment Entry":
            class PE:
                def __init__(self):
                    self.name = "PE-1"

                def insert(self, ignore_permissions=True):
                    return self

            return PE()
        if doctype == "Journal Entry":
            class JE:
                def __init__(self):
                    self.name = "JE-1"
                    self.accounts = []

                def append(self, field, row):
                    if field == "accounts":
                        self.accounts.append(row)

                def insert(self, ignore_permissions=True):
                    return self

            return JE()
        raise ValueError("Unexpected doctype")

    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)

    pe_name = tax_operations.create_tax_payment_entry(batch)
    je_name = tax_operations.create_tax_payment_journal_entry(batch)

    assert pe_name == "PE-1"
    assert je_name == "JE-1"
    assert updates.get("payment_entry") == "PE-1"
    assert updates.get("journal_entry") == "JE-1"


def test_t9_locked_tax_period_blocks_changes(monkeypatch):
    if not DOCTYPE_PERIOD_CLOSING:
        pytest.skip("Tax Period Closing missing; feature gap")

    def fake_get_all(doctype, *args, **kwargs):
        if doctype == DOCTYPE_PERIOD_CLOSING:
            return ["TPC-1"]
        return []

    monkeypatch.setattr(frappe, "get_all", fake_get_all)

    previous = types.SimpleNamespace(
        doctype="Purchase Invoice",
        company="Comp",
        posting_date="2024-01-10",
        ti_fp_no="OLD",
        ti_fp_date=None,
        ti_fp_npwp=None,
        ti_fp_dpp=None,
        ti_fp_ppn=None,
        ti_verification_status=None,
        ti_verification_notes=None,
        ti_duplicate_flag=None,
        ti_npwp_match=None,
        taxes=None,
        taxes_and_charges=None,
        ti_tax_invoice_pdf=None,
        apply_tds=None,
        tax_withholding_category=None,
    )

    doc = types.SimpleNamespace(
        doctype="Purchase Invoice",
        company="Comp",
        posting_date="2024-01-10",
        ti_fp_no="NEW",
        ti_fp_date=None,
        ti_fp_npwp=None,
        ti_fp_dpp=None,
        ti_fp_ppn=None,
        ti_verification_status=None,
        ti_verification_notes=None,
        ti_duplicate_flag=None,
        ti_npwp_match=None,
        taxes=None,
        taxes_and_charges=None,
        ti_tax_invoice_pdf=None,
        apply_tds=None,
        tax_withholding_category=None,
        _doc_before_save=previous,
    )

    with pytest.raises(frappe.ThrowMarker):
        tax_operations.validate_tax_period_lock(doc)
