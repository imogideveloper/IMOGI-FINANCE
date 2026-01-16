# 🐛 Fix: Budget Approval Workflow State Tidak Berubah

## Masalah

Budget Reclass Request (BCR-2026-00009) menunjukkan:
- User sudah approve (terlihat di activity log)
- Tapi workflow state tetap "Pending Approval"
- Status tidak berubah setelah approval

## Root Cause

Fungsi `advance_approval_level()` di `imogi_finance/budget_approval.py` hanya mengubah field di **memory** tapi **tidak menyimpan ke database**.

```python
# ❌ BEFORE (Bug)
def advance_approval_level(doc):
    current_level = getattr(doc, "current_approval_level", 0) or 1
    record_approval_timestamp(doc, current_level)
    next_level = current_level + 1
    next_user = getattr(doc, f"level_{next_level}_user", None)
    
    if next_user:
        doc.current_approval_level = next_level
        doc.workflow_state = "Pending Approval"  # ❌ Hanya di memory
        doc.status = "Pending Approval"          # ❌ Tidak tersimpan
    else:
        doc.current_approval_level = 0
        doc.workflow_state = "Approved"  # ❌ Hilang setelah workflow action selesai
        doc.status = "Approved"
```

Setelah `on_workflow_action()` selesai, Frappe tidak otomatis save perubahan field, jadi perubahan hilang.

## Solution

Gunakan `doc.db_set()` untuk menyimpan perubahan langsung ke database:

```python
# ✅ AFTER (Fixed)
def advance_approval_level(doc):
    current_level = getattr(doc, "current_approval_level", 0) or 1
    record_approval_timestamp(doc, current_level)
    next_level = current_level + 1
    next_user = getattr(doc, f"level_{next_level}_user", None)
    
    if next_user:
        # Move to next level
        doc.current_approval_level = next_level
        doc.workflow_state = "Pending Approval"
        doc.status = "Pending Approval"
        
        # ✅ Save to database
        if hasattr(doc, "db_set"):
            doc.db_set("current_approval_level", next_level)
            doc.db_set("workflow_state", "Pending Approval")
            doc.db_set("status", "Pending Approval")
    else:
        # No more levels, mark as approved
        doc.current_approval_level = 0
        doc.workflow_state = "Approved"
        doc.status = "Approved"
        
        # ✅ Save to database
        if hasattr(doc, "db_set"):
            doc.db_set("current_approval_level", 0)
            doc.db_set("workflow_state", "Approved")
            doc.db_set("status", "Approved")
```

## Files Changed

### 1. `imogi_finance/budget_approval.py`
- ✅ Fixed `advance_approval_level()` - tambahkan `db_set()` untuk workflow_state, status, current_approval_level
- ✅ Fixed `record_approval_timestamp()` - tambahkan `db_set()` untuk approved_by dan approved_at fields

### 2. `imogi_finance/imogi_finance/doctype/budget_reclass_request/budget_reclass_request.py`
- ✅ Fixed `on_workflow_action()` - Submit action menggunakan `db_set()`
- ✅ Fixed `on_workflow_action()` - Reject action menggunakan `db_set()`

### 3. `imogi_finance/imogi_finance/doctype/additional_budget_request/additional_budget_request.py`
- ✅ Fixed `on_workflow_action()` - Submit action menggunakan `db_set()`
- ✅ Fixed `on_workflow_action()` - Reject action menggunakan `db_set()`

## Testing

### Manual Test
1. Buat Budget Reclass Request baru
2. Submit document
3. Approve dengan user pertama
4. ✅ Cek workflow_state berubah:
   - Jika ada level 2: state = "Pending Approval", current_approval_level = 2
   - Jika hanya 1 level: state = "Approved", current_approval_level = 0
5. Refresh halaman - state harus tetap tersimpan

### SQL Check
```sql
-- Check dokumen yang sudah di-approve
SELECT name, workflow_state, status, current_approval_level,
       level_1_approved_by, level_1_approved_at,
       level_2_approved_by, level_2_approved_at
FROM `tabBudget Reclass Request`
WHERE name = 'BCR-2026-00009';

-- Expected result setelah approval:
-- workflow_state: "Approved" atau "Pending Approval" (tergantung level)
-- current_approval_level: angka yang benar atau 0 jika sudah approved semua
-- level_X_approved_by: user yang approve
-- level_X_approved_at: timestamp
```

### Console Test
```javascript
// Di browser console pada form Budget Reclass Request
frappe.call({
    method: 'frappe.client.get_value',
    args: {
        doctype: 'Budget Reclass Request',
        filters: {name: cur_frm.doc.name},
        fieldname: ['workflow_state', 'status', 'current_approval_level']
    },
    callback: function(r) {
        console.log('DB Values:', r.message);
        console.log('Form Values:', {
            workflow_state: cur_frm.doc.workflow_state,
            status: cur_frm.doc.status,
            current_approval_level: cur_frm.doc.current_approval_level
        });
    }
});
```

## Impact Analysis

### Affected Doctypes
- ✅ Budget Reclass Request
- ✅ Additional Budget Request
- ⚠️ Expense Request (menggunakan ApprovalService, tidak terpengaruh)
- ⚠️ Internal Charge Request (workflow berbeda, tidak terpengaruh)

### Backward Compatibility
✅ **Safe** - Perbaikan ini hanya menambahkan `db_set()` tanpa mengubah logic:
- Existing code tetap jalan
- Tidak ada breaking changes
- Hanya memastikan perubahan tersimpan ke database

## Deployment

```bash
# 1. Pull latest changes
cd ~/frappe-bench/apps/imogi_finance
git pull

# 2. Restart untuk reload Python code
bench restart

# 3. Test dengan document baru (jangan gunakan document lama yang stuck)
```

### Untuk Document yang Sudah Stuck

Document yang sudah terlanjur stuck (seperti BCR-2026-00009) perlu di-fix manual:

```sql
-- Option 1: Reset untuk di-approve ulang
UPDATE `tabBudget Reclass Request`
SET workflow_state = 'Pending Approval',
    status = 'Pending Approval',
    current_approval_level = 1
WHERE name = 'BCR-2026-00009';

-- Option 2: Langsung set ke Approved (jika sudah benar-benar di-approve)
UPDATE `tabBudget Reclass Request`
SET workflow_state = 'Approved',
    status = 'Approved',
    current_approval_level = 0
WHERE name = 'BCR-2026-00009';
```

Atau gunakan Frappe console:
```python
doc = frappe.get_doc("Budget Reclass Request", "BCR-2026-00009")
doc.workflow_state = "Approved"
doc.status = "Approved"
doc.current_approval_level = 0
doc.db_update()
frappe.db.commit()
```

## Prevention

Pattern yang benar untuk workflow state management:

```python
def on_workflow_action(self, action, **kwargs):
    if action == "Something":
        # 1. Update field di memory (untuk logic)
        self.workflow_state = "New State"
        self.status = "New State"
        
        # 2. Save ke database (agar tidak hilang)
        if hasattr(self, "db_set"):
            self.db_set("workflow_state", "New State")
            self.db_set("status", "New State")
```

## References

Lihat implementasi yang benar di:
- `imogi_finance/budget_control/workflow.py` - `_set_budget_workflow_state()`
- `imogi_finance/transfer_application/payment_entry_hooks.py` - `on_submit()`
- `imogi_finance/events/internal_charge_request.py` - `sync_status_with_workflow()`

Semua menggunakan `db_set()` atau `frappe.db.set_value()` untuk persist perubahan.
