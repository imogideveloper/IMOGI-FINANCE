"""
Test script to verify Purchase Invoice tax calculation from Expense Request.

This script tests whether PPN and PPh are properly calculated when creating
a Purchase Invoice from an Expense Request.

Run with: bench --site [your-site] execute imogi_finance.test_pi_tax_calculation.test_pi_creation
"""

import frappe
from frappe.utils import flt


def test_pi_creation():
    """Test Purchase Invoice creation with tax calculation."""
    
    # Find a recent Expense Request with PPN and PPh
    er_list = frappe.get_all(
        "Expense Request",
        filters={
            "docstatus": 1,
            "workflow_state": "Approved",
            "is_ppn_applicable": 1,
            "is_pph_applicable": 1,
        },
        fields=["name", "amount", "is_ppn_applicable", "is_pph_applicable", 
                "ppn_template", "pph_type", "pph_base_amount", "ti_fp_ppn"],
        order_by="modified desc",
        limit=1
    )
    
    if not er_list:
        print("❌ No approved Expense Request with PPN and PPh found")
        return
    
    er_name = er_list[0].name
    er = frappe.get_doc("Expense Request", er_name)
    
    print(f"\n{'='*80}")
    print(f"Testing Purchase Invoice Creation from Expense Request: {er_name}")
    print(f"{'='*80}")
    
    print(f"\n📋 Expense Request Details:")
    print(f"   Amount: {flt(er.amount):,.2f}")
    print(f"   PPN Applicable: {bool(er.is_ppn_applicable)}")
    print(f"   PPN Amount (OCR): {flt(er.ti_fp_ppn):,.2f}")
    print(f"   PPN Template: {er.ppn_template or 'Not set'}")
    print(f"   PPh Applicable: {bool(er.is_pph_applicable)}")
    print(f"   PPh Type: {er.pph_type or 'Not set'}")
    print(f"   PPh Base Amount: {flt(er.pph_base_amount):,.2f}")
    print(f"   DPP Variance: {flt(er.ti_dpp_variance or 0):,.2f}")
    print(f"   PPN Variance: {flt(er.ti_ppn_variance or 0):,.2f}")
    
    # Check if PI already exists
    existing_pi = frappe.db.get_value(
        "Purchase Invoice",
        {"imogi_expense_request": er_name, "docstatus": ["!=", 2]},
        "name"
    )
    
    if existing_pi:
        print(f"\n⚠️  Purchase Invoice already exists: {existing_pi}")
        pi = frappe.get_doc("Purchase Invoice", existing_pi)
    else:
        print(f"\n🔨 Creating new Purchase Invoice...")
        from imogi_finance.accounting import create_purchase_invoice_from_request
        
        try:
            pi_name = create_purchase_invoice_from_request(er_name)
            pi = frappe.get_doc("Purchase Invoice", pi_name)
            print(f"✅ Purchase Invoice created: {pi_name}")
        except Exception as e:
            print(f"❌ Error creating Purchase Invoice: {str(e)}")
            import traceback
            traceback.print_exc()
            return
    
    print(f"\nNumber of items: {len(pi.items or [])}")
    
    # Check for variance line item
    variance_items = [item for item in (pi.items or []) 
                      if "variance" in (item.item_name or "").lower()]
    if variance_items:
        print(f"\n   📊 Variance Line Items Found:")
        for item in variance_items:
            print(f"      - {item.item_name}: {flt(item.amount):,.2f}")
            print(f"        Account: {item.expense_account}")
    else:
        print(f"\n   ⚠️  No variance line items found")
    
    print(f"\n   💰 Purchase Invoice Tax Details:")
    print(f"   Total (items): {flt(pi.total):,.2f}")
    print(f"   Apply TDS: {bool(pi.apply_tds)}")
    print(f"   Tax Withholding Category: {pi.tax_withholding_category or 'Not set'}")
    print(f"   Withholding Tax Base Amount: {flt(pi.withholding_tax_base_amount):,.2f}")
    
    # Check PPN (in taxes table)
    ppn_total = 0
    if pi.taxes:
        print(f"\n   📊 Taxes Table:")
        for tax in pi.taxes:
            print(f"      - {tax.description}: {flt(tax.tax_amount):,.2f}")
            if "PPN" in (tax.description or ""):
                ppn_total += flt(tax.tax_amount)
    else:
        print(f"\n   ⚠️  No taxes found in taxes table")
    
    # Check PPh (withholding tax)
    pph_total = 0
    if hasattr(pi, "taxes"):
        for tax in pi.taxes:
            # Withholding tax typically has negative amount
            if variance was handled
    dpp_variance = flt(er.ti_dpp_variance or 0)
    if dpp_variance != 0:
        variance_items = [item for item in (pi.items or []) 
                          if "variance" in (item.item_name or "").lower()]
        if variance_items:
            print(f"✅ DPP variance {dpp_variance:,.2f} added as line item")
            # Verify amount matches
            variance_total = sum(flt(item.amount) for item in variance_items)
            if abs(variance_total - dpp_variance) < 1:  # Allow 1 IDR tolerance for rounding
                print(f"✅ Variance amount matches: {variance_total:,.2f}")
            else:
                issues.append(f"❌ Variance amount mismatch: Expected {dpp_variance:,.2f}, got {variance_total:,.2f}")
        else:
            issues.append(f"❌ DPP variance {dpp_variance:,.2f} exists but not added as line item")
    
    # Check if flt(tax.tax_amount) < 0:
                pph_total += abs(flt(tax.tax_amount))
                print(f"      - Withholding: {tax.description}: {flt(tax.tax_amount):,.2f}")
    
    print(f"\n   Total PPN: {ppn_total:,.2f}")
    print(f"   Total PPh (withholding): {pph_total:,.2f}")
    print(f"   Grand Total: {flt(pi.grand_total):,.2f}")
    
    # Validation
    print(f"\n{'='*80}")
    print(f"Validation Results:")
    print(f"{'='*80}")
    
    issues = []
    
    # Check if PPN is calculated
    if er.is_ppn_applicable and ppn_total == 0:
        issues.append("❌ PPN is not calculated (should be > 0)")
    elif er.is_ppn_applicable:
        print(f"✅ PPN is calculated: {ppn_total:,.2f}")
    
    # Check if PPh is calculated
    if er.is_pph_applicable and pph_total == 0:
        issues.append("❌ PPh is not calculated (should be > 0)")
    elif er.is_pph_applicable:
        print(f"✅ PPh is calculated: {pph_total:,.2f}")
    
    # Check apply_tds flag
    if er.is_pph_applicable and not pi.apply_tds:
        issues.append("❌ apply_tds is not set (should be 1)")
    elif er.is_pph_applicable:
        print(f"✅ apply_tds is set")
    
    # Check tax_withholding_category
    if er.is_pph_applicable and not pi.tax_withholding_category:
        issues.append("❌ tax_withholding_category is not set")
    elif er.is_pph_applicable:
        print(f"✅ tax_withholding_category is set: {pi.tax_withholding_category}")
    
    if issues:
        print(f"\n⚠️  Issues Found:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print(f"\n✅ All validations passed!")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    test_pi_creation()
