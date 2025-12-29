import sys
import types


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

    created_pi = _doc_with_defaults(frappe._dict(), linked_purchase_invoice=None)

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


def test_journal_entry_uses_pph_base_amount(monkeypatch):
    request = _make_expense_request(request_type="Asset", name="ER-002")

    created_je = _doc_with_defaults(frappe._dict(), linked_journal_entry=None)

    def fake_get_doc(doctype, name):
        assert doctype == "Expense Request"
        return request

    def fake_get_value(doctype, name, fieldname, *args, **kwargs):
        if doctype == "Cost Center":
            return "Test Company"
        if doctype == "Supplier":
            return "2100 - Creditors - _TC"
        if doctype == "Company":
            return "2100 - Creditors - _TC"
        if doctype == "Tax Withholding Category":
            return "2240 - PPh 23 Payable - _TC"
        return None

    def fake_new_doc(doctype):
        assert doctype == "Journal Entry"
        return created_je

    def fake_insert(ignore_permissions=False):
        created_je.name = "JE-001"

    def fake_append(table, row):
        if not hasattr(created_je, table):
            setattr(created_je, table, [])
        getattr(created_je, table).append(row)

    def fake_db_set(values):
        created_je.db_set_called_with = values

    request.db_set = fake_db_set
    request.linked_journal_entry = None

    monkeypatch.setattr(frappe, "get_doc", fake_get_doc)
    monkeypatch.setattr(frappe, "new_doc", fake_new_doc)
    monkeypatch.setattr(frappe, "get_cached_value", fake_get_value)
    monkeypatch.setattr(frappe.db, "get_value", fake_get_value)
    created_je.insert = fake_insert
    created_je.append = fake_append

    je_name = accounting.create_journal_entry_from_request("ER-002")

    assert je_name == "JE-001"
    assert created_je.accounts[0]["debit_in_account_currency"] == 700
    assert created_je.accounts[1]["debit_in_account_currency"] == 300
    assert created_je.accounts[2]["credit_in_account_currency"] == 1000
