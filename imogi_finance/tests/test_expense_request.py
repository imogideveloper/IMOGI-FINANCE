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


class DoesNotExistError(Exception):
    pass


class ValidationError(Exception):
    pass


def _throw(msg=None, title=None):
    raise NotAllowed(msg or title)


frappe.throw = _throw
frappe.DoesNotExistError = DoesNotExistError
frappe.ValidationError = ValidationError


@pytest.fixture(autouse=True)
def _reset_frappe(monkeypatch):
    monkeypatch.setattr(frappe, "throw", _throw, raising=False)
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user=None), raising=False)
    monkeypatch.setattr(frappe, "get_roles", lambda: [], raising=False)
    monkeypatch.setattr(frappe, "conf", types.SimpleNamespace(), raising=False)
    monkeypatch.setattr(frappe, "db", types.SimpleNamespace(), raising=False)
    monkeypatch.setattr(frappe.db, "set_value", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(frappe.db, "exists", lambda *args, **kwargs: False, raising=False)
    monkeypatch.setattr(frappe, "get_all", lambda *args, **kwargs: [], raising=False)
    monkeypatch.setattr(frappe, "log_error", lambda *args, **kwargs: None, raising=False)

frappe_model = types.ModuleType("frappe.model")
frappe_model_document = types.ModuleType("frappe.model.document")


class Document:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.flags = types.SimpleNamespace()

    def get(self, key, default=None):
        return getattr(self, key, default)


frappe_model_document.Document = Document
sys.modules["frappe.model"] = frappe_model
sys.modules["frappe.model.document"] = frappe_model_document

from imogi_finance.approval import get_approval_route  # noqa: E402
from imogi_finance.imogi_finance.doctype.expense_approval_setting.expense_approval_setting import (  # noqa: E402
    ExpenseApprovalSetting,
)
from imogi_finance.imogi_finance.doctype.expense_request.expense_request import (  # noqa: E402
    ExpenseRequest,
)


def _item(
    amount=100,
    expense_account="5000",
    is_ppn_applicable=0,
    is_pph_applicable=0,
    pph_base_amount=None,
    **overrides,
):
    return Document(
        amount=amount,
        expense_account=expense_account,
        is_ppn_applicable=is_ppn_applicable,
        is_pph_applicable=is_pph_applicable,
        pph_base_amount=pph_base_amount,
        **overrides,
    )


def _make_request(role=None, user=None, **overrides):
    defaults = {
        "status": "Pending Level 1",
        "items": [(_item())],
        "cost_center": "CC",
        "request_type": "Expense",
    }
    defaults.update(overrides)
    request = ExpenseRequest(**defaults)
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


def test_validate_requires_ppn_template_when_applicable():
    request = ExpenseRequest(
        is_ppn_applicable=1,
        request_type="Expense",
        ppn_template=None,
        items=[_item(amount=1)],
        cost_center="CC",
    )

    with pytest.raises(NotAllowed) as excinfo:
        request.validate()

    assert "PPN Template" in str(excinfo.value)


def test_validate_requires_ppn_template_when_item_applicable():
    request = ExpenseRequest(
        is_ppn_applicable=0,
        request_type="Expense",
        ppn_template=None,
        items=[_item(amount=1, is_ppn_applicable=1)],
        cost_center="CC",
    )

    request.validate()


def test_validate_requires_pph_base_amount_when_applicable():
    request = ExpenseRequest(
        is_pph_applicable=1,
        request_type="Expense",
        ppn_template=None,
        pph_type="PPh 23",
        pph_base_amount=None,
        items=[_item(amount=100)],
        cost_center="CC",
    )

    with pytest.raises(NotAllowed) as excinfo:
        request.validate()

    assert "PPh Base Amount" in str(excinfo.value)


def test_validate_requires_pph_base_amount_on_item_when_applicable():
    request = ExpenseRequest(
        is_pph_applicable=0,
        request_type="Expense",
        ppn_template=None,
        pph_type="PPh 23",
        pph_base_amount=None,
        items=[_item(amount=100, is_pph_applicable=1, pph_base_amount=None)],
        cost_center="CC",
    )

    with pytest.raises(NotAllowed) as excinfo:
        request.validate()

    assert "PPh Base Amount" in str(excinfo.value)


def test_validate_requires_pph_type_when_item_has_pph(monkeypatch):
    request = ExpenseRequest(
        is_pph_applicable=0,
        request_type="Expense",
        ppn_template=None,
        pph_type=None,
        pph_base_amount=None,
        items=[_item(amount=100, is_pph_applicable=1, pph_base_amount=50)],
        cost_center="CC",
    )

    with pytest.raises(NotAllowed) as excinfo:
        request.validate()

    assert "PPh Type" in str(excinfo.value)


def test_validate_does_not_require_base_for_non_pph_items():
    request = ExpenseRequest(
        is_pph_applicable=0,
        request_type="Expense",
        ppn_template=None,
        pph_type="PPh 23",
        pph_base_amount=None,
        items=[_item(amount=100, is_pph_applicable=0, pph_base_amount=None)],
        cost_center="CC",
    )

    request.validate()


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

    request = ExpenseRequest(
        status="Pending Level 2",
        level_2_role="Level 2 User",
        level_2_user="level2@example.com",
        level_3_user="level3@example.com",
        items=[_item()],
        cost_center="CC",
        request_type="Expense",
    )

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


def test_close_requires_any_routed_user_or_role(monkeypatch):
    request = ExpenseRequest(
        status="Linked",
        level_1_role="Expense Approver",
        level_2_user="closer@example.com",
        items=[_item()],
        cost_center="CC",
        request_type="Expense",
    )
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": "Expense Approver", "user": None},
            "level_2": {"role": None, "user": "closer@example.com"},
            "level_3": {"role": None, "user": None},
        },
    )

    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="viewer@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])

    with pytest.raises(NotAllowed):
        request.before_workflow_action("Close")


def test_close_blocks_when_not_linked(monkeypatch):
    request = ExpenseRequest(status="Approved", items=[_item()], cost_center="CC", request_type="Expense")
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="approver@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Expense Approver"])

    with pytest.raises(NotAllowed) as excinfo:
        request.before_workflow_action("Close")

    assert "Close action is only allowed when the request is Linked or already Closed." in str(excinfo.value)


def test_close_allows_routed_user_or_role(monkeypatch):
    role_request = ExpenseRequest(
        status="Linked",
        level_3_role="Finance Manager",
        items=[_item()],
        cost_center="CC",
        request_type="Expense",
    )
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": None, "user": None},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": "Finance Manager", "user": None},
        },
    )
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="manager@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Finance Manager"])
    role_request.before_workflow_action("Close")

    user_request = ExpenseRequest(
        status="Linked",
        level_1_user="closer@example.com",
        items=[_item()],
        cost_center="CC",
        request_type="Expense",
    )
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": None, "user": "closer@example.com"},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        },
    )
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="closer@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])
    user_request.before_workflow_action("Close")


def test_close_allows_configuration_override(monkeypatch):
    request = ExpenseRequest(status="Linked", name="ER-001", items=[_item()], cost_center="CC", request_type="Expense")
    comments = []
    warnings = []

    def _logger(_name=None):
        class _Dummy:
            def warning(self, *args, **kwargs):
                warnings.append((args, kwargs))

        return _Dummy()

    monkeypatch.setattr(frappe, "logger", _logger, raising=False)
    request.add_comment = lambda comment_type, text: comments.append((comment_type, text))
    monkeypatch.setattr(frappe, "conf", types.SimpleNamespace(imogi_finance_allow_unrestricted_close=True))

    request.before_workflow_action("Close")

    assert any("unrestricted override" in entry[1] for entry in comments)
    assert warnings


def test_close_revalidates_against_current_route(monkeypatch):
    request = ExpenseRequest(
        status="Linked",
        items=[_item()],
        cost_center="CC",
        expense_account="5000",
        amount=100,
        request_type="Expense",
    )
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": "Finance Approver", "user": None},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        },
    )

    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="viewer@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])
    with pytest.raises(NotAllowed):
        request.before_workflow_action("Close")

    monkeypatch.setattr(frappe, "get_roles", lambda: ["Finance Approver"])
    request.before_workflow_action("Close")


def test_reopen_requires_system_manager_role(monkeypatch):
    request = ExpenseRequest(
        status="Rejected",
        cost_center="CC",
        expense_account="5000",
        items=[_item(amount=100)],
        request_type="Expense",
    )

    monkeypatch.setattr(frappe, "get_roles", lambda: ["Viewer"])
    with pytest.raises(NotAllowed):
        request.before_workflow_action("Reopen")

    monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
    request.before_workflow_action("Reopen")


def test_reopen_refreshes_route_and_status(monkeypatch):
    captured = {}

    def _route(cost_center, accounts, amount):
        captured["args"] = (cost_center, accounts, amount)
        return {
            "level_1": {"role": "Expense Approver", "user": "approver@example.com"},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        }

    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        _route,
    )

    request = ExpenseRequest(
        status="Closed",
        cost_center="CC",
        expense_account="5000",
        amount=250,
        level_1_role="Old Role",
        level_1_user="old@example.com",
        items=[_item(amount=250)],
        request_type="Expense",
    )

    request.on_workflow_action("Reopen", next_state="Pending Level 1")

    assert captured["args"] == ("CC", ("5000",), 250)
    assert request.status == "Pending Level 1"
    assert request.level_1_role == "Expense Approver"
    assert request.level_1_user == "approver@example.com"


def test_reopen_to_draft_tracks_next_state(monkeypatch):
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": "Expense Approver", "user": None},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        },
    )
    request = ExpenseRequest(
        status="Rejected",
        cost_center="CC",
        expense_account="5000",
        items=[_item(amount=50)],
        request_type="Expense",
    )

    request.on_workflow_action("Reopen", next_state="Draft")

    assert request.status == "Draft"


def test_reopen_blocks_when_downstream_active(monkeypatch):
    request = ExpenseRequest(
        status="Closed",
        cost_center="CC",
        expense_account="5000",
        items=[_item(amount=100)],
        linked_payment_entry="PE-1",
        request_type="Expense",
    )
    monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: 1)

    with pytest.raises(NotAllowed):
        request.before_workflow_action("Reopen")


def test_reopen_allows_site_override_with_audit(monkeypatch):
    captured = {}

    def _audit(self, active_links, site_override, request_override):
        captured["active_links"] = active_links
        captured["site_override"] = site_override
        captured["request_override"] = request_override

    request = ExpenseRequest(
        status="Closed",
        cost_center="CC",
        expense_account="5000",
        items=[_item(amount=100)],
        linked_payment_entry="PE-1",
        request_type="Expense",
    )
    monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: 1)
    monkeypatch.setattr(frappe, "conf", types.SimpleNamespace(imogi_finance_allow_reopen_with_active_links=True))
    monkeypatch.setattr(ExpenseRequest, "_add_reopen_override_audit", _audit)

    request.before_workflow_action("Reopen")

    assert captured["active_links"] == ["Payment Entry PE-1"]
    assert captured["site_override"] is True
    assert captured["request_override"] is False


def test_reopen_allows_request_override_with_audit(monkeypatch):
    captured = {}

    def _audit(self, active_links, site_override, request_override):
        captured["active_links"] = active_links
        captured["site_override"] = site_override
        captured["request_override"] = request_override

    request = ExpenseRequest(
        status="Closed",
        cost_center="CC",
        expense_account="5000",
        items=[_item(amount=100)],
        linked_purchase_invoice="PI-1",
        allow_reopen_with_active_links=True,
        request_type="Expense",
    )
    monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: 1)
    monkeypatch.setattr(ExpenseRequest, "_add_reopen_override_audit", _audit)

    request.before_workflow_action("Reopen")

    assert captured["active_links"] == ["Purchase Invoice PI-1"]
    assert captured["site_override"] is False
    assert captured["request_override"] is True


def test_reopen_clears_downstream_links(monkeypatch):
    monkeypatch.setattr(frappe, "get_roles", lambda: ["System Manager"])
    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: 2)
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": "Expense Approver", "user": "approver@example.com"},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        },
    )

    request = ExpenseRequest(
        status="Closed",
        cost_center="CC",
        expense_account="5000",
        items=[_item(amount=100)],
        linked_payment_entry="PE-1",
        linked_purchase_invoice="PI-1",
        linked_asset="AST-1",
        request_type="Expense",
    )

    request.before_workflow_action("Reopen")
    request.on_workflow_action("Reopen", next_state="Pending Level 1")

    assert request.linked_payment_entry is None
    assert request.linked_purchase_invoice is None
    assert request.linked_asset is None
    assert request.pending_purchase_invoice is None
    assert request.status == "Pending Level 1"


def test_before_submit_handles_missing_route(monkeypatch):
    captured = {}

    def _raise_missing(*args, **kwargs):
        raise DoesNotExistError("missing")

    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        _raise_missing,
    )
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.log_route_resolution_error",
        lambda *args, **kwargs: captured.setdefault("called", True),
    )

    request = ExpenseRequest(
        cost_center="CC",
        expense_account="5000",
        amount=100,
        items=[_item(amount=100)],
        request_type="Expense",
    )

    with pytest.raises(NotAllowed) as excinfo:
        request.before_submit()

    assert "Approval route could not be determined" in str(excinfo.value)
    assert captured.get("called")
    assert getattr(request, "status", None) != "Pending Level 1"


def test_reopen_handles_validation_error(monkeypatch):
    captured = {}

    def _raise_validation(*args, **kwargs):
        raise ValidationError("range mismatch")

    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        _raise_validation,
    )
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.log_route_resolution_error",
        lambda *args, **kwargs: captured.setdefault("called", True),
    )

    request = ExpenseRequest(
        status="Closed",
        cost_center="CC",
        expense_account="5000",
        amount=150,
        linked_payment_entry="PE-1",
        request_type="Expense",
        items=[_item(amount=150)],
    )

    with pytest.raises(NotAllowed) as excinfo:
        request.on_workflow_action("Reopen", next_state="Pending Level 1")

    assert "Approval route could not be determined" in str(excinfo.value)
    assert captured.get("called")
    assert request.status == "Closed"
    assert request.linked_payment_entry == "PE-1"


def test_validate_blocks_key_changes_after_final_status():
    previous = ExpenseRequest(
        docstatus=1,
        status="Approved",
        request_type="Expense",
        supplier="Supplier A",
        expense_account="5000",
        amount=100,
        currency="IDR",
        cost_center="CC",
        items=[_item(amount=100)],
    )
    updated = ExpenseRequest(
        docstatus=1,
        status="Approved",
        request_type="Expense",
        supplier="Supplier A",
        expense_account="5000",
        amount=100,
        currency="IDR",
        cost_center="CC",
        items=[_item(amount=100)],
    )
    updated._doc_before_save = previous

    updated.items[0].amount = 200

    with pytest.raises(NotAllowed):
        updated.validate()


def test_validate_allows_changes_outside_final_status(monkeypatch):
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": None, "user": None},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        },
    )
    previous = ExpenseRequest(
        docstatus=1,
        status="Pending Level 1",
        request_type="Expense",
        supplier="Supplier A",
        expense_account="5000",
        amount=100,
        currency="IDR",
        cost_center="CC",
        items=[_item(amount=100)],
    )
    updated = ExpenseRequest(
        docstatus=1,
        status="Pending Level 1",
        request_type="Expense",
        supplier="Supplier A",
        expense_account="5000",
        amount=150,
        currency="IDR",
        cost_center="CC",
        items=[_item(amount=150)],
    )
    updated._doc_before_save = previous

    updated.validate()


def test_validate_restarts_route_when_key_fields_change_after_submit(monkeypatch):
    captured = {}

    def _route(cost_center, accounts, amount):
        captured["args"] = (cost_center, accounts, amount)
        return {
            "level_1": {"role": "Level 1 User", "user": "approver@example.com"},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        }

    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        _route,
    )

    previous = ExpenseRequest(
        docstatus=1,
        status="Pending Level 2",
        request_type="Expense",
        supplier="Supplier A",
        expense_account="5000",
        amount=100,
        currency="IDR",
        cost_center="CC",
        level_2_user="second@example.com",
        items=[_item(amount=100)],
    )
    updated = ExpenseRequest(
        docstatus=1,
        status="Pending Level 2",
        request_type="Expense",
        supplier="Supplier A",
        expense_account="5000",
        amount=200,
        currency="IDR",
        cost_center="CC",
        level_2_user="second@example.com",
        items=[_item(amount=200)],
    )
    updated._doc_before_save = previous

    updated.validate()

    assert captured["args"] == ("CC", ("5000",), 200)
    assert updated.status == "Pending Level 1"
    assert updated.level_1_role == "Level 1 User"
    assert updated.level_1_user == "approver@example.com"


def test_validate_allows_mixed_expense_accounts():
    request = ExpenseRequest(
        items=[_item(expense_account="5000", amount=125), _item(expense_account="6000", amount=175)],
        cost_center="CC",
        request_type="Expense",
    )

    request.validate_amounts()

    assert request.amount == 300
    assert request.expense_account is None
    assert request.expense_accounts == ("5000", "6000")


def test_before_submit_requires_level_one_approver(monkeypatch):
    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        lambda cost_center, accounts, amount: {
            "level_1": {"role": None, "user": None},
            "level_2": {"role": None, "user": None},
            "level_3": {"role": None, "user": None},
        },
    )

    request = ExpenseRequest(cost_center="CC", expense_account="5000", items=[_item(amount=100)], request_type="Expense")

    with pytest.raises(NotAllowed):
        request.before_submit()


def test_submit_requires_creator(monkeypatch):
    request = ExpenseRequest(owner="creator@example.com", status="Draft", items=[_item()], cost_center="CC", request_type="Expense")

    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="other@example.com"))
    with pytest.raises(NotAllowed):
        request.before_workflow_action("Submit")

    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="creator@example.com"))
    request.before_workflow_action("Submit")


def test_approve_requires_route_on_current_level(monkeypatch):
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="approver@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Expense Approver"])

    request = ExpenseRequest(
        status="Pending Level 2",
        level_2_role=None,
        level_2_user=None,
        items=[_item()],
        cost_center="CC",
        request_type="Expense",
    )

    with pytest.raises(NotAllowed):
        request.before_workflow_action("Approve")


def test_validate_blocks_status_change_without_workflow_action():
    previous = ExpenseRequest(
        docstatus=1,
        status="Pending Level 1",
        request_type="Expense",
        cost_center="CC",
        expense_account="5000",
        amount=100,
        items=[_item(amount=100)],
    )
    updated = ExpenseRequest(
        docstatus=1,
        status="Approved",
        request_type="Expense",
        cost_center="CC",
        expense_account="5000",
        amount=100,
        items=[_item(amount=100)],
    )
    updated._doc_before_save = previous

    with pytest.raises(NotAllowed):
        updated.validate()


def test_validate_allows_status_change_when_workflow_flagged():
    previous = ExpenseRequest(
        docstatus=1,
        status="Pending Level 1",
        request_type="Expense",
        cost_center="CC",
        expense_account="5000",
        amount=100,
        items=[_item(amount=100)],
    )
    updated = ExpenseRequest(
        docstatus=1,
        status="Approved",
        request_type="Expense",
        cost_center="CC",
        expense_account="5000",
        amount=100,
        items=[_item(amount=100)],
    )
    updated._doc_before_save = previous
    updated.flags.workflow_action_allowed = True

    updated.validate()


def test_close_uses_snapshot_when_route_missing(monkeypatch):
    request = ExpenseRequest(
        status="Linked",
        level_1_role="Expense Approver",
        items=[_item(amount=150)],
        amount=150,
        cost_center="CC",
        request_type="Expense",
    )
    request.approval_route_snapshot = {
        "level_1": {"role": "Expense Approver", "user": None},
        "level_2": {"role": None, "user": None},
        "level_3": {"role": None, "user": None},
    }

    def _raise(*args, **kwargs):
        raise ValidationError("missing configuration")

    monkeypatch.setattr(
        "imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_approval_route",
        _raise,
    )
    monkeypatch.setattr(frappe, "session", types.SimpleNamespace(user="approver@example.com"))
    monkeypatch.setattr(frappe, "get_roles", lambda: ["Expense Approver"])

    request.before_workflow_action("Close")


def test_get_approval_route_uses_default_rule(monkeypatch):
    amount = 750
    default_line = {
        "parent": "EAS-1",
        "is_default": 1,
        "min_amount": 0,
        "max_amount": 1000,
        "level_1_role": "Default Approver",
        "level_1_user": None,
        "level_2_role": None,
        "level_2_user": None,
        "level_3_role": None,
        "level_3_user": None,
    }

    monkeypatch.setattr(frappe.db, "get_value", lambda *args, **kwargs: "EAS-1")

    def _fake_get_all(doctype, filters=None, fields=None, order_by=None, limit=None):
        if filters.get("expense_account"):
            return []

        if filters.get("is_default") != 1 or filters.get("parent") != "EAS-1":
            return []

        min_filter = filters.get("min_amount")
        max_filter = filters.get("max_amount")
        if not (min_filter and max_filter):
            return []

        min_value = min_filter[1]
        max_value = max_filter[1]

        if min_value <= amount <= max_value:
            return [default_line]
        return []

    monkeypatch.setattr(frappe, "get_all", _fake_get_all, raising=False)

    route = get_approval_route("CC", ("7000",), amount)

    assert route["level_1"]["role"] == "Default Approver"


def test_expense_approval_setting_requires_default_and_contiguous_ranges():
    setting_without_default = ExpenseApprovalSetting(
        expense_approval_lines=[Document(expense_account="5000", min_amount=0, max_amount=1000)]
    )

    with pytest.raises(NotAllowed):
        setting_without_default.validate_default_lines()

    setting_with_gaps = ExpenseApprovalSetting(
        expense_approval_lines=[
            Document(is_default=1, min_amount=0, max_amount=500),
            Document(is_default=1, min_amount=750, max_amount=1000),
        ]
    )

    with pytest.raises(NotAllowed):
        setting_with_gaps.validate_amount_ranges()

    setting_valid = ExpenseApprovalSetting(
        expense_approval_lines=[
            Document(is_default=1, min_amount=0, max_amount=500),
            Document(is_default=1, min_amount=500, max_amount=1000),
        ]
    )

    setting_valid.validate_default_lines()
    setting_valid.validate_amount_ranges()
