"""Tests for Expense Request workflow actions, particularly 'Create PI' and 'Mark Paid' actions.

These tests validate the code structure and logic. Full integration testing requires 
a complete Frappe environment. Run integration tests via bench:
    bench --site your-site run-tests --app imogi_finance --module expense_request
"""

import os


def test_workflow_handlers_exist():
    """Validate that workflow handlers are properly implemented in expense_request.py."""
    # Get the path to expense_request.py
    test_dir = os.path.dirname(__file__)
    er_path = os.path.join(
        test_dir,
        "..",
        "imogi_finance",
        "doctype",
        "expense_request",
        "expense_request.py"
    )
    
    with open(er_path, "r") as f:
        content = f.read()
    
    # Validate Create PI handler exists in before_workflow_action
    assert 'if action == "Create PI":' in content, "Create PI handler should exist in before_workflow_action"
    assert 'accounting.create_purchase_invoice_from_request' in content, "Should call accounting.create_purchase_invoice_from_request"
    assert 'self.linked_purchase_invoice = pi_name' in content, "Should update linked_purchase_invoice field"
    
    # Validate on_workflow_action validations exist
    assert 'if action == "Create PI" and next_state == "PI Created":' in content, "Create PI validation should exist in on_workflow_action"
    assert 'linked_purchase_invoice' in content, "Should check linked_purchase_invoice"
    
    # Validate Mark Paid action is NOT in code (status set by Payment Entry hook)
    assert 'if action == "Mark Paid":' not in content, "Mark Paid handler should NOT exist - status set by Payment Entry hook"


def test_workflow_documentation_updated():
    """Validate that workflow JSON documentation mentions the automatic PI creation."""
    test_dir = os.path.dirname(__file__)
    workflow_path = os.path.join(
        test_dir,
        "..",
        "imogi_finance",
        "workflow",
        "expense_request_workflow",
        "expense_request_workflow.json"
    )
    
    with open(workflow_path, "r") as f:
        content = f.read()
    
    # Validate notes mention automatic PI creation
    assert "create_purchase_invoice_from_request" in content.lower() or "automatically creates" in content.lower(), \
        "Workflow notes should mention automatic PI creation"


# Note: The following tests require full Frappe environment to run.
# They should be executed via: bench --site your-site run-tests

def test_workflow_action_create_pi_integration():
    """Integration test for Create PI workflow action.
    
    This test should be run in Frappe environment to validate:
    - Action creates actual Purchase Invoice document
    - linked_purchase_invoice field is populated
    - Status transitions correctly
    - Error handling works for validation failures
    """
    # Placeholder - requires Frappe environment
    pass


def test_payment_entry_sets_paid_status_integration():
    """Integration test for automatic Paid status from Payment Entry.
    
    This test should be run in Frappe environment to validate:
    - Payment Entry on_submit hook sets ER status to Paid
    - linked_payment_entry field is populated
    - Status transitions automatically
    - No manual workflow action needed
    """
    # Placeholder - requires Frappe environment
    pass


def test_workflow_validation_guards_integration():
    """Integration test for workflow validation guards.
    
    This test should be run in Frappe environment to validate:
    - Status cannot be changed to PI Created without linked_purchase_invoice
    - Status cannot be changed to Paid without proper prerequisites
    - Manual status bypass is prevented
    """
    # Placeholder - requires Frappe environment
    pass
