"""Unit tests for ApprovalService (reusable multi-level approval state machine)."""
import pytest
from unittest.mock import Mock, MagicMock, patch

from imogi_finance.services.approval_service import ApprovalService


@pytest.fixture
def approval_service():
    """Create ApprovalService instance."""
    return ApprovalService(doctype="Test Request", state_field="workflow_state")


@pytest.fixture
def mock_document():
    """Create a mock document with approval fields."""
    doc = Mock()
    doc.name = "TEST-001"
    doc.docstatus = 0
    doc.workflow_state = None
    doc.status = None
    doc.current_approval_level = 0
    doc.level_1_user = "approver1@example.com"
    doc.level_2_user = "approver2@example.com"
    doc.level_3_user = None
    doc.approved_on = None
    doc.rejected_on = None
    doc.approval_route_snapshot = None
    doc.flags = Mock()
    doc.flags.workflow_action_allowed = False
    return doc


class TestBeforeSubmit:
    """Test before_submit() initialization of approval state."""

    def test_before_submit_with_approvers_sets_pending_review(self, approval_service, mock_document):
        """When route has approvers, should set state to Pending Review at level 1."""
        route = {
            "level_1": {"user": "approver1@example.com"},
            "level_2": {"user": "approver2@example.com"},
        }
        
        approval_service.before_submit(mock_document, route=route)
        
        assert mock_document.workflow_state == "Pending Review"
        assert mock_document.status == "Pending Review"
        assert mock_document.current_approval_level == 1
        assert mock_document.flags.workflow_action_allowed is True

    def test_before_submit_no_approvers_auto_approves(self, approval_service, mock_document):
        """When route has no approvers, should auto-approve."""
        route = {"level_1": {}, "level_2": {}, "level_3": {}}
        
        approval_service.before_submit(mock_document, route=route)
        
        assert mock_document.workflow_state == "Approved"
        assert mock_document.status == "Approved"
        assert mock_document.current_approval_level == 0

    def test_before_submit_auto_approve_flag(self, approval_service, mock_document):
        """When auto_approve=True, should set to Approved regardless of route."""
        route = {
            "level_1": {"user": "approver1@example.com"},
            "level_2": {"user": "approver2@example.com"},
        }
        
        approval_service.before_submit(mock_document, route=route, auto_approve=True)
        
        assert mock_document.workflow_state == "Approved"
        assert mock_document.current_approval_level == 0

    def test_before_submit_skip_approval_deprecated(self, approval_service, mock_document):
        """When skip_approval=True (deprecated), should set to Approved."""
        route = {
            "level_1": {"user": "approver1@example.com"},
        }
        
        approval_service.before_submit(mock_document, route=route, skip_approval=True)
        
        assert mock_document.workflow_state == "Approved"
        assert mock_document.current_approval_level == 0

    def test_before_submit_initial_level_is_first_configured(self, approval_service, mock_document):
        """When L1 not configured but L2 is, should start at L2."""
        route = {
            "level_1": {},
            "level_2": {"user": "approver2@example.com"},
            "level_3": {},
        }
        
        approval_service.before_submit(mock_document, route=route)
        
        assert mock_document.current_approval_level == 2
        assert mock_document.workflow_state == "Pending Review"


class TestBeforeWorkflowAction:
    """Test before_workflow_action() - guard + validate approver."""

    @patch("imogi_finance.services.approval_service.frappe")
    def test_before_workflow_action_submit(self, mock_frappe, approval_service, mock_document):
        """Submit action should initialize via before_submit."""
        route = {"level_1": {"user": "approver1@example.com"}}
        
        approval_service.before_workflow_action(mock_document, action="Submit", route=route)
        
        assert mock_document.workflow_state == "Pending Review"
        assert mock_document.current_approval_level == 1

    @patch("imogi_finance.services.approval_service.frappe")
    def test_before_workflow_action_approve_as_correct_user(self, mock_frappe, approval_service, mock_document):
        """Approve action by correct user should pass."""
        mock_frappe.session.user = "approver1@example.com"
        mock_document.workflow_state = "Pending Review"
        mock_document.current_approval_level = 1
        route = {"level_1": {"user": "approver1@example.com"}}
        
        # Should not raise
        approval_service.before_workflow_action(mock_document, action="Approve", route=route)

    @patch("imogi_finance.services.approval_service.frappe")
    def test_before_workflow_action_approve_as_wrong_user_throws(self, mock_frappe, approval_service, mock_document):
        """Approve action by wrong user should throw."""
        mock_frappe.session.user = "wrong_user@example.com"
        mock_frappe.throw = Mock(side_effect=Exception("Not authorized"))
        mock_document.workflow_state = "Pending Review"
        mock_document.current_approval_level = 1
        route = {"level_1": {"user": "approver1@example.com"}}
        
        with pytest.raises(Exception):
            approval_service.before_workflow_action(mock_document, action="Approve", route=route)

    @patch("imogi_finance.services.approval_service.frappe")
    def test_before_workflow_action_approve_not_pending_returns_early(self, mock_frappe, approval_service, mock_document):
        """Approve on non-Pending document should return early."""
        mock_document.workflow_state = "Approved"
        
        approval_service.before_workflow_action(mock_document, action="Approve")
        
        # Should not raise (early return)
        assert mock_document.workflow_state == "Approved"


class TestOnWorkflowAction:
    """Test on_workflow_action() - update state post-action."""

    def test_on_workflow_action_approve_with_next_level(self, approval_service, mock_document):
        """Approve when L2 exists should advance level, stay in Pending Review."""
        mock_document.workflow_state = "Pending Review"
        mock_document.current_approval_level = 1
        mock_document.level_2_user = "approver2@example.com"  # L2 exists
        
        approval_service.on_workflow_action(mock_document, action="Approve", next_state="Pending Review")
        
        assert mock_document.workflow_state == "Pending Review"
        assert mock_document.current_approval_level == 2

    def test_on_workflow_action_approve_final_level(self, approval_service, mock_document):
        """Approve at final level should set Approved."""
        mock_document.workflow_state = "Pending Review"
        mock_document.current_approval_level = 2
        mock_document.level_3_user = None  # No L3
        mock_document.approved_on = None
        
        approval_service.on_workflow_action(mock_document, action="Approve", next_state="Approved")
        
        assert mock_document.workflow_state == "Approved"
        assert mock_document.status == "Approved"
        assert mock_document.current_approval_level == 0
        assert mock_document.approved_on is not None

    def test_on_workflow_action_reject(self, approval_service, mock_document):
        """Reject should set state to Rejected."""
        mock_document.workflow_state = "Pending Review"
        mock_document.rejected_on = None
        
        approval_service.on_workflow_action(mock_document, action="Reject", next_state="Rejected")
        
        assert mock_document.workflow_state == "Rejected"
        assert mock_document.status == "Rejected"
        assert mock_document.current_approval_level == 0
        assert mock_document.rejected_on is not None

    def test_on_workflow_action_reopen(self, approval_service, mock_document):
        """Reopen should reset to Pending Review level 1 if approvers exist."""
        mock_document.workflow_state = "Approved"
        mock_document.current_approval_level = 0
        mock_document.approval_route_snapshot = '{"level_1": {"user": "approver1@example.com"}}'
        
        approval_service.on_workflow_action(mock_document, action="Reopen", next_state="Pending Review")
        
        assert mock_document.workflow_state == "Pending Review"
        assert mock_document.current_approval_level == 1

    def test_on_workflow_action_create_pi_no_update(self, approval_service, mock_document):
        """Create PI action should not update state (handled in before_workflow_action)."""
        initial_state = "Approved"
        mock_document.workflow_state = initial_state
        
        approval_service.on_workflow_action(mock_document, action="Create PI", next_state="PI Created")
        
        # State not updated (Create PI is special, handled elsewhere)
        assert mock_document.workflow_state == initial_state


class TestGuardStatusChanges:
    """Test guard_status_changes() - prevent status bypass."""

    @patch("imogi_finance.services.approval_service.frappe")
    def test_guard_allows_workflow_changes(self, mock_frappe, approval_service, mock_document):
        """When workflow_action_allowed flag is set, should allow status change."""
        mock_document.flags.workflow_action_allowed = True
        
        # Should not raise
        approval_service.guard_status_changes(mock_document)

    @patch("imogi_finance.services.approval_service.frappe")
    def test_guard_blocks_manual_status_change(self, mock_frappe, approval_service, mock_document):
        """Manual status change (docstatus 1) without flag should raise."""
        mock_frappe.flags.in_patch = False
        mock_frappe.flags.in_install = False
        mock_frappe.throw = Mock(side_effect=Exception("Status bypass blocked"))
        
        previous = Mock()
        previous.docstatus = 1
        previous.status = "Pending Review"
        
        mock_document.docstatus = 1
        mock_document.status = "Approved"
        mock_document._doc_before_save = previous
        mock_document.flags.workflow_action_allowed = False
        
        with pytest.raises(Exception):
            approval_service.guard_status_changes(mock_document)

    def test_guard_ignores_status_unchanged(self, approval_service, mock_document):
        """If status didn't change, should not raise."""
        previous = Mock()
        previous.docstatus = 1
        previous.status = "Pending Review"
        
        mock_document.docstatus = 1
        mock_document.status = "Pending Review"
        mock_document._doc_before_save = previous
        
        # Should not raise
        approval_service.guard_status_changes(mock_document)


class TestSyncStateToStatus:
    """Test sync_state_to_status() - keep status in sync."""

    def test_sync_copies_workflow_state_to_status(self, approval_service, mock_document):
        """Should copy workflow_state value to status field."""
        mock_document.workflow_state = "Pending Review"
        
        approval_service.sync_state_to_status(mock_document)
        
        assert mock_document.status == "Pending Review"
        assert mock_document.flags.workflow_action_allowed is True

    def test_sync_ignores_empty_workflow_state(self, approval_service, mock_document):
        """Should not change status if workflow_state is empty."""
        mock_document.workflow_state = None
        mock_document.status = "Draft"
        
        approval_service.sync_state_to_status(mock_document)
        
        assert mock_document.status == "Draft"


class TestPrivateHelpers:
    """Test private helper methods."""

    def test_has_approver_returns_true_when_approver_exists(self, approval_service):
        """Should return True if any level has a user."""
        route = {
            "level_1": {},
            "level_2": {"user": "approver2@example.com"},
        }
        
        assert approval_service._has_approver(route) is True

    def test_has_approver_returns_false_when_no_approver(self, approval_service):
        """Should return False if no level has a user."""
        route = {
            "level_1": {},
            "level_2": {},
            "level_3": {},
        }
        
        assert approval_service._has_approver(route) is False

    def test_get_initial_level_returns_first_configured(self, approval_service):
        """Should return first configured level number."""
        route = {
            "level_1": {},
            "level_2": {"user": "approver2@example.com"},
            "level_3": {"user": "approver3@example.com"},
        }
        
        assert approval_service._get_initial_level(route) == 2

    def test_has_next_level_returns_true(self, approval_service, mock_document):
        """Should return True if next level is configured."""
        mock_document.current_approval_level = 1
        mock_document.level_2_user = "approver2@example.com"
        
        assert approval_service._has_next_level(mock_document) is True

    def test_has_next_level_returns_false(self, approval_service, mock_document):
        """Should return False if no next level."""
        mock_document.current_approval_level = 2
        mock_document.level_3_user = None
        
        assert approval_service._has_next_level(mock_document) is False
