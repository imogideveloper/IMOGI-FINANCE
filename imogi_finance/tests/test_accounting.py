import sys
import types

import pytest


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
frappe.db = types.SimpleNamespace()


frappe._ = lambda msg: msg
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
frappe._dict = lambda value=None: types.SimpleNamespace(**(value or {}))
frappe.db.get_value = lambda *args, **kwargs: None


class _Throw(Exception):
    pass


def _throw(msg=None, title=None):
    raise _Throw(msg or title)


frappe.throw = _throw
frappe.get_doc = None
frappe.new_doc = None
frappe.get_cached_value = None

frappe_utils = types.ModuleType("frappe.utils")
frappe_utils.cint = lambda value=0: 0 if value is None else int(value)
sys.modules["frappe.utils"] = frappe_utils

from imogi_finance import accounting


def _make_expense_request(**overrides):
    def _item(
        amount=1000,
        expense_account="5130 - Meals and Entertainment - _TC",
        is_ppn_applicable=0,
        is_pph_applicable=0,
        pph_base_amount=None,
        **kw,
    ):
        return frappe._dict(
            {
                "expense_account": expense_account,
                "amount": amount,
                "is_ppn_applicable": is_ppn_applicable,
                "is_pph_applicable": is_pph_applicable,
                "pph_base_amount": pph_base_amount,
                **kw,
            }
        )

    defaults = {
        "doctype": "Expense Request",
        "request_type": "Expense",
        "expense_account": "5130 - Meals and Entertainment - _TC",
        "cost_center": "Main - _TC",
        "project": None,
        "amount": 1000,
        "is_ppn_applicable": 0,
        "is_pph_applicable": 1,
        "pph_type": "PPh 23",
        "pph_base_amount": 700,
        "supplier": "Test Supplier",
        "supplier_invoice_no": "INV-001",
        "supplier_invoice_date": "2024-01-01",
        "request_date": "2024-01-02",
        "currency": "IDR",
        "description": "Team lunch",
        "docstatus": 1,
        "status": "Approved",
        "linked_purchase_invoice": None,
        "pending_purchase_invoice": None,
        "items": [_item()],
    }
    defaults.update(overrides)
    request = frappe._dict(defaults)
    request.name = overrides.get("name", "ER-TEST")
    return request


def _doc_with_defaults(doc, **fields):
    for key, value in fields.items():
        setattr(doc, key, value)
    return doc


def test_pph_base_amount_used_for_invoice(monkeypatch):
    request = _make_expense_request(name="ER-001")

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    def fake_db_set(values):
        created_pi.db_set_called_with = values

    request.db_set = fake_db_set
    request.linked_purchase_invoice = None

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    def fake_insert(ignore_permissions=False):
        created_pi.name = "PI-001"

    def fake_append(table, row):
        if not hasattr(created_pi, table):
            setattr(created_pi, table, [])
        getattr(created_pi, table).append(row)

    created_pi.insert = fake_insert
    created_pi.append = fake_append

    pi_name = accounting.create_purchase_invoice_from_request("ER-001")

    assert pi_name == "PI-001"
    assert created_pi.withholding_tax_base_amount == 700
    assert created_pi.db_set_called_with == {
        "linked_purchase_invoice": None,
        "pending_purchase_invoice": "PI-001",
    }
    assert request.pending_purchase_invoice == "PI-001"
    assert request.linked_purchase_invoice is None


def test_pph_base_amount_uses_item_flags(monkeypatch):
    request = _make_expense_request(
        name="ER-001A",
        is_pph_applicable=0,
        pph_base_amount=None,
        items=[
            frappe._dict(
                {
                    "expense_account": "5130 - Meals and Entertainment - _TC",
                    "amount": 100,
                    "is_pph_applicable": 1,
                    "pph_base_amount": 60,
                }
            ),
            frappe._dict(
                {
                    "expense_account": "5130 - Meals and Entertainment - _TC",
                    "amount": 200,
                    "is_pph_applicable": 0,
                    "pph_base_amount": None,
                }
            ),
            frappe._dict(
                {
                    "expense_account": "5130 - Meals and Entertainment - _TC",
                    "amount": 300,
                    "is_pph_applicable": 1,
                    "pph_base_amount": None,
                }
            ),
        ],
    )

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    request.db_set = lambda values: setattr(created_pi, "db_set_called_with", values)

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    created_pi.insert = lambda ignore_permissions=False: setattr(created_pi, "name", "PI-001A")
    created_pi.append = lambda *args, **kwargs: None

    pi_name = accounting.create_purchase_invoice_from_request("ER-001A")

    assert pi_name == "PI-001A"
    assert created_pi.apply_tds == 1
    assert created_pi.withholding_tax_base_amount == 60
    assert created_pi.tax_withholding_category == "PPh 23"


def test_pph_item_wise_detail_includes_only_flagged_rows(monkeypatch):
    request = _make_expense_request(
        name="ER-001B",
        is_pph_applicable=0,
        pph_base_amount=999,
        items=[
            frappe._dict(
                {
                    "expense_account": "5130 - Meals and Entertainment - _TC",
                    "amount": 100,
                    "is_pph_applicable": 1,
                    "pph_base_amount": 80,
                }
            ),
            frappe._dict(
                {
                    "expense_account": "5140 - Travel - _TC",
                    "amount": 200,
                    "is_pph_applicable": 0,
                }
            ),
            frappe._dict(
                {
                    "expense_account": "5150 - Supplies - _TC",
                    "amount": 300,
                    "is_pph_applicable": 1,
                    "pph_base_amount": None,
                }
            ),
        ],
    )

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    request.db_set = lambda values: setattr(created_pi, "db_set_called_with", values)
    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    created_pi.insert = lambda ignore_permissions=False: setattr(created_pi, "name", "PI-001B")
    created_pi.append = lambda *args, **kwargs: None

    pi_name = accounting.create_purchase_invoice_from_request("ER-001B")

    assert pi_name == "PI-001B"
    assert created_pi.apply_tds == 1
    assert created_pi.tax_withholding_category == "PPh 23"
    assert created_pi.withholding_tax_base_amount == 80
    assert created_pi.item_wise_tax_detail == {"1": 80.0}


def test_purchase_invoice_creation_does_not_update_request(monkeypatch):
    request = _make_expense_request(name="ER-003")

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)
    db_set_calls = []

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    request.db_set = lambda values: db_set_calls.append(values)
    request.linked_purchase_invoice = None

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    def fake_insert(ignore_permissions=False):
        created_pi.name = "PI-003"

    def fake_append(table, row):
        if not hasattr(created_pi, table):
            setattr(created_pi, table, [])
        getattr(created_pi, table).append(row)

    created_pi.insert = fake_insert
    created_pi.append = fake_append

    pi_name = accounting.create_purchase_invoice_from_request("ER-003")

    assert pi_name == "PI-003"
    assert db_set_calls == [
        {"linked_purchase_invoice": None, "pending_purchase_invoice": "PI-003"}
    ]
    assert request.status == "Approved"
    assert request.pending_purchase_invoice == "PI-003"
    assert request.linked_purchase_invoice is None


def test_create_purchase_invoice_handles_multiple_items(monkeypatch):
    request = _make_expense_request(name="ER-007")
    request.items = [
        frappe._dict({"expense_account": request.expense_account, "amount": 100, "description": "Line 1"}),
        frappe._dict({"expense_account": request.expense_account, "amount": 200, "description": "Line 2"}),
    ]
    request.amount = 300

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    append_calls = []

    def fake_append(table, row):
        if not hasattr(created_pi, table):
            setattr(created_pi, table, [])
        getattr(created_pi, table).append(row)
        append_calls.append(row)

    def fake_db_set(values):
        created_pi.db_set_called_with = values

    request.db_set = fake_db_set

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    created_pi.insert = lambda ignore_permissions=False: setattr(created_pi, "name", "PI-007")
    created_pi.append = fake_append

    pi_name = accounting.create_purchase_invoice_from_request("ER-007")

    assert pi_name == "PI-007"
    assert len(created_pi.items) == 2
    assert [row["amount"] for row in created_pi.items] == [100, 200]
    assert created_pi.db_set_called_with == {
        "linked_purchase_invoice": None,
        "pending_purchase_invoice": "PI-007",
    }
    assert request.linked_purchase_invoice is None
    assert request.pending_purchase_invoice == "PI-007"


def test_create_purchase_invoice_syncs_amount_and_account(monkeypatch):
    request = _make_expense_request(
        name="ER-008",
        expense_account="9999 - Old - _TC",
        amount=5,
    )
    request.items = [
        frappe._dict({"expense_account": "7777 - Meals - _TC", "amount": 125, "description": "Actual"}),
    ]

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)
    db_set_calls = []

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    request.db_set = lambda values: db_set_calls.append(values)
    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    created_pi.insert = lambda ignore_permissions=False: setattr(created_pi, "name", "PI-008")
    created_pi.append = lambda *args, **kwargs: None

    pi_name = accounting.create_purchase_invoice_from_request("ER-008")

    assert pi_name == "PI-008"
    assert db_set_calls == [
        {"amount": 125.0, "expense_account": "7777 - Meals - _TC"},
        {"linked_purchase_invoice": None, "pending_purchase_invoice": "PI-008"},
    ]
    assert request.amount == 125.0
    assert request.expense_account == "7777 - Meals - _TC"


def test_create_purchase_invoice_allows_mixed_expense_accounts(monkeypatch):
    request = _make_expense_request(name="ER-009", amount=1000, expense_account="5130 - Meals and Entertainment - _TC")
    request.items = [
        frappe._dict({"expense_account": "5130 - Meals and Entertainment - _TC", "amount": 100}),
        frappe._dict({"expense_account": "5140 - Travel - _TC", "amount": 200}),
    ]

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)
    db_set_calls = []

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    def fake_db_set(values):
        db_set_calls.append(values)

    def fake_append(table, row):
        if not hasattr(created_pi, table):
            setattr(created_pi, table, [])
        getattr(created_pi, table).append(row)

    request.db_set = fake_db_set
    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", lambda doctype: created_pi)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    created_pi.insert = lambda ignore_permissions=False: setattr(created_pi, "name", "PI-009")
    created_pi.append = fake_append

    pi_name = accounting.create_purchase_invoice_from_request("ER-009")

    assert pi_name == "PI-009"
    assert db_set_calls[0] == {"amount": 300.0, "expense_account": None}
    assert db_set_calls[1] == {
        "linked_purchase_invoice": None,
        "pending_purchase_invoice": "PI-009",
    }
    assert request.expense_accounts == ("5130 - Meals and Entertainment - _TC", "5140 - Travel - _TC")
    assert request.expense_account is None
    assert request.amount == 300.0
    assert [row["expense_account"] for row in created_pi.items] == [
        "5130 - Meals and Entertainment - _TC",
        "5140 - Travel - _TC",
    ]


def test_create_purchase_invoice_sets_ppn_when_doc_flagged(monkeypatch):
    request = _make_expense_request(
        name="ER-010",
        is_ppn_applicable=1,
        ppn_template="PPN-TEMPLATE",
    )

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    request.db_set = lambda values: setattr(created_pi, "db_set_called_with", values)
    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", lambda doctype: created_pi)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    def fake_insert(ignore_permissions=False):
        created_pi.name = "PI-010"

    def fake_set_taxes():
        created_pi.set_taxes_called = True

    created_pi.insert = fake_insert
    created_pi.append = lambda *args, **kwargs: None
    created_pi.set_taxes = fake_set_taxes

    pi_name = accounting.create_purchase_invoice_from_request("ER-010")

    assert pi_name == "PI-010"
    assert created_pi.taxes_and_charges == "PPN-TEMPLATE"
    assert getattr(created_pi, "set_taxes_called", False) is True


def test_create_purchase_invoice_ignores_item_ppn_flags(monkeypatch):
    request = _make_expense_request(
        name="ER-011",
        is_ppn_applicable=0,
        ppn_template="PPN-TEMPLATE",
    )
    request.items[0].is_ppn_applicable = 1

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    request.db_set = lambda values: setattr(created_pi, "db_set_called_with", values)
    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", lambda doctype: created_pi)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    created_pi.insert = lambda ignore_permissions=False: setattr(created_pi, "name", "PI-011")
    created_pi.append = lambda *args, **kwargs: None
    created_pi.set_taxes = lambda: setattr(created_pi, "set_taxes_called", True)

    pi_name = accounting.create_purchase_invoice_from_request("ER-011")

    assert pi_name == "PI-011"
    assert getattr(created_pi, "taxes_and_charges", None) is None
    assert getattr(created_pi, "set_taxes_called", False) is False


def test_update_links_clears_pending_for_submitted_invoice():
    request = _make_expense_request(name="ER-005", pending_purchase_invoice="PI-DRAFT")
    purchase_invoice = _doc_with_defaults(frappe._dict(), name="PI-005", docstatus=1)
    db_set_calls = []
    request.db_set = lambda values: db_set_calls.append(values)

    accounting._update_request_purchase_invoice_links(request, purchase_invoice)

    assert db_set_calls == [
        {"linked_purchase_invoice": "PI-005", "pending_purchase_invoice": None}
    ]
    assert request.pending_purchase_invoice is None
    assert request.linked_purchase_invoice == "PI-005"


def test_update_links_respects_mark_pending_flag_for_draft():
    request = _make_expense_request(name="ER-006")
    purchase_invoice = _doc_with_defaults(frappe._dict(), name="PI-006", docstatus=0)
    db_set_calls = []
    request.db_set = lambda values: db_set_calls.append(values)

    accounting._update_request_purchase_invoice_links(request, purchase_invoice, mark_pending=False)

    assert db_set_calls == [
        {"linked_purchase_invoice": None, "pending_purchase_invoice": None}
    ]
    assert request.pending_purchase_invoice is None
    assert request.linked_purchase_invoice is None


def test_validate_request_ready_for_link_disallows_linked_status():
    request = _make_expense_request(status="PI Created")
    previous_throw = frappe.throw
    frappe.throw = _throw

    try:
        with pytest.raises(_Throw):
            accounting._validate_request_ready_for_link(request)
    finally:
        frappe.throw = previous_throw


def test_create_purchase_invoice_rejects_when_draft_exists(monkeypatch):
    request = _make_expense_request(name="ER-004", pending_purchase_invoice="PI-DRAFT-1")

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)

    previous_throw = frappe.throw
    frappe.throw = _throw
    try:
        with pytest.raises(_Throw):
            accounting.create_purchase_invoice_from_request("ER-004")
    finally:
        frappe.throw = previous_throw


def test_create_purchase_invoice_requires_verification_for_ppn_when_setting_enabled(monkeypatch):
    request = _make_expense_request(
        name="ER-PPN-VERIFY",
        is_ppn_applicable=1,
        ti_verification_status="Pending",
    )

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        if doctype == "Tax Invoice OCR Settings":
            # Simulate OCR enabled + require verification ON
            if fieldname == "enable_tax_invoice_ocr":
                return 1
            if fieldname == "require_verification_before_create_pi_from_expense_request":
                return 1
        return None

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    previous_throw = frappe.throw
    frappe.throw = _throw
    try:
        with pytest.raises(_Throw) as excinfo:
            accounting.create_purchase_invoice_from_request("ER-PPN-VERIFY")
    finally:
        frappe.throw = previous_throw

    assert "Tax Invoice must be verified" in str(excinfo.value)


def test_create_purchase_invoice_does_not_require_verification_for_non_ppn(monkeypatch):
    request = _make_expense_request(
        name="ER-NON-PPN",
        is_ppn_applicable=0,
        ti_verification_status="Pending",
    )

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        if doctype == "Tax Invoice OCR Settings":
            # Same settings: OCR enabled + require verification ON
            if fieldname == "enable_tax_invoice_ocr":
                return 1
            if fieldname == "require_verification_before_create_pi_from_expense_request":
                return 1
        return None

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_insert(ignore_permissions=False):
        created_pi.name = "PI-NON-PPN"

    created_pi.insert = fake_insert
    created_pi.append = lambda *args, **kwargs: None

    request.db_set = lambda values: setattr(created_pi, "db_set_called_with", values)

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    pi_name = accounting.create_purchase_invoice_from_request("ER-NON-PPN")

    assert pi_name == "PI-NON-PPN"


def test_create_purchase_invoice_calculates_taxes_after_insert(monkeypatch):
    """Test that calculate_taxes_and_totals is called after PI insert to ensure PPN and PPh are calculated."""
    request = _make_expense_request(
        name="ER-TAX-CALC",
        is_ppn_applicable=1,
        ppn_template="PPN-11",
        is_pph_applicable=1,
        pph_type="PPh 23",
        pph_base_amount=1000,
    )

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)
    
    # Track method calls
    created_pi.calculate_taxes_called = False
    created_pi.save_called = False

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_insert(ignore_permissions=False):
        created_pi.name = "PI-TAX-CALC"

    def fake_calculate_taxes_and_totals():
        created_pi.calculate_taxes_called = True

    def fake_save(ignore_permissions=False):
        created_pi.save_called = True

    created_pi.insert = fake_insert
    created_pi.append = lambda *args, **kwargs: None
    created_pi.set_taxes = lambda: None
    created_pi.calculate_taxes_and_totals = fake_calculate_taxes_and_totals
    created_pi.save = fake_save

    request.db_set = lambda values: setattr(created_pi, "db_set_called_with", values)

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    pi_name = accounting.create_purchase_invoice_from_request("ER-TAX-CALC")

    assert pi_name == "PI-TAX-CALC"
    assert created_pi.calculate_taxes_called is True, "calculate_taxes_and_totals should be called after insert"
    assert created_pi.save_called is True, "save should be called after calculate_taxes_and_totals"


def test_create_purchase_invoice_sets_withholding_tax_when_pph_applicable(monkeypatch):
    request = _make_expense_request(
        name="ER-TDS",
        is_pph_applicable=1,
        pph_type="PPh 23",
        pph_base_amount=500,
    )

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None, docstatus=0)
    created_pi.set_tax_withholding_called = False
    created_pi.save_called = False

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        return None

    def fake_new_doc(doctype):
        assert doctype == "Purchase Invoice"
        return created_pi

    def fake_insert(ignore_permissions=False):
        created_pi.name = "PI-TDS"

    def fake_set_tax_withholding():
        created_pi.set_tax_withholding_called = True

    def fake_save(ignore_permissions=False):
        created_pi.save_called = True

    created_pi.insert = fake_insert
    created_pi.append = lambda *args, **kwargs: None
    created_pi.set_tax_withholding = fake_set_tax_withholding
    created_pi.calculate_taxes_and_totals = lambda: None
    created_pi.save = fake_save

    request.db_set = lambda values: setattr(created_pi, "db_set_called_with", values)

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)

    pi_name = accounting.create_purchase_invoice_from_request("ER-TDS")

    assert pi_name == "PI-TDS"
    assert created_pi.set_tax_withholding_called is True
    assert created_pi.save_called is True
