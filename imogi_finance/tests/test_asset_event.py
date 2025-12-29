import sys
import types


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
if not hasattr(frappe, "_"):
    frappe._ = lambda msg: msg
if not hasattr(frappe, "db"):
    frappe.db = types.SimpleNamespace()
if not hasattr(frappe.db, "set_value"):
    frappe.db.set_value = lambda *args, **kwargs: None
if not hasattr(frappe.db, "get_value"):
    frappe.db.get_value = lambda *args, **kwargs: None


from imogi_finance.events import asset  # noqa: E402


def _asset_doc(request_name="ER-AST-001"):
    doc = types.SimpleNamespace(imogi_expense_request=request_name, name="AST-001")
    doc.get = lambda key, default=None: getattr(doc, key, default)
    return doc


def test_asset_cancel_keeps_linked_status_when_purchase_invoice_remains(monkeypatch):
    captured_set_value = {}

    def fake_get_value(doctype, name, fields, as_dict=True):
        return types.SimpleNamespace(
            linked_payment_entry=None,
            linked_purchase_invoice="PI-123",
        )

    def fake_set_value(doctype, name, values):
        captured_set_value["doctype"] = doctype
        captured_set_value["name"] = name
        captured_set_value["values"] = values

    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)
    monkeypatch.setattr(frappe.db, "set_value", fake_set_value)

    doc = _asset_doc("ER-AST-123")
    asset.on_cancel(doc)

    assert captured_set_value["doctype"] == "Expense Request"
    assert captured_set_value["name"] == "ER-AST-123"
    assert captured_set_value["values"] == {"linked_asset": None, "status": "Linked"}
