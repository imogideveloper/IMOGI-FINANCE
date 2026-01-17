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
    "group": "Tax",
    "link_doctype": "Tax Invoice OCR Upload",
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
  },
  {
    "group": "Tax",
    "link_doctype": "Tax Invoice OCR Upload",
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

## 📝 Code Cleanup Opportunities

Now that native connections are implemented, you can **remove** manual connection management code:

### Python Code to Remove
```python
# In expense_request.py or similar
def update_connections(self):  # DELETE THIS
    ...

def set_linked_documents(self):  # DELETE THIS
    ...
```

### JavaScript Code to Remove
```javascript
// In expense_request.js or similar
frm.add_custom_button('View Linked Docs', ...);  // DELETE THIS
```

### Custom Fields to Remove
- `linked_purchase_invoices` (Small Text)
- `linked_payment_entries` (Small Text)
- Any other custom connection display fields

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
