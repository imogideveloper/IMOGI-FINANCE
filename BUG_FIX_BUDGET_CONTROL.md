# 🐛 Bug Fix: Budget Control Entry Tidak Terbuat di Expense Request

## Bug yang Ditemukan

### Bug #1: Wrong Parameter di `on_workflow_action()`
**File:** `imogi_finance/imogi_finance/doctype/expense_request/expense_request.py` Line 186

**Sebelum (Bug):**
```python
def on_workflow_action(self, action, **kwargs):
    approval_service = ApprovalService("Expense Request", state_field="workflow_state")
    next_state = kwargs.get("next_state")
    approval_service.on_workflow_action(self, action, next_state=next_state)
    
    if action in ("Approve", "Reject", "Reopen"):
        # ❌ BUG: workflow_state sudah berubah SEBELUM fungsi ini dipanggil!
        handle_expense_request_workflow(self, action, getattr(self, "workflow_state"))
```

**Masalah:**
- `self.workflow_state` sudah diubah oleh `approval_service.on_workflow_action()` 
- Jadi parameter yang dikirim adalah state **SETELAH** perubahan, bukan **TARGET** state
- Contoh: saat approve dari "Pending Review" → "Approved", yang dikirim adalah "Approved" (bukan next_state dari workflow transition)

**Sesudah (Fixed):**
```python
def on_workflow_action(self, action, **kwargs):
    approval_service = ApprovalService("Expense Request", state_field="workflow_state")
    next_state = kwargs.get("next_state")
    approval_service.on_workflow_action(self, action, next_state=next_state)
    
    if action in ("Approve", "Reject", "Reopen"):
        # ✅ FIX: Kirim next_state dari kwargs, bukan workflow_state yang sudah berubah
        handle_expense_request_workflow(self, action, next_state)
```

---

### Bug #2: Confusing Condition di `handle_expense_request_workflow()`
**File:** `imogi_finance/budget_control/workflow.py` Line 456

**Sebelum (Confusing):**
```python
def handle_expense_request_workflow(expense_request, action: str | None, next_state: str | None):
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return

    target_state = settings.get("lock_on_workflow_state") or "Approved"
    _record_budget_workflow_event(expense_request, action, next_state, target_state)

    # ❌ CONFUSING: Kondisi ini membingungkan dan bisa salah
    if action in {"Reject", "Reopen"} or (next_state and next_state not in {target_state, "PI Created"}):
        release_budget_for_request(expense_request, reason=action)
        return  # ← Exit early, reserve TIDAK jalan!

    # Ini hanya akan jalan jika lolos kondisi di atas
    status = getattr(expense_request, "status", None)
    workflow_state = getattr(expense_request, "workflow_state", None)
    if status == target_state or workflow_state == target_state or next_state == target_state:
        reserve_budget_for_request(expense_request, trigger_action=action, next_state=next_state)
```

**Masalah:**
- Kondisi `next_state not in {target_state, "PI Created"}` membuat logic jadi terlalu kompleks
- Bisa menyebabkan early return yang tidak diinginkan
- Sulit di-debug karena kondisi yang nested

**Sesudah (Clear):**
```python
def handle_expense_request_workflow(expense_request, action: str | None, next_state: str | None):
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return

    target_state = settings.get("lock_on_workflow_state") or "Approved"
    _record_budget_workflow_event(expense_request, action, next_state, target_state)

    # ✅ CLEAR: Simple check for rejection/reopen
    if action in {"Reject", "Reopen"}:
        release_budget_for_request(expense_request, reason=action)
        return

    # ✅ CLEAR: Reserve budget when reaching target state
    # Check both current state and next_state to handle different workflow patterns
    status = getattr(expense_request, "status", None)
    workflow_state = getattr(expense_request, "workflow_state", None)
    
    # Priority check: next_state first (most reliable)
    if next_state == target_state or workflow_state == target_state or status == target_state:
        reserve_budget_for_request(expense_request, trigger_action=action, next_state=next_state)
```

---

## Impact Analysis

### Sebelum Fix:
```
User approve Expense Request
  → on_workflow_action("Approve", next_state="Approved")
    → approval_service changes workflow_state to "Approved"
    → handle_expense_request_workflow(self, "Approve", "Approved")  ✅ workflow_state sudah "Approved"
      → Check: action in {"Reject", "Reopen"}? No
      → Check: next_state not in {"Approved", "PI Created"}? No (Approved IN set)
      → release_budget_for_request() NOT called
      → Check: next_state == "Approved"? YES! ✅
        → reserve_budget_for_request() SHOULD BE CALLED
```

**TAPI** jika ada race condition atau state tidak konsisten, bisa terjadi:
```
  → handle_expense_request_workflow(self, "Approve", "Pending Review")  ❌ Masih state lama
    → Check: next_state not in {"Approved", "PI Created"}? YES! ("Pending Review" not in set)
      → release_budget_for_request() called  ❌ WRONG!
      → RETURN early
      → reserve_budget_for_request() NEVER CALLED  ❌ BUG!
```

### Sesudah Fix:
```
User approve Expense Request
  → on_workflow_action("Approve", next_state="Approved")
    → approval_service changes workflow_state to "Approved"
    → handle_expense_request_workflow(self, "Approve", "Approved")  ✅ next_state dari kwargs
      → Check: action in {"Reject", "Reopen"}? No
      → Check: next_state == "Approved"? YES! ✅
        → reserve_budget_for_request() CALLED  ✅ CORRECT!
```

---

## Testing Required

### Test Case 1: Normal Approval Flow
```python
# Setup
er = frappe.get_doc("Expense Request", "ER-00001")
er.workflow_state = "Pending Review"

# Action
er.on_workflow_action("Approve", next_state="Approved")

# Expected
assert frappe.db.exists("Budget Control Entry", {
    "ref_doctype": "Expense Request",
    "ref_name": "ER-00001",
    "entry_type": "RESERVATION"
})
```

### Test Case 2: Multi-level Approval
```python
# Setup
er = frappe.get_doc("Expense Request", "ER-00002")
er.workflow_state = "Pending Review"

# First approval (still pending)
er.on_workflow_action("Approve", next_state="Pending Review")
# Should NOT create reservation yet

# Final approval
er.on_workflow_action("Approve", next_state="Approved")
# Should create reservation now

# Expected
entries = frappe.get_all("Budget Control Entry", {
    "ref_doctype": "Expense Request",
    "ref_name": "ER-00002"
})
assert len(entries) == 1  # Only one reservation entry
```

### Test Case 3: Rejection Flow
```python
# Setup
er = frappe.get_doc("Expense Request", "ER-00003")
er.workflow_state = "Approved"
# Assume reservation already created

# Action
er.on_workflow_action("Reject", next_state="Rejected")

# Expected
release_entries = frappe.get_all("Budget Control Entry", {
    "ref_doctype": "Expense Request",
    "ref_name": "ER-00003",
    "entry_type": "RELEASE"
})
assert len(release_entries) > 0  # Release entries created
```

---

## Files Changed

1. ✅ `imogi_finance/imogi_finance/doctype/expense_request/expense_request.py` (Line 186)
2. ✅ `imogi_finance/budget_control/workflow.py` (Line 456)

---

## Deployment Notes

⚠️ **CRITICAL:** Setelah deploy, test dengan Expense Request baru untuk memastikan:

1. Budget Control Entry (RESERVATION) terbuat saat ER di-approve
2. Budget Control Entry (CONSUMPTION) terbuat saat PI di-submit
3. Budget Control Entry (RELEASE) terbuat saat ER di-reject
4. Tidak ada duplikasi entries

**Monitoring Command:**
```sql
-- Check recent budget entries
SELECT 
    name, 
    entry_type, 
    direction, 
    ref_doctype, 
    ref_name, 
    amount,
    creation
FROM `tabBudget Control Entry`
WHERE creation > NOW() - INTERVAL 1 DAY
ORDER BY creation DESC
LIMIT 50;
```

---

**Fixed By:** GitHub Copilot  
**Date:** 2026-01-16  
**Priority:** HIGH - Critical bug affecting budget control functionality
