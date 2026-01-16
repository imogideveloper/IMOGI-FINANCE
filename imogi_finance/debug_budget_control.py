#!/usr/bin/env python3
"""
Script untuk troubleshoot Budget Control Entry yang tidak jalan di Expense Request
Usage: bench --site <site_name> execute imogi_finance.debug_budget_control
"""

import frappe
from frappe import _


def check_settings():
    """Check Budget Control Settings"""
    print("\n" + "="*60)
    print("CHECKING BUDGET CONTROL SETTINGS")
    print("="*60)
    
    try:
        settings = frappe.get_doc("Budget Control Settings")
        
        print(f"✓ Budget Control Settings exists")
        print(f"\n📋 Current Settings:")
        print(f"  - enable_budget_lock: {settings.enable_budget_lock}")
        print(f"  - lock_on_workflow_state: {settings.lock_on_workflow_state}")
        print(f"  - enforce_mode: {settings.enforce_mode}")
        print(f"  - require_budget_controller_review: {settings.require_budget_controller_review}")
        print(f"  - allow_budget_overrun_role: {settings.allow_budget_overrun_role}")
        
        # Check if enabled
        if not settings.enable_budget_lock:
            print(f"\n❌ PROBLEM FOUND: enable_budget_lock is DISABLED")
            print(f"   Solution: Enable it in Budget Control Settings")
            return False
        else:
            print(f"\n✅ Budget lock is ENABLED")
        
        # Check fiscal year
        print(f"\n" + "="*60)
        print("CHECKING FISCAL YEAR CONFIGURATION")
        print("="*60)
        
        from imogi_finance.budget_control import utils
        fiscal_year = utils.resolve_fiscal_year(None)
        
        if not fiscal_year:
            print(f"❌ PROBLEM FOUND: Fiscal Year cannot be resolved")
            print(f"   Checked:")
            print(f"   - User defaults: Not set")
            print(f"   - Global defaults: Not set")
            print(f"   - System Settings: Not set")
            print(f"   - Current date lookup: Failed")
            print(f"\n   Solution:")
            print(f"   1. Set 'Current Fiscal Year' in System Settings, OR")
            print(f"   2. Set user default: frappe.defaults.set_user_default('fiscal_year', 'YYYY-YYYY')")
            return False
        else:
            print(f"✅ Fiscal Year resolved: {fiscal_year}")
            print(f"   This will be used for Budget Control Entries")
            
        return True
        
    except Exception as e:
        print(f"❌ ERROR: Cannot load Budget Control Settings")
        print(f"   Error: {str(e)}")
        return False


def check_expense_request(er_name=None):
    """Check specific Expense Request"""
    print("\n" + "="*60)
    print("CHECKING EXPENSE REQUEST")
    print("="*60)
    
    if not er_name:
        # Get latest approved ER
        ers = frappe.get_all(
            "Expense Request",
            filters={"workflow_state": "Approved"},
            fields=["name", "status", "workflow_state", "budget_lock_status", "modified"],
            order_by="modified desc",
            limit=1
        )
        
        if not ers:
            print("❌ No approved Expense Request found")
            return None
            
        er_name = ers[0].name
        print(f"📄 Checking latest approved ER: {er_name}")
    else:
        print(f"📄 Checking ER: {er_name}")
    
    try:
        er = frappe.get_doc("Expense Request", er_name)
        
        print(f"\n📋 ER Details:")
        print(f"  - Name: {er.name}")
        print(f"  - Status: {er.status}")
        print(f"  - Workflow State: {er.workflow_state}")
        print(f"  - Budget Lock Status: {getattr(er, 'budget_lock_status', 'N/A')}")
        print(f"  - Budget Workflow State: {getattr(er, 'budget_workflow_state', 'N/A')}")
        print(f"  - Cost Center: {er.cost_center}")
        print(f"  - Total Amount: {er.total_amount}")
        
        return er
        
    except Exception as e:
        print(f"❌ ERROR: Cannot load Expense Request {er_name}")
        print(f"   Error: {str(e)}")
        return None


def check_budget_entries(ref_name):
    """Check Budget Control Entries for a reference"""
    print("\n" + "="*60)
    print("CHECKING BUDGET CONTROL ENTRIES")
    print("="*60)
    
    entries = frappe.get_all(
        "Budget Control Entry",
        filters={
            "ref_doctype": "Expense Request",
            "ref_name": ref_name
        },
        fields=["name", "entry_type", "direction", "amount", "cost_center", "account", "docstatus"],
        order_by="creation desc"
    )
    
    if not entries:
        print(f"❌ NO Budget Control Entries found for ER: {ref_name}")
        print(f"\n🔍 This is the PROBLEM - RESERVATION entries should exist!")
        return False
    else:
        print(f"✅ Found {len(entries)} Budget Control Entries:")
        for entry in entries:
            status = "Submitted" if entry.docstatus == 1 else "Draft" if entry.docstatus == 0 else "Cancelled"
            print(f"\n  📌 {entry.name}")
            print(f"     Type: {entry.entry_type}")
            print(f"     Direction: {entry.direction}")
            print(f"     Amount: {entry.amount}")
            print(f"     Cost Center: {entry.cost_center}")
            print(f"     Account: {entry.account}")
            print(f"     Status: {status}")
        return True


def check_workflow_conditions(er):
    """Check if ER meets conditions for budget reservation"""
    print("\n" + "="*60)
    print("CHECKING WORKFLOW CONDITIONS")
    print("="*60)
    
    from imogi_finance.budget_control import utils
    
    settings = utils.get_settings()
    target_state = settings.get("lock_on_workflow_state") or "Approved"
    
    print(f"\n📋 Condition Check:")
    print(f"  1. enable_budget_lock: {settings.get('enable_budget_lock')} {'✅' if settings.get('enable_budget_lock') else '❌'}")
    print(f"  2. target_state setting: {target_state}")
    print(f"  3. ER workflow_state: {er.workflow_state} {'✅' if er.workflow_state == target_state else '❌'}")
    print(f"  4. ER status: {er.status} {'✅' if er.status == target_state else '❌'}")
    
    # Check if any condition matches
    if er.workflow_state == target_state or er.status == target_state:
        print(f"\n✅ ER meets conditions for budget reservation")
        return True
    else:
        print(f"\n❌ ER does NOT meet conditions for budget reservation")
        print(f"   Expected state: '{target_state}'")
        print(f"   Actual workflow_state: '{er.workflow_state}'")
        print(f"   Actual status: '{er.status}'")
        return False


def test_budget_function(er_name):
    """Test calling the budget function manually"""
    print("\n" + "="*60)
    print("TEST: Manual Budget Reservation Call")
    print("="*60)
    
    try:
        from imogi_finance.budget_control.workflow import reserve_budget_for_request
        
        er = frappe.get_doc("Expense Request", er_name)
        
        print(f"\n🧪 Attempting to call reserve_budget_for_request()...")
        print(f"   This is a DRY RUN - no actual changes will be made")
        
        # Check if would run
        from imogi_finance.budget_control import utils
        settings = utils.get_settings()
        
        if not settings.get("enable_budget_lock"):
            print(f"❌ BLOCKED: enable_budget_lock is disabled")
            return False
            
        target_state = settings.get("lock_on_workflow_state") or "Approved"
        if er.workflow_state != target_state and er.status != target_state:
            print(f"❌ BLOCKED: ER state ({er.workflow_state}/{er.status}) doesn't match target ({target_state})")
            return False
            
        print(f"✅ All conditions met - function would execute")
        return True
        
    except Exception as e:
        print(f"❌ ERROR during test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main(er_name=None):
    """Main troubleshooting function"""
    print("\n" + "="*80)
    print("BUDGET CONTROL TROUBLESHOOTING TOOL")
    print("="*80)
    
    # Step 1: Check settings
    settings_ok = check_settings()
    
    # Step 2: Check ER
    er = check_expense_request(er_name)
    if not er:
        return
    
    # Step 3: Check budget entries
    has_entries = check_budget_entries(er.name)
    
    # Step 4: Check conditions
    conditions_ok = check_workflow_conditions(er)
    
    # Step 5: Test function
    if not has_entries:
        test_ok = test_budget_function(er.name)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    if has_entries:
        print("✅ Budget Control Entries exist - system is working correctly")
    else:
        print("❌ Budget Control Entries NOT found - system has issues")
        print("\nPossible causes:")
        if not settings_ok:
            print("  1. Budget Control Settings: enable_budget_lock is DISABLED")
            print("     → Enable it in Budget Control Settings")
        if not conditions_ok:
            print("  2. Workflow State mismatch")
            print("     → Check that lock_on_workflow_state matches ER workflow_state")
        
        print("\n📖 See BUDGET_CONTROL_TROUBLESHOOTING.md for detailed solutions")
    
    print("\n" + "="*80)


# Can be called from bench console
if __name__ == "__main__":
    main()


# Expose as whitelisted method
@frappe.whitelist()
def run_diagnostics(er_name=None):
    """Run diagnostics from UI"""
    main(er_name)
