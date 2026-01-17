# Customer Receipt - Workflow & Tracking Implementation

## Summary

Implementasi workflow, tracking logs, dan native ERPNext connections untuk Customer Receipt.

## Changes Made

### 1. Workflow Implementation

**Files Modified:**
- `workflow_state.json` - Added states: Issued, Partially Paid
- `workflow.json` - Added Customer Receipt Workflow

**Workflow States:**
- Draft (docstatus=0)
- Issued (docstatus=1)
- Partially Paid (docstatus=1) - Auto
- Paid (docstatus=1) - Auto
- Cancelled (docstatus=2)

**Transitions:**
- Draft → Issued (Issue action)
- Issued → Cancelled (Cancel action)
- Partially Paid → Cancelled (Cancel action)

**Auto Status Updates:**
- Payment Entry hooks automatically update status: Issued → Partially Paid → Paid
- Status changes based on outstanding amount

### 2. Tracking Fields

**Added Fields:**
- `workflow_state` - Link to Workflow State
- `created_by_user` - Who created the receipt
- `created_on` - When created
- `issued_by_user` - Who issued (submitted) it
- `issued_on` - When issued
- `first_printed_by` - Who printed first
- `first_printed_on` - When first printed
- `paid_on` - When fully paid
- `last_payment_entry` - Last payment reference

**Tracking Section:**
Collapsible section showing all tracking information in 4 columns:
- Column 1: Created by/on
- Column 2: Issued by/on
- Column 3: First printed by/on
- Column 4: Paid on, Last payment

### 3. Native ERPNext Connections

**Uses `links` property for native connections tab:**

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

**Benefits:**
- Native ERPNext UI styling
- Automatic link detection
- Grouped by category (Payment, Reference)
- Click to navigate to linked documents
- Shows document count

### 4. Python Implementation

**New Methods:**
- `track_creation()` - Auto-track on first save
- `track_issuance()` - Track on submit
- `get_last_payment_entry()` - Get latest payment
- `track_print()` - Whitelisted method for print tracking

**Enhanced Methods:**
- `compute_totals()` - Now tracks `paid_on` timestamp
- `recompute_payment_state()` - Syncs workflow_state with status
- `on_submit()` - Tracks issuance details

### 5. JavaScript Enhancement

**Print Tracking:**
```javascript
frm.page.on('print', function() {
    frappe.call({
        method: 'track_print',
        doc: frm.doc,
        callback: function(r) {
            if (r.message) {
                frm.reload_doc();
            }
        }
    });
});
```

## Workflow Behavior

### Draft → Issued
- Action: "Issue" button
- Triggers: `on_submit()`
- Tracks: `issued_by_user`, `issued_on`
- Sets: `docstatus=1`, `status="Issued"`, `workflow_state="Issued"`

### Issued → Partially Paid
- Trigger: Payment Entry submitted with partial payment
- Auto-detected in `compute_totals()`
- Sets: `status="Partially Paid"`, `workflow_state="Partially Paid"`

### Partially Paid → Paid
- Trigger: Payment Entry covers full outstanding
- Auto-detected in `compute_totals()`
- Tracks: `paid_on` timestamp
- Sets: `status="Paid"`, `workflow_state="Paid"`

### Print Tracking
- First print tracked automatically
- Records: `first_printed_by`, `first_printed_on`
- Subsequent prints not tracked (only first)

## Installation Steps

1. **Reload DocTypes:**
```bash
bench --site [site-name] reload-doc imogi_finance "DocType" "Customer Receipt"
bench --site [site-name] reload-doc imogi_finance "DocType" "Customer Receipt Item"
```

2. **Install Fixtures:**
```bash
bench --site [site-name] migrate
```

3. **Clear Cache:**
```bash
bench --site [site-name] clear-cache
bench restart
```

4. **Verify Workflow:**
- Go to: Setup > Workflow > Customer Receipt Workflow
- Check if workflow is active
- Verify states and transitions

## Usage

### Creating Receipt
1. Fill customer, company, receipt purpose
2. Add items (Sales Order or Sales Invoice)
3. Save - `created_by_user` and `created_on` tracked
4. Click "Issue" workflow button
5. Receipt submitted - `issued_by_user` and `issued_on` tracked

### Making Payment
1. Open submitted receipt
2. Click "Make Payment Entry" button
3. Fill payment details and submit
4. Receipt status auto-updates to "Partially Paid" or "Paid"
5. `paid_on` tracked when fully paid

### Printing
1. Open submitted receipt
2. Click Print button
3. First print tracked - `first_printed_by` and `first_printed_on`

### Viewing Connections
1. Open receipt
2. Click "Connections" tab
3. See grouped connections:
   - **Payment**: All linked Payment Entries
   - **Reference**: All linked Sales Orders/Invoices

## Benefits

1. **Native UI** - Uses ERPNext's built-in connections feature
2. **Auto-linking** - ERPNext automatically detects and shows links
3. **Audit Trail** - Complete tracking of who did what and when
4. **Workflow Control** - Clear state transitions
5. **Better UX** - Grouped, styled, clickable connections

## Notes

- `workflow_state` field is managed by ERPNext workflow engine
- `status` field still exists for backward compatibility
- Both fields are kept in sync
- Connections appear automatically in native tab
- No manual connection field updates needed

## Testing

### Test Workflow States
```python
# Create and check tracking
receipt = frappe.new_doc("Customer Receipt")
receipt.customer = "Test Customer"
receipt.company = "Test Company"
receipt.receipt_purpose = "Billing (Sales Invoice)"
receipt.save()
# Check: created_by_user and created_on should be set

receipt.submit()
# Check: issued_by_user and issued_on should be set
# Check: workflow_state = "Issued"
```

### Test Connections
1. Create Customer Receipt with Sales Invoice
2. Create Payment Entry linked to receipt
3. Open receipt and check "Connections" tab
4. Should show Sales Invoice under "Reference"
5. Should show Payment Entry under "Payment"

## Migration from Old Fields

Old custom connection fields removed:
- `connections_section`
- `linked_sales_orders`
- `linked_sales_invoices`
- `linked_payment_entries`

These are now handled natively by ERPNext's `links` property.
