# 🐛 Bug Fix: Fiscal Year Not Found Error di Purchase Invoice

## Problem Statement
Error "fiscal tidak ditemukan" saat membuat Purchase Invoice yang terhubung dengan Expense Request yang menggunakan Budget Control.

## Root Cause

### Issue Location
**File:** `imogi_finance/budget_control/workflow.py` - Function `_build_allocation_slices()` (Line 217)

**Problem:**
```python
def _build_allocation_slices(expense_request, *, settings=None, ic_doc=None):
    # ...
    fiscal_year = utils.resolve_fiscal_year(getattr(expense_request, "fiscal_year", None))
    
    # ❌ NO VALIDATION - fiscal_year bisa None!
    # Langsung dipakai untuk create Budget Control Entry
    # Yang menyebabkan error di database (fiscal_year is required field)
```

### Error Flow
```
Purchase Invoice Submit
  → consume_budget_for_purchase_invoice()
    → _build_allocation_slices()
      → resolve_fiscal_year() returns None
      → No validation!
      → ledger.post_entry() tries to create BCE
        → fiscal_year is None
        → ❌ ERROR: "fiscal_year" is required
```

## Solution Applied

### Fix #1: Add Validation in `_build_allocation_slices()`
**File:** `imogi_finance/budget_control/workflow.py`

```python
def _build_allocation_slices(expense_request, *, settings=None, ic_doc=None):
    settings = settings or utils.get_settings()
    company = utils.resolve_company_from_cost_center(getattr(expense_request, "cost_center", None))
    fiscal_year = utils.resolve_fiscal_year(getattr(expense_request, "fiscal_year", None))
    
    # ✅ NEW: Validate fiscal year is found
    if not fiscal_year:
        frappe.throw(
            _("Fiscal Year could not be determined for Expense Request {0}. Please set a default Fiscal Year in System Settings or User Defaults.").format(
                getattr(expense_request, "name", "Unknown")
            ),
            title=_("Fiscal Year Required")
        )
    
    # Rest of the function...
```

**Benefits:**
- Clear error message untuk user
- Mencegah silent failure
- User tahu apa yang harus dilakukan (set fiscal year default)

### Fix #2: Improve `resolve_fiscal_year()` with Better Fallback
**File:** `imogi_finance/budget_control/utils.py`

```python
def resolve_fiscal_year(fiscal_year: str | None) -> str | None:
    if fiscal_year:
        return fiscal_year

    # Try user defaults
    defaults = getattr(frappe, "defaults", None)
    if defaults and hasattr(defaults, "get_user_default"):
        try:
            value = defaults.get_user_default("fiscal_year")
            if value:
                return value
        except Exception:
            pass

    # Try global defaults
    if defaults and hasattr(defaults, "get_global_default"):
        try:
            value = defaults.get_global_default("fiscal_year")
            if value:
                return value
        except Exception:
            pass

    # Try System Settings
    if getattr(frappe, "db", None):
        try:
            value = frappe.db.get_single_value("System Settings", "fiscal_year")
            if value:
                return value
        except Exception:
            pass

        try:
            value = frappe.db.get_single_value("System Settings", "current_fiscal_year")
            if value:
                return value
        except Exception:
            pass
        
        # ✅ NEW: Last resort - get fiscal year from current date
        try:
            get_fiscal_year = getattr(frappe.utils, "get_fiscal_year", None)
            if callable(get_fiscal_year):
                from frappe.utils import nowdate
                result = get_fiscal_year(nowdate(), as_dict=True)
                if result and result.get("name"):
                    return result.get("name")
        except Exception:
            pass

    return None
```

**Benefits:**
- Tambahan fallback: ambil fiscal year dari tanggal sekarang
- Menggunakan fungsi built-in ERPNext `get_fiscal_year()`
- Lebih robust, lebih jarang return None

## How to Fix (User Action)

Jika user mengalami error ini, ada 3 cara fix:

### Option 1: Set Global Default Fiscal Year (Recommended)
```
1. Buka System Settings
2. Set "Current Fiscal Year" field
3. Save
```

**SQL Alternative:**
```sql
UPDATE `tabSingles`
SET value = '2025-2026'  -- Ganti dengan fiscal year yang sesuai
WHERE doctype = 'System Settings'
AND field = 'fiscal_year';
```

### Option 2: Set User Default Fiscal Year
```
1. Buka User Profile (current user)
2. Klik "Set User Permissions"
3. Add: Fiscal Year = 2025-2026
```

**From Frappe console:**
```python
frappe.defaults.set_user_default("fiscal_year", "2025-2026")
```

### Option 3: Add fiscal_year Field to Expense Request (Long-term)
```python
# In Expense Request DocType, add:
{
    "fieldname": "fiscal_year",
    "fieldtype": "Link",
    "label": "Fiscal Year",
    "options": "Fiscal Year",
    "reqd": 1
}
```

## Testing

### Test Case 1: Normal Flow with Fiscal Year Set
```python
# Setup
frappe.db.set_single_value("System Settings", "fiscal_year", "2025-2026")

# Create ER and approve
er = frappe.get_doc("Expense Request", "ER-00001")
er.on_workflow_action("Approve", next_state="Approved")

# Create PI
pi = frappe.get_doc("Purchase Invoice", "PI-00001")
pi.imogi_expense_request = "ER-00001"
pi.submit()

# Expected: No error, Budget Control Entry created with fiscal_year = "2025-2026"
```

### Test Case 2: Error with Clear Message
```python
# Setup: NO fiscal year set
frappe.db.set_single_value("System Settings", "fiscal_year", None)
frappe.defaults.clear_default("fiscal_year")

# Try to create PI
pi = frappe.get_doc("Purchase Invoice", "PI-00002")
pi.imogi_expense_request = "ER-00002"

# Expected: Clear error message
# "Fiscal Year could not be determined for Expense Request ER-00002. 
#  Please set a default Fiscal Year in System Settings or User Defaults."
```

### Test Case 3: Fallback from Current Date
```python
# Setup: Create fiscal year document for current date range
fy = frappe.get_doc({
    "doctype": "Fiscal Year",
    "year": "2025-2026",
    "year_start_date": "2025-01-01",
    "year_end_date": "2025-12-31"
})
fy.insert()

# Clear all defaults
frappe.db.set_single_value("System Settings", "fiscal_year", None)

# Try resolve
from imogi_finance.budget_control import utils
result = utils.resolve_fiscal_year(None)

# Expected: result = "2025-2026" (from date-based lookup)
```

## Monitoring Query

Check Budget Control Entries without fiscal year (should be ZERO after fix):

```sql
SELECT 
    name,
    entry_type,
    ref_doctype,
    ref_name,
    fiscal_year,
    creation
FROM `tabBudget Control Entry`
WHERE fiscal_year IS NULL
   OR fiscal_year = ''
ORDER BY creation DESC
LIMIT 20;
```

## Related Files Changed

1. ✅ `imogi_finance/budget_control/workflow.py` (Line 217) - Added validation
2. ✅ `imogi_finance/budget_control/utils.py` (Line 106) - Improved fallback

## Priority
**HIGH** - Prevents Purchase Invoice submission when Budget Control is enabled

---

**Fixed By:** GitHub Copilot  
**Date:** 2026-01-16  
**Related to:** Budget Control Entry bug fixes
