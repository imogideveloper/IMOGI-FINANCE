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
if not hasattr(frappe, "throw"):
    frappe.throw = lambda *args, **kwargs: None
if not hasattr(frappe, "get_doc"):
    frappe.get_doc = lambda *args, **kwargs: None


from imogi_finance.events import payment_entry  # noqa: E402


def _payment_entry_doc(request_name="ER-TEST"):
    doc = types.SimpleNamespace(imogi_expense_request=request_name, name="PE-001")
    doc.get = lambda key, default=None: getattr(doc, key, default)
    return doc


@pytest.mark.parametrize("docstatus,status", [(0, "Approved"), (1, "Pending")])
def test_payment_entry_linking_requires_approved_request(monkeypatch, docstatus, status):
    request = types.SimpleNamespace(name="ER-001", docstatus=docstatus, status=status, request_type="Expense")
    set_value_calls = []

    class LinkError(Exception):
        pass

    def _throw(msg=None, title=None):
        raise LinkError(msg or title)

    monkeypatch.setattr(frappe, "throw", _throw)
    monkeypatch.setattr(frappe, "get_doc", lambda *args, **kwargs: request)
    monkeypatch.setattr(frappe.db, "set_value", lambda *args, **kwargs: set_value_calls.append((args, kwargs)))

    with pytest.raises(LinkError) as excinfo:
        payment_entry.on_submit(_payment_entry_doc("ER-001"))

    assert "docstatus 1 and status Closed, Linked" in str(excinfo.value)
    assert set_value_calls == []


def test_payment_entry_links_request_when_approved(monkeypatch):
    request = types.SimpleNamespace(
        name="ER-002", docstatus=1, status="Linked", linked_payment_entry=None, request_type="Expense", linked_purchase_invoice="PI-111"
    )
    captured_set_value = {}

    class LinkError(Exception):
        pass

    def _throw(msg=None, title=None):
        raise LinkError(msg or title)

    monkeypatch.setattr(frappe, "throw", _throw)
    monkeypatch.setattr(frappe, "get_doc", lambda *args, **kwargs: request)

    def fake_set_value(doctype, name, values):
        captured_set_value["doctype"] = doctype
        captured_set_value["name"] = name
        captured_set_value["values"] = values

    monkeypatch.setattr(frappe.db, "set_value", fake_set_value)

    doc = _payment_entry_doc("ER-002")
    payment_entry.on_submit(doc)

    assert captured_set_value["doctype"] == "Expense Request"
    assert captured_set_value["name"] == "ER-002"
    assert captured_set_value["values"] == {"linked_payment_entry": doc.name, "status": "Closed"}


def test_payment_entry_throws_if_already_linked(monkeypatch):
    request = types.SimpleNamespace(
        name="ER-003", docstatus=1, status="Linked", linked_payment_entry="PE-0009", request_type="Expense", linked_purchase_invoice="PI-111"
    )

    class LinkError(Exception):
        pass

    def _throw(msg=None, title=None):
        raise LinkError(msg or title)

    monkeypatch.setattr(frappe, "throw", _throw)
    monkeypatch.setattr(frappe, "get_doc", lambda *args, **kwargs: request)

    set_value_calls = []
    monkeypatch.setattr(frappe.db, "set_value", lambda *args, **kwargs: set_value_calls.append((args, kwargs)))

    with pytest.raises(LinkError) as excinfo:
        payment_entry.on_submit(_payment_entry_doc("ER-003"))

    assert "Expense Request already linked to Payment Entry PE-0009" in str(excinfo.value)
    assert set_value_calls == []


def test_payment_entry_requires_purchase_invoice_or_asset(monkeypatch):
    request = types.SimpleNamespace(
        name="ER-004", docstatus=1, status="Linked", linked_payment_entry=None, linked_purchase_invoice=None,
        linked_asset=None, request_type="Asset"
    )

    class LinkError(Exception):
        pass

    def _throw(msg=None, title=None):
        raise LinkError(msg or title)

    monkeypatch.setattr(frappe, "throw", _throw)
    monkeypatch.setattr(frappe, "get_doc", lambda *args, **kwargs: request)

    set_value_calls = []
    monkeypatch.setattr(frappe.db, "set_value", lambda *args, **kwargs: set_value_calls.append((args, kwargs)))

    with pytest.raises(LinkError) as excinfo:
        payment_entry.on_submit(_payment_entry_doc("ER-004"))

    assert "must be linked to a Purchase Invoice or Asset" in str(excinfo.value)
    assert set_value_calls == []
