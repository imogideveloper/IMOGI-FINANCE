import sys
import types

import pytest

frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
frappe._ = lambda msg, *args, **kwargs: msg
frappe.session = types.SimpleNamespace(user="user@example.com")
frappe._dict = lambda value=None, **kwargs: types.SimpleNamespace(**(value or {}), **kwargs)


class _Throw(Exception):
    pass


def _throw(message=None, *args, **kwargs):
    raise _Throw(message)


frappe.throw = _throw
frappe.get_cached_value = lambda *args, **kwargs: "IDR"
frappe.get_attr = lambda path: (lambda posting_date, company=None, as_dict=False: {"name": "FY-2024"})
frappe.db = types.SimpleNamespace(get_value=lambda *args, **kwargs: None, exists=lambda *args, **kwargs: False)

frappe.utils = types.SimpleNamespace(
    cint=lambda value, *args, **kwargs: int(value),
    flt=lambda value, *args, **kwargs: float(value),
    nowdate=lambda: "2024-03-01",
    get_first_day=lambda value: value,
    get_last_day=lambda value: value,
    get_site_path=lambda *args, **kwargs: "/tmp",
)
sys.modules["frappe.utils"] = frappe.utils


class Document:
    def get(self, key, default=None):
        return getattr(self, key, default)


sys.modules["frappe.model.document"] = types.SimpleNamespace(Document=Document)


from imogi_finance.budget_control import service  # noqa: E402
from imogi_finance.imogi_finance.doctype.branch_expense_request import branch_expense_request  # noqa: E402


def _settings(**overrides):
    base = {
        "enable_branch_expense_request": 1,
        "default_expense_account": "5110",
        "require_employee": 0,
        "enable_budget_check": 1,
        "budget_block_on_over": 1,
        "budget_warn_on_over": 0,
        "budget_check_basis": "Fiscal Year",
    }
    base.update(overrides)
    return frappe._dict(base)


def _fake_dims(**kwargs):
    return types.SimpleNamespace(**kwargs)


def _fake_budget_result(available):
    return service.BudgetCheckResult(
        ok=available >= 0,
        message=f"available {available}",
        available=available,
        snapshot={"available": available, "allocated": 1_000},
    )


def _build_request(monkeypatch, *, available_map):
    frappe.throw = _throw
    monkeypatch.setattr(branch_expense_request, "get_settings", lambda: _settings(), raising=False)
    monkeypatch.setattr(
        branch_expense_request.service,
        "resolve_dims",
        lambda **kwargs: _fake_dims(**kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        branch_expense_request.service,
        "check_budget_available",
        lambda dims, amount, **kwargs: _fake_budget_result(available_map.get(dims.cost_center, amount)),
        raising=False,
    )

    doc = branch_expense_request.BranchExpenseRequest()
    doc.company = "TC"
    doc.posting_date = "2024-03-15"
    doc.branch = "BR-1"
    doc.items = [
        types.SimpleNamespace(qty=1, rate=100, amount=100, cost_center="CC-OK", expense_account="5110", project=None),
        types.SimpleNamespace(qty=1, rate=600, amount=600, cost_center="CC-OVR", expense_account="5110", project=None),
    ]
    return doc


def test_validate_sets_amount_and_expense_account(monkeypatch):
    doc = _build_request(monkeypatch, available_map={"CC-OK": 500, "CC-OVR": 500})

    doc.validate()

    assert doc.amount == 700
    assert doc.expense_account == "5110"
    assert doc.expense_accounts == ("5110",)


def test_validate_requires_ppn_template(monkeypatch):
    doc = _build_request(monkeypatch, available_map={"CC-OK": 500, "CC-OVR": 500})
    doc.is_ppn_applicable = 1
    doc.ppn_template = None

    with pytest.raises(_Throw):
        doc.validate()


def test_validate_requires_pph_base_amount(monkeypatch):
    doc = _build_request(monkeypatch, available_map={"CC-OK": 500, "CC-OVR": 500})
    doc.is_pph_applicable = 1
    doc.pph_type = "PPh 23"
    doc.pph_base_amount = None

    with pytest.raises(_Throw):
        doc.validate()


def test_validate_requires_item_pph_base(monkeypatch):
    doc = _build_request(monkeypatch, available_map={"CC-OK": 500, "CC-OVR": 500})
    doc.is_pph_applicable = 0
    doc.pph_type = "PPh 23"
    doc.items[0].is_pph_applicable = 1
    doc.items[0].pph_base_amount = None

    with pytest.raises(_Throw):
        doc.validate()


def test_budget_check_over_budget_blocks_submit(monkeypatch):
    doc = _build_request(monkeypatch, available_map={"CC-OK": 1000, "CC-OVR": 400})

    doc.validate()

    assert doc.fiscal_year == "FY-2024"
    assert doc.budget_check_status == "Over Budget"
    assert doc.items[0].budget_result == "OK"
    assert doc.items[1].budget_result == "Over Budget"

    with pytest.raises(_Throw):
        doc.before_submit()


def test_budget_warning_allows_submit(monkeypatch):
    monkeypatch.setattr(
        branch_expense_request,
        "get_settings",
        lambda: _settings(budget_warn_on_over=1, budget_block_on_over=0),
        raising=False,
    )
    monkeypatch.setattr(
        branch_expense_request.service,
        "resolve_dims",
        lambda **kwargs: _fake_dims(**kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        branch_expense_request.service,
        "check_budget_available",
        lambda dims, amount, **kwargs: _fake_budget_result(100),
        raising=False,
    )

    doc = branch_expense_request.BranchExpenseRequest()
    doc.company = "TC"
    doc.posting_date = "2024-04-01"
    doc.branch = "BR-2"
    doc.items = [types.SimpleNamespace(qty=1, rate=150, amount=150, cost_center="CC-1", expense_account=None, project=None)]

    doc.validate()
    assert doc.budget_check_status == "Warning"
    assert doc.items[0].budget_result == "Warning"

    # Should not raise because warn_only mode is on
    doc.before_submit()
