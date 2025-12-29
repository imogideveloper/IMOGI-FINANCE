import sys
import types

import pytest


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
if not hasattr(frappe, "_"):
    frappe._ = lambda msg: msg
if not hasattr(frappe, "db"):
    frappe.db = types.SimpleNamespace()
if not hasattr(frappe.db, "set_value"):
    frappe.db.set_value = lambda *args, **kwargs: None
if not hasattr(frappe.db, "get_value"):
    frappe.db.get_value = lambda *args, **kwargs: None


from imogi_finance.events import purchase_invoice  # noqa: E402


def _purchase_invoice_doc(request_name="ER-PI-001"):
    doc = types.SimpleNamespace(imogi_expense_request=request_name, name="PI-001")
    doc.get = lambda key, default=None: getattr(doc, key, default)
    return doc


def test_purchase_invoice_cancel_sets_status_linked_when_asset_remains(monkeypatch):
    captured_set_value = {}

    def fake_get_value(doctype, name, fields, as_dict=True):
        return {
            "linked_payment_entry": None,
            "linked_asset": "AST-123",
            "linked_purchase_invoice": "PI-123",
        }

    def fake_set_value(doctype, name, values):
        captured_set_value["doctype"] = doctype
        captured_set_value["name"] = name
        captured_set_value["values"] = values

    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)
    monkeypatch.setattr(frappe.db, "set_value", fake_set_value)

    doc = _purchase_invoice_doc("ER-PI-002")
    purchase_invoice.on_cancel(doc)

    assert captured_set_value["doctype"] == "Expense Request"
    assert captured_set_value["name"] == "ER-PI-002"
    assert captured_set_value["values"] == {
        "linked_purchase_invoice": None,
        "status": "Linked",
    }


def test_purchase_invoice_cancel_resets_status_when_no_other_links(monkeypatch):
    captured_set_value = {}

    def fake_get_value(doctype, name, fields, as_dict=True):
        return {
            "linked_payment_entry": None,
            "linked_asset": None,
            "linked_purchase_invoice": "PI-003",
        }

    def fake_set_value(doctype, name, values):
        captured_set_value["doctype"] = doctype
        captured_set_value["name"] = name
        captured_set_value["values"] = values

    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)
    monkeypatch.setattr(frappe.db, "set_value", fake_set_value)

    doc = _purchase_invoice_doc("ER-PI-003")
    purchase_invoice.on_cancel(doc)

    assert captured_set_value["doctype"] == "Expense Request"
    assert captured_set_value["name"] == "ER-PI-003"
    assert captured_set_value["values"] == {
        "linked_purchase_invoice": None,
        "status": "Approved",
    }


def test_purchase_invoice_cancel_no_request_skips_updates(monkeypatch):
    set_value_calls = []
    get_value_calls = []

    monkeypatch.setattr(frappe.db, "set_value", lambda *args, **kwargs: set_value_calls.append((args, kwargs)))
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: get_value_calls.append((args, kwargs)))

    doc = _purchase_invoice_doc(None)
    purchase_invoice.on_cancel(doc)

    assert set_value_calls == []
    assert get_value_calls == []


def test_purchase_invoice_submit_links_request(monkeypatch):
    captured_set_value = {}

    def fake_get_approved_expense_request(request_name, target_label):
        assert request_name == "ER-PI-004"
        return types.SimpleNamespace(
            name=request_name, linked_purchase_invoice=None, request_type="Expense"
        )

    def fake_set_value(doctype, name, values):
        captured_set_value["doctype"] = doctype
        captured_set_value["name"] = name
        captured_set_value["values"] = values

    monkeypatch.setattr(purchase_invoice, "get_approved_expense_request", fake_get_approved_expense_request)
    monkeypatch.setattr(frappe.db, "set_value", fake_set_value)

    doc = _purchase_invoice_doc("ER-PI-004")
    purchase_invoice.on_submit(doc)

    assert captured_set_value["doctype"] == "Expense Request"
    assert captured_set_value["name"] == "ER-PI-004"
    assert captured_set_value["values"] == {"linked_purchase_invoice": "PI-001", "status": "Linked"}
