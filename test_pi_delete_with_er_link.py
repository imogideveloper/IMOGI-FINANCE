"""
Test Purchase Invoice deletion when linked to Expense Request.

This test verifies that a draft PI can be deleted even when it has
a link to an Expense Request, which was previously causing LinkExistsError.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPIDeleteWithERLink(FrappeTestCase):
    def setUp(self):
        """Setup test data."""
        # Create a test company and cost center if not exists
        if not frappe.db.exists("Company", "_Test Company"):
            company = frappe.get_doc({
                "doctype": "Company",
                "company_name": "_Test Company",
                "country": "Indonesia",
                "default_currency": "IDR"
            })
            company.insert(ignore_if_duplicate=True)
        
        # Create test cost center
        if not frappe.db.exists("Cost Center", "_Test Cost Center - _TC"):
            cc = frappe.get_doc({
                "doctype": "Cost Center",
                "cost_center_name": "_Test Cost Center",
                "parent_cost_center": "_Test Company - _TC",
                "company": "_Test Company"
            })
            cc.insert(ignore_if_duplicate=True)
        
        # Create test supplier
        if not frappe.db.exists("Supplier", "_Test Supplier PI Delete"):
            supplier = frappe.get_doc({
                "doctype": "Supplier",
                "supplier_name": "_Test Supplier PI Delete",
                "supplier_group": "All Supplier Groups",
                "supplier_type": "Company"
            })
            supplier.insert(ignore_if_duplicate=True)
    
    def test_delete_draft_pi_with_er_link(self):
        """Test that draft PI can be deleted when linked to ER via linked_purchase_invoice field."""
        # Create Expense Request
        er = frappe.get_doc({
            "doctype": "Expense Request",
            "cost_center": "_Test Cost Center - _TC",
            "supplier": "_Test Supplier PI Delete",
            "description": "Test ER for PI deletion",
            "request_type": "Expense",
            "total_amount": 1000000,
            "workflow_state": "Approved",
            "linked_purchase_invoice": None  # Will be set later
        })
        er.insert()
        
        # Create draft Purchase Invoice linked to ER
        pi = frappe.get_doc({
            "doctype": "Purchase Invoice",
            "supplier": "_Test Supplier PI Delete",
            "company": "_Test Company",
            "imogi_expense_request": er.name,  # Link to ER
            "items": [{
                "item_code": "_Test Item",
                "qty": 1,
                "rate": 1000000,
                "expense_account": "Cost of Goods Sold - _TC",
                "cost_center": "_Test Cost Center - _TC"
            }]
        })
        pi.insert()
        
        # Simulate ER having a link back to PI (this causes LinkExistsError)
        frappe.db.set_value("Expense Request", er.name, "linked_purchase_invoice", pi.name)
        frappe.db.commit()
        
        # Verify link exists
        er.reload()
        self.assertEqual(er.linked_purchase_invoice, pi.name)
        
        # This should NOT raise LinkExistsError anymore
        try:
            pi.delete()
            deletion_successful = True
        except frappe.exceptions.LinkExistsError:
            deletion_successful = False
        
        self.assertTrue(deletion_successful, "PI deletion should succeed even with ER link")
        
        # Verify PI is deleted
        self.assertFalse(frappe.db.exists("Purchase Invoice", pi.name))
        
        # Verify ER link is cleared
        er.reload()
        self.assertIsNone(er.linked_purchase_invoice)
        
        # Cleanup
        er.delete()
    
    def test_delete_submitted_pi_with_er_link_should_require_cancel(self):
        """Test that submitted PI cannot be deleted directly - must be cancelled first."""
        # Create and submit Expense Request
        er = frappe.get_doc({
            "doctype": "Expense Request",
            "cost_center": "_Test Cost Center - _TC",
            "supplier": "_Test Supplier PI Delete",
            "description": "Test ER for submitted PI",
            "request_type": "Expense",
            "total_amount": 1000000,
            "workflow_state": "Approved"
        })
        er.insert()
        er.submit()
        
        # Create and submit Purchase Invoice
        pi = frappe.get_doc({
            "doctype": "Purchase Invoice",
            "supplier": "_Test Supplier PI Delete",
            "company": "_Test Company",
            "imogi_expense_request": er.name,
            "items": [{
                "item_code": "_Test Item",
                "qty": 1,
                "rate": 1000000,
                "expense_account": "Cost of Goods Sold - _TC",
                "cost_center": "_Test Cost Center - _TC"
            }]
        })
        pi.insert()
        
        # Mock budget consumption to avoid errors
        pi.flags.ignore_validate = True
        pi.submit()
        
        # Submitted docs should require cancel first
        with self.assertRaises(frappe.exceptions.ValidationError):
            pi.delete()
        
        # Cancel then delete should work
        pi.cancel()
        pi.delete()
        
        # Cleanup
        er.cancel()
        er.delete()


def run_test():
    """Helper function to run the test from console."""
    import unittest
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPIDeleteWithERLink)
    unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    run_test()
