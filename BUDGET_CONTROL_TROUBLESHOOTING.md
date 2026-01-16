# 🔍 Troubleshooting: Budget Control Entry Tidak Jalan di Expense Request

## Problem Statement
Budget Control Entry (RESERVATION) tidak dibuat saat Expense Request di-approve, padahal CONSUMPTION di Purchase Invoice berjalan normal.

## Root Cause Analysis

### Kondisi yang Harus Dipenuhi untuk RESERVATION

File: `imogi_finance/budget_control/workflow.py` - Fungsi `handle_expense_request_workflow()` (line 448-464)

```python
def handle_expense_request_workflow(expense_request, action: str | None, next_state: str | None):
    settings = utils.get_settings()
    
    # ❌ KONDISI 1: enable_budget_lock harus aktif
    if not settings.get("enable_budget_lock"):
        return

    target_state = settings.get("lock_on_workflow_state") or "Approved"
    _record_budget_workflow_event(expense_request, action, next_state, target_state)

    # ❌ KONDISI 2: Action tidak boleh Reject/Reopen
    if action in {"Reject", "Reopen"} or (next_state and next_state not in {target_state, "PI Created"}):
        release_budget_for_request(expense_request, reason=action)
        return

    # ❌ KONDISI 3: Status/workflow_state harus = target_state (default: "Approved")
    status = getattr(expense_request, "status", None)
    workflow_state = getattr(expense_request, "workflow_state", None)
    if status == target_state or workflow_state == target_state or next_state == target_state:
        reserve_budget_for_request(expense_request, trigger_action=action, next_state=next_state)
```

### ✅ Checklist Debugging

Jalankan query berikut untuk cek kondisi:

#### 1. Cek Budget Control Settings
```sql
SELECT 
    enable_budget_lock,
    lock_on_workflow_state,
    enforce_mode
FROM `tabBudget Control Settings`;
```

**Expected:**
- `enable_budget_lock` = 1
- `lock_on_workflow_state` = "Approved" (atau state yang sesuai)
- `enforce_mode` = "Both" atau "ER Approval + PI Submit"

#### 2. Cek Expense Request yang Bermasalah
```sql
SELECT 
    name,
    status,
    workflow_state,
    budget_lock_status,
    budget_workflow_state
FROM `tabExpense Request`
WHERE name = 'ER-xxxxx'  -- Ganti dengan nama ER
LIMIT 1;
```

**Expected saat approved:**
- `workflow_state` = "Approved"
- `status` = "Approved"

#### 3. Cek Budget Control Entry
```sql
SELECT 
    name,
    entry_type,
    direction,
    ref_doctype,
    ref_name,
    amount,
    cost_center,
    account
FROM `tabBudget Control Entry`
WHERE ref_doctype = 'Expense Request'
AND ref_name = 'ER-xxxxx'  -- Ganti dengan nama ER
ORDER BY creation DESC;
```

**Expected:**
- Entry type = "RESERVATION"
- Direction = "OUT"

---

## 🛠️ Solusi

### Solusi 1: Aktifkan Budget Lock di Settings

1. Buka **Budget Control Settings**
2. Centang **Enable Budget Lock**
3. Set **Lock on Workflow State** = "Approved"
4. Set **Enforce Mode** = "Both"
5. Save

### Solusi 2: Cek Workflow State yang Benar

Pastikan Expense Request menggunakan **workflow state** yang sesuai dengan `lock_on_workflow_state`:

```python
# Di Expense Request workflow config
# State yang trigger reservation harus match dengan setting
```

### Solusi 3: Enable Logging untuk Debug

Tambahkan logging di `imogi_finance/budget_control/workflow.py`:

```python
def handle_expense_request_workflow(expense_request, action: str | None, next_state: str | None):
    settings = utils.get_settings()
    
    # DEBUG LOG
    frappe.logger().info(f"""
    === Budget Workflow Debug ===
    ER: {getattr(expense_request, 'name', 'Unknown')}
    Action: {action}
    Next State: {next_state}
    Status: {getattr(expense_request, 'status', None)}
    Workflow State: {getattr(expense_request, 'workflow_state', None)}
    
    Settings:
    - enable_budget_lock: {settings.get('enable_budget_lock')}
    - lock_on_workflow_state: {settings.get('lock_on_workflow_state')}
    - enforce_mode: {settings.get('enforce_mode')}
    =============================
    """)
    
    if not settings.get("enable_budget_lock"):
        frappe.logger().warning("Budget lock DISABLED - skipping")
        return
    # ... rest of code
```

---

## 🔍 Quick Test Query

Jalankan query ini untuk cek kenapa reservation tidak dibuat:

```sql
-- Cek setting
SELECT 
    'Settings' as source,
    enable_budget_lock,
    lock_on_workflow_state,
    enforce_mode
FROM `tabBudget Control Settings`

UNION ALL

-- Cek ER terakhir yang di-approve
SELECT 
    'Last ER' as source,
    status as enable_budget_lock,
    workflow_state as lock_on_workflow_state,
    budget_lock_status as enforce_mode
FROM `tabExpense Request`
WHERE status = 'Approved'
ORDER BY modified DESC
LIMIT 1;
```

---

## 📊 Expected Flow vs Current State

### Expected Flow:
```
ER Submit
  → on_submit() dipanggil
    → handle_expense_request_workflow("Submit", "Pending Review")
      → Skip (karena state != "Approved")

ER Approved (workflow action)
  → on_workflow_action("Approve", "Approved")
    → handle_expense_request_workflow("Approve", "Approved")
      → ✅ reserve_budget_for_request()
        → RESERVATION entry dibuat
```

### Current State (Issue):
```
ER Approved (workflow action)
  → on_workflow_action("Approve", "Approved")
    → handle_expense_request_workflow("Approve", "Approved")
      → ❌ Salah satu kondisi tidak terpenuhi
        → Function return early
        → RESERVATION tidak dibuat
```

---

## 🎯 Action Items

1. **Immediate Check:**
   ```bash
   # SSH ke server
   bench --site imogi.finance console
   ```
   
   ```python
   # Di console
   from imogi_finance.budget_control import utils
   settings = utils.get_settings()
   print(f"enable_budget_lock: {settings.get('enable_budget_lock')}")
   print(f"lock_on_workflow_state: {settings.get('lock_on_workflow_state')}")
   print(f"enforce_mode: {settings.get('enforce_mode')}")
   ```

2. **Test dengan ER baru:**
   - Buat Expense Request baru
   - Approve hingga status = "Approved"
   - Cek apakah Budget Control Entry dibuat

3. **Review Log:**
   ```bash
   tail -f logs/worker.log | grep "reserve_budget_for_request"
   ```

---

## 📝 Related Files

- [budget_control/workflow.py](imogi_finance/budget_control/workflow.py#L448-L464) - Main logic
- [budget_control/utils.py](imogi_finance/budget_control/utils.py#L20-L33) - Settings default
- [expense_request.py](imogi_finance/imogi_finance/doctype/expense_request/expense_request.py#L177-L189) - Hook caller
- [hooks.py](imogi_finance/hooks.py) - Event registration

---

**Updated:** {{ now() }}
