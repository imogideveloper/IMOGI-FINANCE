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

from imogi_finance import accounting


def _make_expense_request(**overrides):
    def _item(amount=1000, expense_account="5130 - Meals and Entertainment - _TC", **kw):
        return frappe._dict({"expense_account": expense_account, "amount": amount, **kw})

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
        "asset_name": None,
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
        "linked_purchase_invoice": "PI-001",
        "pending_purchase_invoice": "PI-001",
    }
    assert request.pending_purchase_invoice == "PI-001"
    assert request.linked_purchase_invoice == "PI-001"


def test_asset_request_creates_purchase_invoice(monkeypatch):
    request = _make_expense_request(
        request_type="Asset", name="ER-002", asset_name="New Laptop", description="Laptop"
    )
    request.items[0].asset_name = "New Laptop"
    request.items[0].asset_description = "Laptop"

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
        created_pi.name = "PI-002"

    def fake_append(table, row):
        if not hasattr(created_pi, table):
            setattr(created_pi, table, [])
        getattr(created_pi, table).append(row)

    created_pi.insert = fake_insert
    created_pi.append = fake_append

    pi_name = accounting.create_purchase_invoice_from_request("ER-002")

    assert pi_name == "PI-002"
    assert created_pi.withholding_tax_base_amount == 700
    assert created_pi.items[0]["item_name"] == "New Laptop"
    assert created_pi.db_set_called_with == {
        "linked_purchase_invoice": "PI-002",
        "pending_purchase_invoice": "PI-002",
    }
    assert request.pending_purchase_invoice == "PI-002"
    assert request.linked_purchase_invoice == "PI-002"


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
        {"linked_purchase_invoice": "PI-003", "pending_purchase_invoice": "PI-003"}
    ]
    assert request.status == "Approved"
    assert request.pending_purchase_invoice == "PI-003"
    assert request.linked_purchase_invoice == "PI-003"


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
        "linked_purchase_invoice": "PI-007",
        "pending_purchase_invoice": "PI-007",
    }
    assert request.linked_purchase_invoice == "PI-007"
    assert request.pending_purchase_invoice == "PI-007"


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
        {"linked_purchase_invoice": "PI-006", "pending_purchase_invoice": None}
    ]
    assert request.pending_purchase_invoice is None
    assert request.linked_purchase_invoice == "PI-006"


def test_validate_request_ready_for_link_disallows_linked_status():
    request = _make_expense_request(status="Linked")
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
