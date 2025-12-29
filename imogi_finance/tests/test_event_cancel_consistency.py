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


from imogi_finance.events import asset, payment_entry, purchase_invoice  # noqa: E402


@pytest.mark.parametrize(
    "event_module, cleared_field, remaining_field",
    [
        (asset, "linked_asset", "linked_purchase_invoice"),
        (purchase_invoice, "linked_purchase_invoice", "linked_asset"),
        (payment_entry, "linked_payment_entry", "linked_purchase_invoice"),
    ],
)
def test_cancel_keeps_linked_status_when_other_links_exist(
    event_module, cleared_field, remaining_field, monkeypatch
):
    captured_set_value = {}

    def fake_get_value(doctype, name, fields, as_dict=True):
        return {
            "linked_purchase_invoice": (
                "PI-ACTIVE" if remaining_field == "linked_purchase_invoice" else None
            ),
            "linked_payment_entry": (
                "PE-ACTIVE" if remaining_field == "linked_payment_entry" else None
            ),
            "linked_asset": "AST-ACTIVE" if remaining_field == "linked_asset" else None,
        }

    def fake_set_value(doctype, name, values):
        captured_set_value["doctype"] = doctype
        captured_set_value["name"] = name
        captured_set_value["values"] = values

    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)
    monkeypatch.setattr(frappe.db, "set_value", fake_set_value)

    doc = types.SimpleNamespace(imogi_expense_request="ER-CROSS", name="DOC-001")
    doc.get = lambda key, default=None: getattr(doc, key, default)

    event_module.on_cancel(doc)

    assert captured_set_value["doctype"] == "Expense Request"
    assert captured_set_value["name"] == "ER-CROSS"
    assert captured_set_value["values"]["status"] == "Linked"
    assert captured_set_value["values"][cleared_field] is None
