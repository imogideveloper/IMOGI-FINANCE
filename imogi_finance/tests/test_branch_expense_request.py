import sys
import types

import pytest


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
frappe._ = lambda msg: msg


class _Throw(Exception):
	pass


def _throw(msg=None, title=None):
	raise _Throw(msg or title)


frappe.throw = _throw
frappe.session = types.SimpleNamespace(user="tester@example.com")
frappe.db = types.SimpleNamespace(
	get_value=lambda *args, **kwargs: None,
)
frappe.get_cached_value = lambda *args, **kwargs: None
frappe._dict = lambda value=None: types.SimpleNamespace(**(value or {}))
frappe.get_cached_doc = lambda *args, **kwargs: frappe._dict(
	{
		"enable_branch_expense_request": 1,
		"default_expense_account": None,
		"require_employee": 0,
	}
)
frappe.get_single = lambda *args, **kwargs: frappe.get_cached_doc(*args, **kwargs)
frappe.utils = types.SimpleNamespace(
	flt=lambda value, precision=None: float(value or 0),
	nowdate=lambda: "2024-01-01",
)
sys.modules["frappe.utils"] = frappe.utils


class _Document:
	def __init__(self, **kwargs):
		for key, value in kwargs.items():
			setattr(self, key, value)

	def get(self, key, default=None):
		return getattr(self, key, default)

	def append(self, table, row):
		getattr(self, table).append(row)


sys.modules["frappe.model"] = types.SimpleNamespace()
sys.modules["frappe.model.document"] = types.SimpleNamespace(Document=_Document)

from imogi_finance.imogi_finance.doctype.branch_expense_request.branch_expense_request import (
	BranchExpenseRequest,
)


def _item(**overrides):
	defaults = {
		"description": "Item",
		"qty": 1,
		"rate": 1000,
		"cost_center": "CC-01",
	}
	defaults.update(overrides)
	return frappe._dict(defaults)


def _make_request(items=None, **overrides):
	defaults = {
		"company": "Test Company",
		"branch": "BR-01",
		"purpose": "Testing",
		"currency": "IDR",
		"items": items or [],
		"docstatus": overrides.pop("docstatus", 0),
	}
	defaults.update(overrides)
	return BranchExpenseRequest(**defaults)


def test_submit_fails_without_items():
	request = _make_request(items=[])
	with pytest.raises(_Throw):
		request.validate()


def test_cost_center_required_per_item():
	request = _make_request(items=[_item(cost_center=None)])
	with pytest.raises(_Throw):
		request.validate()


def test_total_amount_computed_and_positive_qty():
	items = [_item(qty=2, rate=2500), _item(qty=1, rate=1500, cost_center="CC-02")]
	request = _make_request(items=items)

	request.validate()

	assert request.items[0].amount == 5000
	assert request.items[1].amount == 1500
	assert request.total_amount == 6500


def test_cancel_updates_status():
	request = _make_request(items=[_item()])
	request.on_cancel()
	assert request.status == BranchExpenseRequest.STATUS_CANCELLED
