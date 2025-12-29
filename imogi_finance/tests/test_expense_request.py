import sys
import types

import pytest


frappe = sys.modules.setdefault("frappe", types.ModuleType("frappe"))
frappe._ = lambda msg: msg
frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
frappe.session = types.SimpleNamespace(user=None)
frappe.get_roles = lambda: []


class NotAllowed(Exception):
    pass


def _throw(msg=None, title=None):
    raise NotAllowed(msg or title)


frappe.throw = _throw

frappe_model = types.ModuleType("frappe.model")
frappe_model_document = types.ModuleType("frappe.model.document")


class Document:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)


frappe_model_document.Document = Document
sys.modules["frappe.model"] = frappe_model
sys.modules["frappe.model.document"] = frappe_model_document

from imogi_finance.imogi_finance.doctype.expense_request.expense_request import (  # noqa: E402
    ExpenseRequest,
)


def _make_request(role=None, user=None):
    request = ExpenseRequest()
    request.status = "Pending Level 1"
    request.level_1_role = role
    request.level_1_user = user
    return request


def test_before_workflow_action_requires_role_when_only_role(monkeypatch):
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="approver@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Expense Approver"])

    request = _make_request(role="Expense Approver")
    request.before_workflow_action("Approve")

    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])
    request_without_role = _make_request(role="Expense Approver")

    with pytest.raises(NotAllowed) as excinfo:
        request_without_role.before_workflow_action("Approve")

    assert "role 'Expense Approver'" in str(excinfo.value)


def test_before_workflow_action_requires_exact_user_when_only_user(monkeypatch):
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="owner@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])

    request = _make_request(user="owner@example.com")
    request.before_workflow_action("Approve")

    other_user_request = _make_request(user="owner@example.com")
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="other@example.com"))

    with pytest.raises(NotAllowed) as excinfo:
        other_user_request.before_workflow_action("Approve")

    assert "user 'owner@example.com'" in str(excinfo.value)


def test_before_workflow_action_requires_both_user_and_role(monkeypatch):
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="owner@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Expense Approver"])

    request = _make_request(role="Expense Approver", user="owner@example.com")
    request.before_workflow_action("Approve")

    wrong_user = _make_request(role="Expense Approver", user="owner@example.com")
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="other@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Expense Approver"])

    with pytest.raises(NotAllowed) as excinfo:
        wrong_user.before_workflow_action("Approve")

    assert "user 'owner@example.com'" in str(excinfo.value)

    missing_role = _make_request(role="Expense Approver", user="owner@example.com")
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="owner@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])

    with pytest.raises(NotAllowed) as excinfo:
        missing_role.before_workflow_action("Approve")

    message = str(excinfo.value)
    assert "user 'owner@example.com'" in message
    assert "role 'Expense Approver'" in message


def test_before_workflow_action_blocks_skipping_level_two(monkeypatch):
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="approver@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Level 1 User"])

    request = _make_request(role="Level 1 User", user="approver@example.com")
    request.level_2_user = "second@example.com"

    with pytest.raises(NotAllowed):
        request.before_workflow_action("Approve", next_state="Approved")


def test_before_workflow_action_blocks_skipping_level_three(monkeypatch):
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="level2@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Level 2 User"])

    request = ExpenseRequest()
    request.status = "Pending Level 2"
    request.level_2_role = "Level 2 User"
    request.level_2_user = "level2@example.com"
    request.level_3_user = "level3@example.com"

    with pytest.raises(NotAllowed):
        request.before_workflow_action("Approve", next_state="Approved")


def test_before_workflow_action_allows_final_approval_when_no_next_level(monkeypatch):
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="approver@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Level 1 User"])

    request = _make_request(role="Level 1 User", user="approver@example.com")

    request.before_workflow_action("Approve", next_state="Approved")


def test_before_workflow_action_allows_routed_user_without_generic_role(monkeypatch):
    """Workflow-level roles are broad; routing still enforces the actual approver."""
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="routed@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])

    request = _make_request(user="routed@example.com")

    request.before_workflow_action("Approve")


def test_before_workflow_action_blocks_generic_role_without_route(monkeypatch):
    """Having a generic workflow role is insufficient when the route expects a specific user."""
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="other@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Level 1 User"])

    request = _make_request(user="owner@example.com")

    with pytest.raises(NotAllowed) as excinfo:
        request.before_workflow_action("Approve")

    assert "user 'owner@example.com'" in str(excinfo.value)
