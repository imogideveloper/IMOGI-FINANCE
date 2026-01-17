# Native ERPNext Connections - Implementation Guide

## Overview
Native ERPNext connections menggunakan property `links` di DocType JSON untuk otomatis menampilkan linked documents di tab "Connections" dengan styling native ERPNext - tanpa perlu Python atau JavaScript code manual.

## ✅ DocTypes Updated

### 1. Customer Receipt
```json
"links": [
  {
    "group": "Payment",
    "link_doctype": "Payment Entry",
    "link_fieldname": "customer_receipt"
  },
  {
    "group": "Reference",
    "link_doctype": "Sales Order",
    "link_fieldname": "items.sales_order"
  },
  {
    "group": "Reference",
    "link_doctype": "Sales Invoice",
    "link_fieldname": "items.sales_invoice"
  }
]
```

### 2. Expense Request
```json
"links": [
  {
    "group": "Invoice",
    "link_doctype": "Purchase Invoice",
    "link_fieldname": "imogi_expense_request"
  },
  {
    "group": "Payment",
    "link_doctype": "Payment Entry",
    "link_fieldname": "imogi_expense_request"
  },
  {
    "group": "Allocation",
    "link_doctype": "Internal Charge Request",
    "link_fieldname": "expense_request"
  },
  {
    "group": "Budget",
    "link_doctype": "Budget Control Ledger Entry",
    "link_fieldname": "source_document"
  }
]
```

### 3. Branch Expense Request
```json
"links": [
  {
    "group": "Invoice",
    "link_doctype": "Purchase Invoice",
    "link_fieldname": "branch_expense_request"
  },
  {
    "group": "Payment",
    "link_doctype": "Payment Entry",
    "link_fieldname": "branch_expense_request"
  }
]
```

### 4. Internal Charge Request
```json
"links": [
  {
    "group": "Reference",
    "link_doctype": "Expense Request",
    "link_fieldname": "internal_charge_request"
  },
  {
    "group": "Budget",
    "link_doctype": "Budget Control Ledger Entry",
    "link_fieldname": "source_document"
  }
]
```

## 🎯 Benefits

### Before (Manual Connection Management)
```python
# In Python
def update_connections(self):
    # Manual collect linked docs
    pis = []
    for doc in frappe.get_all("Purchase Invoice", 
                              filters={"imogi_expense_request": self.name}):
        pis.append(doc.name)
    self.linked_purchase_invoices = ", ".join(pis)
    self.save()
```

```javascript
// In JavaScript
frm.add_custom_button('View Linked PI', function() {
    frappe.set_route('List', 'Purchase Invoice', {
        'imogi_expense_request': frm.doc.name
    });
});
```

❌ **Problems:**
- Manual code maintenance
- Need to update on every change
- Performance overhead
- Not real-time
- Ugly UI (just text)

### After (Native Connections)
```json
{
  "links": [{
    "group": "Invoice",
    "link_doctype": "Purchase Invoice",
    "link_fieldname": "imogi_expense_request"
  }]
}
```

✅ **Benefits:**
- Zero Python code
- Zero JavaScript code
- Auto-detection by ERPNext
- Real-time updates
- Native UI styling
- Grouped by category
- Clickable links
- Two-way linking
- Document count
- Better performance

## 🔍 How It Works

### Link Format

#### Parent Field Link
```json
{
  "link_doctype": "Payment Entry",
  "link_fieldname": "customer_receipt"
}
```
Query: `SELECT name FROM tabPayment Entry WHERE customer_receipt = 'KR-2026-00001'`

#### Child Table Field Link
```json
{
  "link_doctype": "Sales Invoice",
  "link_fieldname": "items.sales_invoice"
}
```
Query: `SELECT DISTINCT sales_invoice FROM tabCustomer Receipt Item WHERE parent = 'KR-2026-00001' AND sales_invoice IS NOT NULL`

### Grouping
```json
{
  "group": "Payment",  // Category name in Connections tab
  "link_doctype": "Payment Entry",
  "link_fieldname": "customer_receipt"
}
```

## 📊 Connection Display

When you open a Customer Receipt, the Connections tab shows:

```
┌─ Connections ────────────────────────────────┐
│                                               │
│ Payment (2)                                   │
│   Payment Entry                               │
│   • ACC-PAY-2026-00001                       │
│   • ACC-PAY-2026-00002                       │
│                                               │
│ Reference (3)                                 │
│   Sales Invoice                               │
│   • ACC-SINV-2026-00001                      │
│   • ACC-SINV-2026-00002                      │
│                                               │
│   Sales Order                                 │
│   • SAL-ORD-2026-00001                       │
│                                               │
└───────────────────────────────────────────────┘
```

## 🚀 Installation

1. **Reload DocTypes:**
```bash
bench --site [site] reload-doc imogi_finance "DocType" "Customer Receipt"
bench --site [site] reload-doc imogi_finance "DocType" "Expense Request"
bench --site [site] reload-doc imogi_finance "DocType" "Branch Expense Request"
bench --site [site] reload-doc imogi_finance "DocType" "Internal Charge Request"
```

2. **Clear Cache:**
```bash
bench --site [site] clear-cache
bench restart
```

3. **Verify:**
- Open any Expense Request
- Look for "Connections" tab
- Should show linked Purchase Invoices, Payment Entries, etc.

## 📝 Code Cleanup - COMPLETED ✅

Now that native connections are implemented, manual connection management code has been cleaned up:

### ✅ Changes Completed (January 17, 2026)

#### 1. Removed Custom Buttons (internal_charge_request.js)
```javascript
// ✅ REMOVED - Replaced by native connections
function addExpenseRequestButton(frm) {
  frm.add_custom_button(__('View Expense Request'), ...);  // DELETED
  frm.add_custom_button(__('View Budget Entries'), ...);   // DELETED
}
```

#### 2. Removed Dashboard Indicators (internal_charge_request.js)
```javascript
// ✅ REMOVED - Redundant with connections tab
function addStatusIndicators(frm) {
  frm.dashboard.add_indicator(...);  // DELETED
}
```

#### 3. Hidden Display Fields (expense_request.json)
- `links_section` - Hidden from form (kept in DB for business logic)
- `linked_purchase_invoice` - Hidden from form (kept in DB for business logic)
- `linked_payment_entry` - Hidden from form (kept in DB for business logic)
- `pending_purchase_invoice` - Hidden from form (kept in DB for business logic)
- `column_break_links` - Hidden from form

**Note**: Fields remain in database and are still used by business logic in `accounting.py` and `events/utils.py`

### ⚠️ What Was NOT Removed (Still Required)

#### Python Business Logic - KEEP
```python
# imogi_finance/accounting.py
def _update_request_purchase_invoice_links(...)  # ✅ KEEP - Business logic

# imogi_finance/events/utils.py  
def get_expense_request_status(...)              # ✅ KEEP - Status determination
def get_expense_request_links(...)               # ✅ KEEP - Link retrieval
```

These functions manage workflow state, not UI display, so they remain necessary.

---

## 🔄 Flow Refactoring - Query-Based Status (January 17, 2026)

### Major Change: From Manual Fields to Database Queries

Previous implementation used manual field updates (`linked_purchase_invoice`, `linked_payment_entry`) which were redundant with native connections. Now the system queries directly from submitted documents for cleaner, real-time status.

### 🔒 Business Rules

#### 1. **1 Expense Request = 1 Purchase Invoice (Max)**
- Each ER can only have **ONE** submitted Purchase Invoice at a time
- Cancelled PI are ignored - you can create new PI if old one is cancelled
- Validation enforced at PI submit time
- Prevents duplicate PI for same expense

#### 2. **1 Purchase Invoice = Multiple Payment Entries (Allowed)**
- Each PI can have **MULTIPLE** submitted Payment Entries
- Useful for installment payments or split payments
- No limit on number of PEs per PI
- All PEs are tracked via native connections

#### 3. **Status Priority**
- **"Paid"** = Has ANY submitted Payment Entry (even 1 out of many)
- **"PI Created"** = Has submitted PI but no PE yet
- **"Approved"** = No submitted PI

### ✅ New Flow Implementation

#### 1. **Status Determination - Query-Based**

**Before (Manual Field Update):**
```python
# When PI submitted
frappe.db.set_value("Expense Request", er.name, {
    "linked_purchase_invoice": pi.name,
    "status": "PI Created"
})

# Status read from field
status = er.status  # "PI Created"
```

**After (Database Query):**
```python
# When PI submitted - only update workflow_state
frappe.db.set_value("Expense Request", er.name, {
    "workflow_state": "PI Created"
})

# Status determined by querying submitted documents
def get_expense_request_links(request_name):
    """Query submitted PI and PE from database."""
    linked_pi = frappe.db.get_value(
        "Purchase Invoice",
        {"imogi_expense_request": request_name, "docstatus": 1},
        "name"
    )
    
    linked_pe = frappe.db.get_value(
        "Payment Entry",
        {"imogi_expense_request": request_name, "docstatus": 1},
        "name"
    )
    
    return {
        "linked_purchase_invoice": linked_pi,
        "linked_payment_entry": linked_pe
    }

def get_expense_request_status(request_links):
    """Determine status from queried links."""
    if request_links.get("linked_payment_entry"):
        return "Paid"
    if request_links.get("linked_purchase_invoice"):
        return "PI Created"
    return "Approved"
```

#### 2. **Purchase Invoice Submit Flow**

```python
def _validate_one_pi_per_request(doc):
    """Validate 1 ER = 1 submitted PI only."""
    expense_request = doc.get("imogi_expense_request")
    
    if expense_request:
        # Check for existing submitted PI (cancelled are ignored)
        existing_pi = frappe.db.get_value(
            "Purchase Invoice",
            {
                "imogi_expense_request": expense_request,
                "docstatus": 1,  # Only submitted
                "name": ["!=", doc.name]
            },
            "name"
        )
        
        if existing_pi:
            frappe.throw(
                f"ER already linked to PI {existing_pi}. Cancel that PI first."
            )

def _handle_expense_request_submit(doc, request_name):
    """PI submit - validated and simplified."""
    
    # Validation already done in _validate_one_pi_per_request
    # called from validate_before_submit hook
    
    # ✅ Only update workflow_state
    frappe.db.set_value("Expense Request", request_name, {
        "workflow_state": "PI Created"
    })
    
    # Status "PI Created" is auto-determined by query:
    # - get_expense_request_links() finds this submitted PI
    # - get_expense_request_status() returns "PI Created"
```

**Validation Points:**
- ❌ Block if another submitted PI exists for same ER
- ✅ Allow if old PI is cancelled (docstatus=2)
- ✅ Allow if old PI is draft (docstatus=0)

#### 3. **Payment Entry Submit Flow**

```python
def _handle_expense_request_submit(doc, expense_request):
    """PE submit - multiple PE allowed per PI."""
    
    # ✅ No validation against other PEs
    # Multiple PE per ER is ALLOWED (1 PI can have multiple payments)
    
    # Validate PI exists (query from DB)
    has_pi = frappe.db.get_value(
        "Purchase Invoice",
        {"imogi_expense_request": expense_request, "docstatus": 1},
        "name"
    )
    
    if not has_pi:
        frappe.throw("Must have submitted PI before PE")
    
    # ✅ Only update workflow_state
    frappe.db.set_value("Expense Request", expense_request, {
        "workflow_state": "Paid"
    })
    
    # Status "Paid" is auto-determined by query:
    # - get_expense_request_links() finds ANY submitted PE
    # - get_expense_request_status() returns "Paid"
```

**Validation Points:**
- ✅ Allow multiple submitted PE for same ER/PI
- ❌ Block if no submitted PI exists
- ✅ Each PE creates its own Payment Entry document
- ✅ All PEs visible in Connections tab

#### 4. **Cancel/Trash Flow**

```python
def on_cancel(doc, method=None):
    """PI/PE cancel - workflow state updates, status auto via query."""
    
    expense_request = doc.get("imogi_expense_request")
    
    if expense_request:
        # Query current links
        request_links = get_expense_request_links(expense_request)
        next_status = get_expense_request_status(request_links)
        
        # ✅ Only update workflow_state
        # ❌ No longer clear linked_* fields
        frappe.db.set_value("Expense Request", expense_request, {
            "workflow_state": next_status
        })
        
    # Status automatically reflects cancelled state:
    # - If PI cancelled: query finds no submitted PI → status "Approved"
    # - If PE cancelled: query finds no submitted PE → status "PI Created"
```

### 🎯 Benefits of Query-Based Approach

| Aspect | Manual Fields | Query-Based |
|--------|--------------|-------------|
| **Data Source** | Field updates on ER | Direct query from PI/PE |
| **Real-time** | Need manual sync | Always current |
| **Cancelled Docs** | Manual cleanup needed | Auto-excluded (docstatus filter) |
| **Duplicate Detection** | Field-based check | Database query |
| **Multiple PE Support** | Not supported | ✅ Fully supported |
| **Status Accuracy** | Can be stale | Always accurate |
| **Code Complexity** | High (many updates) | Low (minimal updates) |
| **Maintainability** | Prone to bugs | Reliable |
| **Native Connections** | Redundant | Aligned |
| **Business Rules** | Manual enforcement | Database-driven |

### 🔐 Validation Summary

| Document | Rule | Validation Point | Action if Violated |
|----------|------|------------------|-------------------|
| **Purchase Invoice** | 1 ER = 1 PI (max) | Before submit | ❌ Block: "ER already linked to PI-XXX" |
| **Purchase Invoice** | Must cancel all PE first | Before cancel | ❌ Block: "Cancel PE-XXX and PE-YYY first" |
| **Payment Entry** | 1 PI = Multiple PE | Before submit | ✅ Allow multiple PE |
| **Payment Entry** | Must have PI first | Before submit | ❌ Block: "Must have submitted PI" |
| **Payment Entry** | Not in printed report | Before cancel | ❌ Block: "Use reversal instead" |

### 📈 Use Cases Supported

#### ✅ **Installment Payments**
```
ER-001 → PI-001 (Rp 10M)
  ├─ PE-001: Rp 3M (Down Payment)
  ├─ PE-002: Rp 3M (Installment 1)
  ├─ PE-003: Rp 2M (Installment 2)
  └─ PE-004: Rp 2M (Final Payment)
```

#### ✅ **Split Payments to Different Accounts**
```
ER-001 → PI-001 (Rp 5M)
  ├─ PE-001: Rp 3M from Cash Account A
  └─ PE-002: Rp 2M from Bank Account B
```

#### ✅ **Re-create PI After Cancellation**
```
ER-001 → PI-001 (submitted) ❌ Cancel
       → PI-002 (new, can submit) ✅
```

#### ❌ **Multiple PI per ER (Blocked)**
```
ER-001 → PI-001 (submitted)
       → PI-002 (tries to submit) ❌ "ER already linked to PI-001"
```

#### ✅ **Partial Payment Cancellation**
```
ER-001 → PI-001 (Rp 10M)
  ├─ PE-001: Rp 5M (submitted)
  ├─ PE-002: Rp 3M (submitted)
  └─ PE-003: Rp 2M (submitted)

Cancel PE-001 ✅
  → ER status still "Paid" (PE-002, PE-003 active)

Cancel PE-002 ✅
  → ER status still "Paid" (PE-003 active)

Cancel PE-003 ✅
  → ER status back to "PI Created" (no PE active)
```

#### ✅ **Payment Reversal (for Printed Reports)**
```
ER-001 → PI-001 (Rp 8M)
  ├─ PE-001: Rp 5M (submitted, printed in daily report)
  └─ PE-002: Rp 3M (submitted)

Reverse PE-001 ✅
  → Creates PE-REV-001 (reversal entry)
  → PE-001 marked as reversed
  → ER status still "Paid" (PE-002 active)

Reverse PE-002 ✅
  → Creates PE-REV-002
  → ER status back to "PI Created" (no active PE)
```

### 📊 Flow Comparison

#### **Scenario 1: Create PI from ER**

**Flow:**
1. User creates PI from ER (draft)
2. User submits PI
3. Validation checks: No other submitted PI for this ER?
   - ✅ Pass → PI submitted
   - ❌ Fail → Error: "ER already linked to PI-001"
4. Hook updates: `workflow_state = "PI Created"`
5. Status auto-determined: "PI Created"

**Cancel & Retry:**
1. User cancels PI-001
2. User creates new PI-002 from same ER
3. Validation checks: No other submitted PI?
   - ✅ Pass (PI-001 is cancelled, docstatus=2)
4. PI-002 submitted successfully

#### **Scenario 2: Create Multiple PE from PI**

**Flow:**
1. PI submitted, ER status = "PI Created"
2. User creates PE-001 (partial payment Rp 5M)
3. PE-001 submitted → ER status = "Paid"
4. User creates PE-002 (final payment Rp 3M)
5. PE-002 submitted → ER status still "Paid"
6. Connections tab shows:
   - Purchase Invoice (1): PI-001
   - Payment Entry (2): PE-001, PE-002

**Benefits:**
- ✅ Installment payments supported
- ✅ Split payments to different accounts
- ✅ Each payment tracked separately
- ✅ All visible in native connections

#### **Scenario 3: Cancel PE (with Multiple PEs)**

**Before:**
- PI-001 submitted
- PE-001 submitted (Rp 5M)
- PE-002 submitted (Rp 3M)
- ER status = "Paid"

**User cancels PE-001:**
1. PE-001 cancelled (docstatus=2)
2. Hook checks: Any other submitted PE?
   - Yes: PE-002 still submitted (docstatus=1)
3. ✅ **Status remains: "Paid"**
4. Connections tab shows:
   - Purchase Invoice (1): PI-001
   - Payment Entry (1): PE-002 ❌ PE-001 hidden (cancelled)

**User cancels PE-002:**
1. PE-002 cancelled (docstatus=2)
2. Hook checks: Any other submitted PE?
   - No: All PEs cancelled
3. ✅ **Status updated: "PI Created"**
4. Connections tab shows:
   - Purchase Invoice (1): PI-001
   - Payment Entry (0): ❌ All cancelled

**Summary:**
- ✅ Status tetap "Paid" selama masih ada minimal 1 PE submitted
- ✅ Status kembali "PI Created" hanya jika SEMUA PE cancelled
- ✅ Query `docstatus=1` otomatis exclude cancelled PE

#### **Scenario 4: Reverse PE (for Printed Reports)**

**When to use Reversal:**
- PE already included in printed Cash/Bank Daily Report
- Cannot cancel directly (accounting lock)
- Must create reversal entry instead

**Flow:**
1. PE-001 submitted and printed in daily report
2. User tries to cancel PE-001
3. ❌ Blocked: "PE linked to printed report, use reversal instead"
4. User clicks "Reverse Payment Entry"
5. System creates PE-REV-001:
   - Reverses all amounts (debit ↔ credit)
   - Posts at today's date (not original date)
   - Links back to PE-001 in remarks
6. PE-001 marked as `is_reversed=1`
7. Hook checks: Any other active PE? (excluding reversed)
   - If yes → Status remains "Paid"
   - If no → Status back to "PI Created"

**With Multiple PEs:**
```
Before:
- PE-001 (Rp 5M) - submitted, printed
- PE-002 (Rp 3M) - submitted

User reverses PE-001:
- PE-REV-001 created (reversal of PE-001)
- PE-001 marked is_reversed=1
- Check: PE-002 still active?
  → Yes: PE-002 (Rp 3M) still submitted
- ✅ Status remains "Paid"

User reverses PE-002:
- PE-REV-002 created (reversal of PE-002)
- PE-002 marked is_reversed=1
- Check: Any other PE active?
  → No: All PEs reversed
- ✅ Status back to "PI Created"
```

#### **Scenario 5: Cancel PI (with Multiple PEs)**

**Before:**
- PI-001 submitted
- PE-001 submitted
- PE-002 submitted

**User tries to cancel PI-001:**
1. Validation checks: Any submitted PE linked?
   - PE-001 exists (submitted)
2. ❌ **Block cancellation**
3. Error: "Cannot cancel PI. Cancel PE-001 and PE-002 first."

**Correct Flow:**
1. Cancel PE-002 first
2. Cancel PE-001
3. Now PI-001 can be cancelled
4. ER status back to: "Approved"

### 🔄 Cancel vs Reversal

| Aspect | Cancel PE | Reverse PE |
|--------|-----------|------------|
| **When to Use** | PE not in printed report | PE already printed in daily report |
| **Action** | Cancel document (docstatus=2) | Create new reversal PE |
| **Original PE** | Cancelled | Remains submitted, marked `is_reversed=1` |
| **Posting Date** | - | Today (or specified date) |
| **Accounting** | Entries deleted | New entries created (reversed) |
| **Audit Trail** | Less clear | Clear (shows reversal) |
| **Daily Report** | Must not be printed | Can be printed |

### 📋 Status Update Logic

```python
def determine_status_on_pe_cancel(expense_request_name, cancelled_pe_name):
    """Determine ER status when a PE is cancelled."""
    
    # Query untuk PE lain yang masih submitted
    other_active_pes = frappe.db.get_all(
        "Payment Entry",
        filters={
            "imogi_expense_request": expense_request_name,
            "docstatus": 1,  # Only submitted
            "name": ["!=", cancelled_pe_name]  # Exclude the one being cancelled
        },
        pluck="name"
    )
    
    if other_active_pes:
        # Masih ada PE lain yang submitted
        return "Paid"  # Status tetap Paid
    else:
        # Tidak ada PE lain, cek PI
        has_pi = frappe.db.exists(
            "Purchase Invoice",
            {
                "imogi_expense_request": expense_request_name,
                "docstatus": 1
            }
        )
        return "PI Created" if has_pi else "Approved"
```

### 🔧 Migration Notes

**No Migration Required!**
- Old `linked_*` fields remain in database (hidden from UI)
- New queries ignore old values, read directly from PI/PE
- Backward compatible with existing data
- Status recalculated on-the-fly from actual documents

**To Test:**
1. Open existing Expense Request
2. Check "Connections" tab → shows linked PI/PE
3. Check status field → auto-determined from query
4. Submit/cancel PI or PE → status updates automatically

### ⚠️ Important Notes

1. **workflow_state vs status:**
   - `workflow_state` = Manually updated on submit/cancel
   - `status` = Auto-calculated via `get_expense_request_status()`
   - Both should match, but status is source of truth

2. **Display fields kept:**
   - `linked_purchase_invoice` and `linked_payment_entry` still exist in database
   - Hidden from form UI
   - May be used by other legacy code
   - Will be fully deprecated in future release

3. **Query performance:**
   - Indexed on `imogi_expense_request` field
   - Filter by `docstatus=1` is efficient
   - Single query per status check

4. **Cancelled documents:**
   - Automatically excluded by `docstatus=1` filter
   - No manual cleanup needed
   - Audit trail preserved

5. **Multiple PE handling:**
   - Status "Paid" = Has ANY submitted PE (at least 1)
   - Cancel 1 PE while others exist → Status remains "Paid"
   - Cancel ALL PEs → Status back to "PI Created"
   - Query automatically excludes cancelled PEs (docstatus=2)

6. **Reversed PE handling:**
   - Reversed PE marked with `is_reversed=1`
   - Original PE remains submitted (docstatus=1)
   - Reversal creates new PE with flipped accounts
   - Query excludes reversed PEs from status check
   - Status updates same as cancel (check remaining active PEs)

7. **Cancel sequence:**
   - Must cancel ALL PEs before cancelling PI
   - Validation blocks PI cancel if any PE still submitted
   - Prevents orphaned payment entries

## 🎨 Best Practices

### 1. Choose Meaningful Group Names
```json
{
  "group": "Payment",     // ✅ Clear category
  "group": "Invoice",     // ✅ Clear category
  "group": "Documents"    // ❌ Too generic
}
```

### 2. Use Consistent Grouping
```json
// All payments in one group
{"group": "Payment", "link_doctype": "Payment Entry", ...}
{"group": "Payment", "link_doctype": "Journal Entry", ...}

// All references in one group
{"group": "Reference", "link_doctype": "Sales Order", ...}
{"group": "Reference", "link_doctype": "Sales Invoice", ...}
```

### 3. Document Count Auto-Shows
ERPNext automatically shows count in parentheses:
- Payment Entry (3)
- Sales Invoice (2)

### 4. Two-Way Linking is Automatic
If Customer Receipt links to Payment Entry, then Payment Entry automatically shows link back to Customer Receipt.

## 🔗 Applying to Other DocTypes

For any custom DocType, add `links` property:

```json
{
  "doctype": "DocType",
  "name": "Your Custom DocType",
  ...
  "links": [
    {
      "group": "Category Name",
      "link_doctype": "Linked DocType",
      "link_fieldname": "field_name_in_linked_doctype"
    }
  ]
}
```

## ⚠️ Important Notes

1. **Field Must Exist**: `link_fieldname` must be an actual field in the linked DocType
2. **Case Sensitive**: Field names are case-sensitive
3. **Child Tables**: Use dot notation: `items.sales_invoice`
4. **Link/Data Fields**: Usually Link fields, but can be Data if storing document names
5. **Filtering**: ERPNext filters by current document's name automatically

## 🧪 Testing

### Test Connection Display
1. Create Expense Request: ER-2026-00001
2. Create Purchase Invoice linked to it
3. Open Expense Request
4. Check Connections tab
5. Should show Purchase Invoice under "Invoice" group

### Test Two-Way Linking
1. Open Purchase Invoice
2. Check Connections tab
3. Should show Expense Request automatically

### Test Child Table Links
1. Create Customer Receipt with multiple Sales Invoices
2. Open Customer Receipt
3. Check Connections tab
4. Should show all unique Sales Invoices from items table

## 📚 Summary

| Aspect | Manual Code | Native Connections |
|--------|-------------|-------------------|
| Python Code | Required | None |
| JavaScript Code | Required | None |
| UI Styling | Custom | Native ERPNext |
| Performance | Slower | Optimized |
| Real-time | No | Yes |
| Two-way Link | Manual | Automatic |
| Grouping | Manual | Built-in |
| Maintenance | High | Zero |

**Recommendation**: Always use native connections instead of manual connection management for cleaner, maintainable code!

---

## ✅ Cleanup Status

**Completed**: January 17, 2026

- ✅ Removed redundant custom buttons from Internal Charge Request
- ✅ Removed redundant dashboard indicators
- ✅ Hidden display-only link fields from Expense Request form
- ✅ Verified business logic fields remain intact
- ✅ Documentation updated

**Files Modified**:
1. [internal_charge_request.js](../imogi_finance/imogi_finance/doctype/internal_charge_request/internal_charge_request.js) - Removed 2 functions
2. [expense_request.json](../imogi_finance/imogi_finance/doctype/expense_request/expense_request.json) - Hidden 5 display fields

**Next Steps**:
1. Reload doctypes: `bench --site [site] reload-doc imogi_finance "DocType" "Expense Request"`
2. Clear cache: `bench --site [site] clear-cache`
3. Test connections tab displays correctly
4. Verify business logic (PI creation, status updates) still works
