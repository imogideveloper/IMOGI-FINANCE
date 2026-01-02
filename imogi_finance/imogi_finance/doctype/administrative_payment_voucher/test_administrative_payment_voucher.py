import sys
import types

import pytest


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
if not hasattr(frappe, "_"):
    frappe._ = lambda msg: msg
if not hasattr(frappe, "_dict"):
    frappe._dict = lambda *args, **kwargs: types.SimpleNamespace(**kwargs)
if not hasattr(frappe, "msgprint"):
    frappe.msgprint = lambda *args, **kwargs: None
if not hasattr(frappe, "bold"):
    frappe.bold = lambda msg: msg
if not hasattr(frappe, "whitelist"):
    frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)

frappe_db = getattr(frappe, "db", types.SimpleNamespace())
if not hasattr(frappe_db, "set_value"):
    frappe_db.set_value = lambda *args, **kwargs: None
if not hasattr(frappe_db, "has_column"):
    frappe_db.has_column = lambda *args, **kwargs: False
if not hasattr(frappe_db, "get_value"):
    frappe_db.get_value = lambda *args, **kwargs: None
if not hasattr(frappe_db, "exists"):
    frappe_db.exists = lambda *args, **kwargs: False
if not hasattr(frappe_db, "sql"):
    frappe_db.sql = lambda *args, **kwargs: None
frappe.db = frappe_db

if not hasattr(frappe, "get_all"):
    frappe.get_all = lambda *args, **kwargs: []
if not hasattr(frappe, "get_doc"):
    frappe.get_doc = lambda *args, **kwargs: None
if not hasattr(frappe, "new_doc"):
    frappe.new_doc = lambda *args, **kwargs: None
if not hasattr(frappe, "get_roles"):
    frappe.get_roles = lambda *args, **kwargs: []
frappe.session = frappe._dict(user="tester@example.com")

if not hasattr(frappe, "throw"):
    class ThrowMarker(Exception):
        pass

    def _throw(msg=None, title=None):
        raise ThrowMarker(msg or title)

    frappe.ThrowMarker = ThrowMarker
    frappe.throw = _throw

model = sys.modules.setdefault("frappe.model", types.ModuleType("frappe.model"))
document = types.ModuleType("frappe.model.document")


class DummyDocument:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def append(self, fieldname, values):
        rows = getattr(self, fieldname, [])
        rows.append(values)
        setattr(self, fieldname, rows)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def db_set(self, *args, **kwargs):
        pass


document.Document = DummyDocument
model.document = document
sys.modules["frappe.model.document"] = document

utils = sys.modules.setdefault("frappe.utils", types.ModuleType("frappe.utils"))
if not hasattr(utils, "now_datetime"):
    import datetime

    utils.now_datetime = lambda: datetime.datetime.now()
if not hasattr(utils, "flt"):
    utils.flt = lambda value, *args, **kwargs: float(value or 0)
if not hasattr(utils, "get_first_day"):
    utils.get_first_day = lambda date_str=None: None
if not hasattr(utils, "get_last_day"):
    utils.get_last_day = lambda date_obj=None: None
if not hasattr(utils, "nowdate"):
    utils.nowdate = lambda: ""

sys.modules["frappe.utils"] = utils

xlsxutils = types.ModuleType("frappe.utils.xlsxutils")
xlsxutils.make_xlsx = lambda *args, **kwargs: types.SimpleNamespace(getvalue=lambda: b"")
sys.modules["frappe.utils.xlsxutils"] = xlsxutils

from imogi_finance.imogi_finance.doctype.administrative_payment_voucher import (  # noqa: E402
    administrative_payment_voucher as apv,
)


def test_payment_entry_mapping_receive_direction():
    mapping = apv.map_payment_entry_accounts("Receive", 1500, "ACC-BANK", "ACC-INCOME")
    assert mapping.payment_type == "Receive"
    assert mapping.paid_to == "ACC-BANK"
    assert mapping.paid_from == "ACC-INCOME"
    assert mapping.paid_amount == 1500
    assert mapping.received_amount == 1500


def test_target_account_rejects_bank_or_cash(monkeypatch):
    doc = apv.AdministrativePaymentVoucher(
        bank_cash_account="ACC-BANK",
        target_gl_account="ACC-BANK",
        company="Company A",
        direction="Pay",
        amount=100,
        payment_entry=None,
    )
    details = apv.AccountDetails("ACC-BANK", "Bank", "Asset", 0, "Company A")
    monkeypatch.setattr(doc, "_get_account", lambda account: details)
    monkeypatch.setattr(apv, "get_apv_settings", lambda: frappe._dict({"allow_target_bank_cash": 0}))
    with pytest.raises(Exception):
        doc._validate_accounts()


def test_party_required_for_receivable_accounts(monkeypatch):
    details = apv.AccountDetails("ACC-REC", "Receivable", "Asset", 0, "Company A")

    class Marker(Exception):
        pass

    monkeypatch.setattr(frappe, "throw", lambda *args, **kwargs: (_ for _ in ()).throw(Marker()))
    with pytest.raises(Marker):
        apv.validate_party(details, None, None)


def test_apply_optional_dimension_respects_missing_column(monkeypatch):
    doc = DummyDocument(doctype="Dummy")
    monkeypatch.setattr(frappe.db, "has_column", lambda doctype, field: False, raising=False)
    apv.apply_optional_dimension(doc, "branch", "BR-01")
    assert not hasattr(doc, "branch")


def test_apply_optional_dimension_sets_when_present(monkeypatch):
    doc = DummyDocument(doctype="Dummy")
    monkeypatch.setattr(frappe.db, "has_column", lambda doctype, field: True, raising=False)
    apv.apply_optional_dimension(doc, "branch", "BR-02")
    assert doc.branch == "BR-02"


def test_validate_accounts_disallows_target_bank_when_setting_disabled(monkeypatch):
    doc = apv.AdministrativePaymentVoucher(
        bank_cash_account="BANK-1",
        target_gl_account="BANK-2",
        company="IMOGI",
        amount=1000,
        direction="Pay",
        payment_entry=None,
    )

    bank = apv.AccountDetails("BANK-1", "Bank", "Asset", 0, "IMOGI")
    target = apv.AccountDetails("BANK-2", "Bank", "Asset", 0, "IMOGI")
    monkeypatch.setattr(doc, "_get_account", lambda account: bank if account == "BANK-1" else target)
    monkeypatch.setattr(apv, "get_apv_settings", lambda: frappe._dict({"allow_target_bank_cash": 0}))

    with pytest.raises(Exception):
        doc._validate_accounts()


def test_existing_payment_entry_reused_without_duplicate(monkeypatch):
    doc = apv.AdministrativePaymentVoucher(
        name="APV-001",
        workflow_state="Approved",
        status="Approved",
        docstatus=1,
        bank_cash_account="BANK-1",
        target_gl_account="EXP-1",
        amount=250,
        company="IMOGI",
        posting_date="2024-02-01",
        mode_of_payment="Cash",
        direction="Pay",
        payment_entry="PE-001",
    )
    doc.flags = types.SimpleNamespace(workflow_action_allowed=True, allow_payment_entry_in_workflow=True)

    bank = apv.AccountDetails("BANK-1", "Bank", "Asset", 0, "IMOGI")
    target = apv.AccountDetails("EXP-1", "Payable", "Liability", 0, "IMOGI")
    monkeypatch.setattr(doc, "_get_account", lambda account: bank if account == "BANK-1" else target)

    class DummyPaymentEntry(DummyDocument):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.meta = types.SimpleNamespace(has_field=lambda field: True)

        def submit(self):
            self.docstatus = 1

    existing = DummyPaymentEntry(
        name="PE-001",
        docstatus=1,
        paid_from="BANK-1",
        paid_to="EXP-1",
        paid_amount=250,
        received_amount=250,
        company="IMOGI",
        posting_date="2024-02-01",
        mode_of_payment="Cash",
    )

    monkeypatch.setattr(frappe.db, "exists", lambda doctype, name=None: name == "PE-001")
    monkeypatch.setattr(frappe, "get_doc", lambda doctype, name=None: existing if name == "PE-001" else None)
    monkeypatch.setattr(frappe, "get_all", lambda *args, **kwargs: [])
    monkeypatch.setattr(frappe, "new_doc", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("Should not create")))

    payment_entry, created = doc._ensure_payment_entry()

    assert payment_entry is existing
    assert created is False
    assert doc.payment_entry == "PE-001"
    assert doc.status == "Posted"
    assert doc.workflow_state == "Posted"


def test_payment_entry_creation_requires_approval(monkeypatch):
    doc = apv.AdministrativePaymentVoucher(
        name="APV-002",
        workflow_state="Draft",
        status="Draft",
        docstatus=1,
        bank_cash_account="BANK-1",
        target_gl_account="EXP-1",
        amount=100,
        company="IMOGI",
        posting_date="2024-02-02",
        direction="Pay",
    )
    bank = apv.AccountDetails("BANK-1", "Bank", "Asset", 0, "IMOGI")
    target = apv.AccountDetails("EXP-1", "Payable", "Liability", 0, "IMOGI")
    monkeypatch.setattr(doc, "_get_account", lambda account: bank if account == "BANK-1" else target)

    with pytest.raises(Exception):
        doc._ensure_payment_entry()


def test_cancel_payment_entry_failure_bubbles_up(monkeypatch):
    doc = apv.AdministrativePaymentVoucher(name="APV-003", payment_entry="PE-ERR")

    class DummyPaymentEntry(DummyDocument):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.docstatus = kwargs.get("docstatus", 1)

        def cancel(self):
            raise Exception("Reconciled")

    payment_entry = DummyPaymentEntry(name="PE-ERR")
    monkeypatch.setattr(frappe.db, "exists", lambda doctype, name=None: name == "PE-ERR")
    monkeypatch.setattr(frappe, "get_doc", lambda doctype, name=None: payment_entry)

    with pytest.raises(Exception):
        doc._attempt_cancel_payment_entry()
