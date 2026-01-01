import sys
import types

import pytest

frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
frappe._ = lambda msg, *args, **kwargs: msg
frappe.get_roles = lambda: []
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
frappe.utils = types.SimpleNamespace(
    cint=lambda value: int(value),
    flt=lambda value, *args, **kwargs: float(value),
    get_site_path=lambda *args, **kwargs: "/tmp",
)
sys.modules["frappe.utils"] = frappe.utils
frappe.utils.formatters = types.SimpleNamespace(format_value=lambda value, *args, **kwargs: value)
sys.modules["frappe.utils.formatters"] = frappe.utils.formatters
frappe.exceptions = types.SimpleNamespace(ValidationError=Exception)
sys.modules["frappe.exceptions"] = frappe.exceptions


class _Throw(Exception):
    pass


def _throw(msg=None, title=None):
    raise _Throw(msg or title)


frappe.throw = _throw

from imogi_finance.budget_control import ledger, native_budget, service, utils  # noqa: E402
from imogi_finance.budget_control import workflow  # noqa: E402
from imogi_finance.imogi_finance.doctype.additional_budget_request.additional_budget_request import (  # noqa: E402
    AdditionalBudgetRequest,
)
from imogi_finance.imogi_finance.doctype.budget_reclass_request.budget_reclass_request import (  # noqa: E402
    BudgetReclassRequest,
)
from imogi_finance.imogi_finance.doctype.internal_charge_request.internal_charge_request import (  # noqa: E402
    InternalChargeRequest,
)


def _patch_settings(monkeypatch, **overrides):
    settings = utils.DEFAULT_SETTINGS.copy()
    settings.update(overrides)
    monkeypatch.setattr(utils, "get_settings", lambda: settings)
    monkeypatch.setattr(service.utils, "get_settings", lambda: settings)
    monkeypatch.setattr(ledger, "get_settings", lambda: settings)
    monkeypatch.setattr(workflow.utils, "get_settings", lambda: settings)
    return settings


def test_budget_reclass_creates_entries_and_updates_budget(monkeypatch):
    _patch_settings(monkeypatch, enable_budget_reclass=1, enable_budget_lock=1)

    ledger_calls = []
    delta_calls = []

    monkeypatch.setattr(
        ledger,
        "post_entry",
        lambda entry_type, dims, amount, direction, **kw: ledger_calls.append(
            {"entry_type": entry_type, "amount": amount, "direction": direction, "filters": dims.as_filters()}
        )
        or "BCE-0001",
    )
    monkeypatch.setattr(
        service,
        "check_budget_available",
        lambda dims, amount: service.BudgetCheckResult(True, "ok", available=1000, snapshot={}),
    )
    monkeypatch.setattr(
        service,
        "apply_budget_allocation_delta",
        lambda dims, delta: delta_calls.append({"account": dims.account, "delta": delta}),
    )

    doc = BudgetReclassRequest()
    doc.company = "TC"
    doc.fiscal_year = "2024"
    doc.from_cost_center = "CC-OLD"
    doc.from_account = "5110"
    doc.to_cost_center = "CC-NEW"
    doc.to_account = "5120"
    doc.amount = 500

    doc.on_submit()

    assert len(ledger_calls) == 2
    assert {"account": "5110", "delta": -500} in delta_calls
    assert {"account": "5120", "delta": 500} in delta_calls


def test_additional_budget_request_posts_supplement(monkeypatch):
    _patch_settings(monkeypatch, enable_additional_budget=1, enable_budget_lock=1)

    ledger_calls = []
    delta_calls = []

    monkeypatch.setattr(
        ledger,
        "post_entry",
        lambda entry_type, dims, amount, direction, **kw: ledger_calls.append(
            {"entry_type": entry_type, "amount": amount, "direction": direction, "filters": dims.as_filters()}
        )
        or "BCE-0002",
    )
    monkeypatch.setattr(
        service,
        "apply_budget_allocation_delta",
        lambda dims, delta: delta_calls.append({"account": dims.account, "delta": delta}),
    )

    doc = AdditionalBudgetRequest()
    doc.company = "TC"
    doc.fiscal_year = "2024"
    doc.cost_center = "CC-MAIN"
    doc.account = "5110"
    doc.amount = 1200

    doc.on_submit()

    assert len(ledger_calls) == 1
    assert ledger_calls[0]["entry_type"] == "SUPPLEMENT"
    assert {"account": "5110", "delta": 1200} in delta_calls


def test_disabled_additional_budget_is_noop(monkeypatch):
    _patch_settings(monkeypatch, enable_additional_budget=0, enable_budget_lock=0)

    called = []
    monkeypatch.setattr(service, "record_supplement", lambda **kw: called.append(kw))

    doc = AdditionalBudgetRequest()
    doc.company = "TC"
    doc.fiscal_year = "2024"
    doc.cost_center = "CC-MAIN"
    doc.account = "5110"
    doc.amount = 100

    doc.on_submit()

    assert called == []


def test_internal_charge_route_resolution(monkeypatch):
    _patch_settings(monkeypatch, enable_internal_charge=1)

    expense_items = [types.SimpleNamespace(expense_account="5110", amount=300)]
    dummy_expense = types.SimpleNamespace(docstatus=1, status="Approved", items=expense_items)

    monkeypatch.setattr(
        InternalChargeRequest,
        "expense_request",
        "ER-001",
        raising=False,
    )

    ic_module = sys.modules[
        "imogi_finance.imogi_finance.doctype.internal_charge_request.internal_charge_request"
    ]

    monkeypatch.setattr(
        ic_module.accounting,
        "summarize_request_items",
        lambda items, **kwargs: (sum(getattr(it, "amount", 0) for it in items), ("5110",)),
    )

    route = {"level_1": {"role": "Approver", "user": None}, "level_2": {}, "level_3": {}}
    monkeypatch.setattr(ic_module, "get_active_setting_meta", lambda cc: {"name": "SETTING"})
    monkeypatch.setattr(
        ic_module,
        "get_approval_route",
        lambda cc, accounts, amount, setting_meta=None: route,
    )

    doc = InternalChargeRequest()
    doc.expense_request = "ER-001"
    doc.company = "TC"
    doc.fiscal_year = "2024"
    doc.source_cost_center = "CC-SOURCE"
    doc.total_amount = 300
    line = types.SimpleNamespace(target_cost_center="CC-TGT", amount=300, line_status=None)
    doc.internal_charge_lines = [line]

    doc.validate()

    assert line.route_snapshot
    assert line.line_status == "Pending L1"
    assert doc.status == "Pending Approval"


def test_create_internal_charge_from_expense_request(monkeypatch):
    _patch_settings(monkeypatch, enable_internal_charge=1)

    class _DummyIC:
        def __init__(self):
            self.internal_charge_lines = []
            self.name = "IC-001"

        def append(self, table, row):
            self.internal_charge_lines.append(row)

        def insert(self, **kwargs):
            return self

    er = types.SimpleNamespace(
        name="ER-001",
        allocation_mode="Allocated via Internal Charge",
        cost_center="CC-001",
        fiscal_year="2024",
        request_date="2024-03-01",
        internal_charge_request=None,
        items=[types.SimpleNamespace(expense_account="5110", amount=250)],
    )
    frappe.utils = types.SimpleNamespace(nowdate=lambda: "2024-03-01")
    monkeypatch.setattr(frappe, "get_doc", lambda *args, **kwargs: er, raising=False)
    monkeypatch.setattr(frappe, "new_doc", lambda dt: _DummyIC(), raising=False)
    monkeypatch.setattr(utils, "resolve_company_from_cost_center", lambda cc: "TC", raising=False)
    monkeypatch.setattr(frappe.utils, "nowdate", lambda: "2024-03-01", raising=False)
    er.db_set = lambda field, value: setattr(er, field, value)

    ic_name = workflow.create_internal_charge_from_expense_request(er.name)

    assert ic_name == "IC-001"
    assert er.internal_charge_request == "IC-001"


def test_reserve_budget_for_request(monkeypatch):
    settings = _patch_settings(monkeypatch, enable_budget_lock=1, lock_on_workflow_state="Approved")
    settings["allow_budget_overrun_role"] = None

    er = types.SimpleNamespace(
        name="ER-LOCK",
        status="Approved",
        cost_center="CC-100",
        project=None,
        branch=None,
        allocation_mode="Direct",
        budget_lock_status=None,
        items=[types.SimpleNamespace(expense_account="5110", amount=300)],
    )

    posted = []
    monkeypatch.setattr(utils, "resolve_company_from_cost_center", lambda cc: "TC", raising=False)
    monkeypatch.setattr(utils, "resolve_fiscal_year", lambda fy: "2024", raising=False)
    monkeypatch.setattr(service, "check_budget_available", lambda dims, amount: service.BudgetCheckResult(True, "ok", available=1000, snapshot={}), raising=False)
    monkeypatch.setattr(ledger, "post_entry", lambda *args, **kwargs: posted.append({"entry_type": args[0], "amount": args[2]}) or "BCE-1", raising=False)

    er.db_set = lambda field, value: setattr(er, field, value)

    workflow.reserve_budget_for_request(er, trigger_action="Approve", next_state="Approved")

    assert any(row["entry_type"] == "RESERVATION" for row in posted)
    assert er.budget_lock_status == "Locked"
