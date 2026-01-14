"""
Purchase Invoice overrides for Payment Entry creation
"""
import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry as erpnext_get_payment_entry


@frappe.whitelist()
def get_payment_entry(dt, dn, party_amount=None, bank_account=None, bank_amount=None):
    """
    Override ERPNext get_payment_entry to include imogi_expense_request field
    
    This ensures when user clicks "Make > Payment Entry" from Purchase Invoice,
    the Expense Request link is automatically populated.
    """
    # Call original ERPNext method
    payment_entry = erpnext_get_payment_entry(dt, dn, party_amount, bank_account, bank_amount)
    
    # If source is Purchase Invoice, copy imogi_expense_request field
    if dt == "Purchase Invoice":
        pi = frappe.get_doc("Purchase Invoice", dn)
        expense_request = getattr(pi, "imogi_expense_request", None)
        
        if expense_request:
            payment_entry.imogi_expense_request = expense_request
            frappe.logger().info(
                f"[get_payment_entry override] Copied ER {expense_request} from PI {dn} to PE"
            )
    
    return payment_entry
