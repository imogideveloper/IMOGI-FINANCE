# Internal Charge & Budget Control - Complete Flow Analysis

**Tanggal:** 16 Januari 2026  
**Status:** ✅ ANALISIS LENGKAP

---

## 📋 Executive Summary

Internal Charge Request **SUDAH terhubung dengan Budget Control Entry** melalui mekanisme **allocation slices**. Tidak perlu ledger khusus karena setiap transaksi Internal Charge menciptakan Budget Control Entry dengan ref_doctype dan ref_name yang jelas.

**Key Finding:**
- ✅ Internal Charge menggunakan Budget Control Entry untuk tracking
- ✅ Setiap line IC → generates multiple Budget Control Entries (per account × per cost center)
- ✅ Journal Entry (JE) hanya untuk reclass GL, bukan untuk budget tracking
- ⚠️ Ada gap dalam budget validation saat IC Approval

---

## 1. Flow Lengkap: Internal Charge → Budget Control Entry

### 1.1 Kapan Budget Control Entry Dibuat?

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTERNAL CHARGE LIFECYCLE                    │
└─────────────────────────────────────────────────────────────────┘

1. CREATE INTERNAL CHARGE (Draft)
   ├─ User creates IC Request from Expense Request
   ├─ Function: create_internal_charge_from_expense_request()
   └─ Status: Draft, NO Budget Control Entry yet

2. APPROVE INTERNAL CHARGE (Line by Line)
   ├─ Multi-level approval (L1 → L2 → L3)
   ├─ Per-line, per-cost-center approval
   └─ Status: Approved, NO Budget Control Entry yet
   
3. EXPENSE REQUEST APPROVAL (Budget Lock)
   ├─ Function: reserve_budget_for_request()
   ├─ Creates allocation_slices using _build_allocation_slices()
   ├─ IF allocation_mode = "Allocated via Internal Charge":
   │  ├─ Load IC doc (must be Approved)
   │  ├─ Calculate ratio per IC line
   │  └─ Generate slices: (dims, amount) per account × per IC line
   │
   └─ Creates Budget Control Entry:
      ├─ entry_type: "RESERVATION"
      ├─ direction: "OUT"
      ├─ ref_doctype: "Expense Request"
      ├─ ref_name: ER-XXX
      └─ One entry per slice (cost_center × account)

4. PURCHASE INVOICE SUBMIT
   ├─ Function A: consume_budget_for_purchase_invoice()
   │  ├─ Creates Budget Control Entry:
   │  │  ├─ entry_type: "CONSUMPTION"
   │  │  ├─ direction: "IN"
   │  │  ├─ ref_doctype: "Purchase Invoice"
   │  │  └─ ref_name: PI-XXX
   │  └─ Updates ER: budget_lock_status = "Consumed"
   │
   └─ Function B: maybe_post_internal_charge_je()
      ├─ IF internal_charge_posting_mode = "Auto JE on PI Submit"
      ├─ Creates Journal Entry (GL reclass)
      │  ├─ Credit: source_cost_center (ER cost center)
      │  └─ Debit: target_cost_centers (IC lines)
      └─ NO Budget Control Entry (JE is for GL only)
```

### 1.2 Allocation Slices Mechanism

**Source Code:** [imogi_finance/budget_control/workflow.py](imogi_finance/budget_control/workflow.py#L218-L263)

```python
def _build_allocation_slices(expense_request, *, settings=None, ic_doc=None):
    """
    Generates allocation slices based on:
    - Expense Request items (→ expense accounts)
    - Internal Charge lines (→ target cost centers + ratio)
    
    Returns: List[(Dimensions, amount)]
    """
    
    # Step 1: Get account totals from ER items
    total_amount, account_totals = _get_account_totals(expense_request.items)
    # Example: {
    #   "6110 - Travel Expense": 1000,
    #   "6120 - Meal Expense": 500
    # }
    
    # Step 2: If allocation_mode != "Allocated via Internal Charge"
    if expense_request.allocation_mode != "Allocated via Internal Charge":
        # Direct allocation to ER cost center
        for account, amount in account_totals.items():
            dims = resolve_dims(
                cost_center=expense_request.cost_center,
                account=account,
                ...
            )
            slices.append((dims, amount))
        return slices
    
    # Step 3: Load Internal Charge Request
    ic_doc = _load_internal_charge_request(expense_request.internal_charge_request)
    
    # Step 4: For each IC line, calculate ratio and allocate
    for line in ic_doc.internal_charge_lines:
        ratio = line.amount / total_amount
        # Example: Line 1 (CC-A): 600/1500 = 0.4 (40%)
        #          Line 2 (CC-B): 900/1500 = 0.6 (60%)
        
        for account, account_amount in account_totals.items():
            dims = resolve_dims(
                cost_center=line.target_cost_center,  # ← IC target CC
                account=account,
                ...
            )
            slices.append((dims, account_amount * ratio))
            # Example: (CC-A, 6110, 400), (CC-A, 6120, 200)
            #          (CC-B, 6110, 600), (CC-B, 6120, 300)
    
    return slices
```

**Example:**
```
Expense Request:
- Total: 1500
- Items:
  - Travel (6110): 1000
  - Meal (6120): 500
- Source Cost Center: CC-HQ
- allocation_mode: "Allocated via Internal Charge"

Internal Charge Request:
- Line 1: CC-A → 600 (40%)
- Line 2: CC-B → 900 (60%)

Allocation Slices Generated:
1. (CC-A, 6110, 400)  ← 1000 × 40%
2. (CC-A, 6120, 200)  ← 500 × 40%
3. (CC-B, 6110, 600)  ← 1000 × 60%
4. (CC-B, 6120, 300)  ← 500 × 60%

Budget Control Entries Created (RESERVATION):
- Entry 1: CC-A, 6110, 400, OUT, ref=ER-XXX
- Entry 2: CC-A, 6120, 200, OUT, ref=ER-XXX
- Entry 3: CC-B, 6110, 600, OUT, ref=ER-XXX
- Entry 4: CC-B, 6120, 300, OUT, ref=ER-XXX
```

---

## 2. Budget Control Entry Types & Internal Charge

### 2.1 Entry Types Matrix

| Entry Type | Direction | Kapan Terjadi | ref_doctype | ref_name |
|------------|-----------|---------------|-------------|----------|
| **RESERVATION** | OUT | ER Approval (budget lock) | Expense Request | ER-XXX |
| **CONSUMPTION** | IN | PI Submit | Purchase Invoice | PI-XXX |
| **RELEASE** | IN | ER Cancel/Reject | Expense Request | ER-XXX |
| **REVERSAL** | OUT | PI Cancel | Purchase Invoice | PI-XXX |
| **RECLASS** | IN/OUT | Manual budget reclass | Budget Reclass Request | BRR-XXX |
| **SUPPLEMENT** | IN | Additional budget | Additional Budget Request | ABR-XXX |

**Internal Charge Impact:**
- RESERVATION & CONSUMPTION menggunakan allocation_slices dari IC
- RELEASE & REVERSAL juga follow allocation_slices untuk reverse
- RECLASS/SUPPLEMENT tidak terkait langsung dengan IC

### 2.2 Query Budget Control Entries untuk Internal Charge

```sql
-- Get all budget entries for specific Expense Request
SELECT
  name,
  entry_type,
  direction,
  cost_center,
  account,
  amount,
  posting_date,
  ref_doctype,
  ref_name
FROM `tabBudget Control Entry`
WHERE ref_doctype = 'Expense Request'
  AND ref_name = 'ER-2024-00123'
  AND docstatus = 1
ORDER BY posting_date, creation;

-- Get budget impact per cost center
SELECT
  cost_center,
  account,
  SUM(CASE WHEN direction = 'OUT' THEN amount ELSE -amount END) as net_reserved
FROM `tabBudget Control Entry`
WHERE ref_doctype = 'Expense Request'
  AND ref_name = 'ER-2024-00123'
  AND entry_type IN ('RESERVATION', 'RELEASE')
  AND docstatus = 1
GROUP BY cost_center, account;
```

---

## 3. Journal Entry vs Budget Control Entry

### 3.1 Perbedaan Fundamental

| Aspek | Journal Entry (JE) | Budget Control Entry (BCE) |
|-------|-------------------|---------------------------|
| **Purpose** | GL reclass (accounting) | Budget tracking (control) |
| **When Created** | PI Submit (if Auto JE enabled) | ER Approval & PI Submit |
| **Accounts Affected** | GL Accounts (debit/credit) | Budget accounts (reserve/consume) |
| **Cost Center** | Multiple (source → targets) | Per-line (allocation) |
| **Entry Type** | Journal Entry | RESERVATION/CONSUMPTION/etc |
| **Reference** | Purchase Invoice | Expense Request / Purchase Invoice |
| **Can be Manual** | Yes (if mode = Manual) | No (always programmatic) |

### 3.2 Flow Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                   PURCHASE INVOICE SUBMIT                      │
└────────────────────────────────────────────────────────────────┘
                              |
                              ├─────────────────────────────────┐
                              │                                 │
                    ┌─────────▼─────────┐           ┌──────────▼──────────┐
                    │  BUDGET CONTROL   │           │   JOURNAL ENTRY     │
                    │      ENTRIES      │           │   (GL Reclass)      │
                    └───────────────────┘           └─────────────────────┘
                              │                                 │
        ┌─────────────────────┼─────────────────────┐          │
        │                     │                     │          │
┌───────▼───────┐   ┌─────────▼────────┐   ┌───────▼──────┐   │
│ CONSUMPTION   │   │  CONSUMPTION     │   │ CONSUMPTION  │   │
│ CC-A, 6110    │   │  CC-A, 6120      │   │ CC-B, 6110   │   │
│ 400, IN       │   │  200, IN         │   │ 600, IN      │   │
│ ref=PI-XXX    │   │  ref=PI-XXX      │   │ ref=PI-XXX   │   │
└───────────────┘   └──────────────────┘   └──────────────┘   │
                                                                │
                    ┌───────────────────────────────────────────┘
                    │
        ┌───────────▼──────────┐      ┌────────────────────────┐
        │ JE Line 1 (Credit)   │      │ JE Line 2 (Debit)      │
        │ CC-HQ, 6110, 1000    │      │ CC-A, 6110, 400        │
        │ CC-HQ, 6120, 500     │      │ CC-A, 6120, 200        │
        │                      │      │ CC-B, 6110, 600        │
        │                      │      │ CC-B, 6120, 300        │
        └──────────────────────┘      └────────────────────────┘
              ▲                                  ▲
              │                                  │
         Source CC                         Target CCs
       (from ER)                        (from IC lines)
```

---

## 4. Rules & Validation Flow

### 4.1 Internal Charge Approval Flow

**Source:** [imogi_finance/imogi_finance/doctype/internal_charge_request/internal_charge_request.py](imogi_finance/imogi_finance/doctype/internal_charge_request/internal_charge_request.py#L45-L110)

```
┌─────────────────────────────────────────────────────────────────┐
│             INTERNAL CHARGE APPROVAL (Per-Line)                 │
└─────────────────────────────────────────────────────────────────┘

1. VALIDATE (on save)
   ├─ _validate_amounts()
   │  ├─ Check: minimum 1 line
   │  ├─ Check: all amounts > 0
   │  └─ Check: sum(line.amount) = total_amount
   │
   ├─ _populate_line_routes()
   │  ├─ Load Expense Request
   │  ├─ Get expense accounts from ER items
   │  ├─ For each IC line:
   │  │  ├─ Resolve approval route for target_cost_center
   │  │  ├─ Store route_snapshot (level_1/2/3 approvers)
   │  │  └─ Set line_status: "Pending L1/L2/L3"
   │  └─ NO BUDGET CHECK ⚠️
   │
   └─ _sync_status()
      └─ Aggregate line_status → document status

2. SUBMIT
   ├─ Same validations as above
   └─ _sync_workflow_state()
      └─ Map status + line_status → workflow_state

3. APPROVE (Workflow Action)
   ├─ _validate_approve_permission()
   │  ├─ Check session user vs expected approver
   │  ├─ Filter approvable lines (user can approve)
   │  └─ Throw if no approvable lines
   │
   ├─ _advance_line_status()
   │  ├─ Pending L1 → Pending L2 (or Approved)
   │  ├─ Pending L2 → Pending L3 (or Approved)
   │  └─ Pending L3 → Approved
   │
   └─ _sync_status() + _sync_workflow_state()
      └─ Update document status/workflow_state

4. ALL LINES APPROVED
   ├─ status = "Approved"
   ├─ workflow_state = "Approved"
   ├─ Set approved_by, approved_on
   └─ IC READY for ER approval
```

**Key Points:**
- ✅ Per-line approval based on target_cost_center
- ✅ Multi-level (L1/L2/L3) support
- ✅ Partial approval support (some lines approved, others pending)
- ⚠️ **NO BUDGET VALIDATION** during IC approval

### 4.2 Expense Request Budget Lock Flow

**Source:** [imogi_finance/budget_control/workflow.py](imogi_finance/budget_control/workflow.py#L315-L390)

```
┌─────────────────────────────────────────────────────────────────┐
│          EXPENSE REQUEST APPROVAL (Budget Lock)                 │
└─────────────────────────────────────────────────────────────────┘

1. reserve_budget_for_request() triggered
   ├─ Check: enable_budget_lock = true
   ├─ Check: status/workflow_state = target_state (e.g., "Approved")
   │
   ├─ IF allocation_mode = "Allocated via Internal Charge":
   │  └─ _require_internal_charge_ready()
   │     ├─ Check: IC exists
   │     ├─ Check: IC status = "Approved" ✅
   │     ├─ Check: IC total = ER total
   │     └─ Check: ER has expense accounts
   │
   ├─ _build_allocation_slices()
   │  └─ Generate (dims, amount) per account × per IC line
   │
   ├─ _reverse_reservations()
   │  └─ Release any prior reservations
   │
   ├─ FOR EACH slice:
   │  ├─ check_budget_available(dims, amount)
   │  │  ├─ allocated = get from Budget doctype
   │  │  ├─ actual = get from GL Entry
   │  │  ├─ reserved = get from Budget Control Entry
   │  │  ├─ available = allocated - actual - reserved
   │  │  └─ IF available < amount AND !allow_overrun:
   │  │     └─ THROW "Insufficient budget"
   │  │
   │  └─ post_entry("RESERVATION", dims, amount, "OUT", ref=ER)
   │     └─ Creates Budget Control Entry ✅
   │
   └─ Update ER:
      ├─ budget_lock_status = "Locked" (or "Overrun Allowed")
      └─ budget_workflow_state = "Approved"
```

**Key Validations:**
1. ✅ Internal Charge must be Approved before ER approval
2. ✅ Budget availability checked per target cost center
3. ✅ Budget Control Entry created for tracking
4. ⚠️ Budget check happens **after** IC approval (not during)

---

## 5. Gap Analysis & Improvement Recommendations

### 5.1 Current Gaps

| Gap | Deskripsi | Impact | Priority |
|-----|-----------|--------|----------|
| **Gap 1: No Budget Check on IC Approval** | IC bisa di-approve tanpa cek budget availability di target cost centers | IC approved tapi ER approval gagal karena insufficient budget | 🔴 HIGH |
| **Gap 2: Limited JE Posting Mode** | Hanya "None" atau "Auto JE on PI Submit" | User tidak bisa post JE lebih awal (e.g., on IC Approval) | 🟡 MEDIUM |
| **Gap 3: No IC-Specific Report** | Tidak ada report khusus untuk IC allocation tracking | Sulit audit IC impact per cost center | 🟢 LOW |
| **Gap 4: No Budget Control Entry for IC Approval** | BCE hanya dibuat saat ER approval, bukan IC approval | IC approval tidak reflected di budget system | 🟡 MEDIUM |

### 5.2 Recommendation 1: Early Budget Validation (HIGH Priority)

**Problem:** Internal Charge bisa di-approve meskipun target cost centers tidak punya budget.

**Solution:**
```python
# In: internal_charge_request.py
def _validate_approve_permission(self):
    """Validate user can approve pending lines based on cost-centre routes."""
    
    # ... existing approval permission checks ...
    
    # NEW: Check budget availability for approvable lines
    if approvable_lines:
        self._validate_budget_for_lines(approvable_lines)
    
    # ... rest of approval logic ...

def _validate_budget_for_lines(self, lines):
    """Validate budget availability for IC lines before approval.
    
    This prevents IC approval when target cost centers lack budget,
    ensuring ER approval won't fail due to insufficient budget.
    """
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return  # Budget validation disabled
    
    # Only validate if setting enabled
    if not settings.get("internal_charge_validate_budget_on_approval"):
        return
    
    # Get ER info for account totals
    try:
        expense_request = frappe.get_doc("Expense Request", self.expense_request)
    except Exception:
        return  # Can't validate without ER
    
    total_amount, account_totals = accounting.summarize_request_items(
        getattr(expense_request, "items", []) or []
    )
    
    if not total_amount or not account_totals:
        return
    
    # Check budget for each line being approved
    insufficient_lines = []
    for line in lines:
        ratio = float(getattr(line, "amount", 0) or 0) / total_amount
        
        for account, account_amount in account_totals.items():
            dims = service.resolve_dims(
                company=utils.resolve_company_from_cost_center(
                    getattr(expense_request, "cost_center", None)
                ),
                fiscal_year=utils.resolve_fiscal_year(
                    getattr(expense_request, "fiscal_year", None)
                ),
                cost_center=getattr(line, "target_cost_center", None),
                account=account,
                project=getattr(expense_request, "project", None),
                branch=getattr(expense_request, "branch", None),
            )
            
            allocated_amount = account_amount * ratio
            result = service.check_budget_available(dims, allocated_amount)
            
            if not result.ok:
                insufficient_lines.append({
                    "cost_center": line.target_cost_center,
                    "account": account,
                    "required": allocated_amount,
                    "available": result.available or 0,
                    "message": result.message
                })
    
    if insufficient_lines:
        # Format error message
        messages = []
        for info in insufficient_lines:
            messages.append(
                _("Cost Center {cc}, Account {acc}: Required {req}, Available {avail}").format(
                    cc=info["cost_center"],
                    acc=info["account"],
                    req=info["required"],
                    avail=info["available"]
                )
            )
        
        frappe.throw(
            _("Insufficient budget for Internal Charge approval:\n{0}").format(
                "\n".join(messages)
            ),
            title=_("Budget Validation Failed")
        )
```

**Configuration:**
```python
# In: budget_control_settings.json
{
  "fieldname": "internal_charge_validate_budget_on_approval",
  "label": "Validate Budget on IC Approval",
  "fieldtype": "Check",
  "default": 0,
  "description": "Check budget availability for target cost centers during IC approval"
}
```

### 5.3 Recommendation 2: Flexible JE Posting Modes (MEDIUM Priority)

**Problem:** JE hanya bisa posted "None" atau "Auto on PI Submit".

**Solution:**
```python
# In: budget_control_settings.json
{
  "fieldname": "internal_charge_posting_mode",
  "label": "Internal Charge Posting Mode",
  "fieldtype": "Select",
  "options": "None\nAuto JE on IC Approval\nAuto JE on ER Approval\nAuto JE on PI Submit\nManual",
  "default": "None"
}
```

**Implementation:**
```python
# In: internal_charge_request.py
def before_workflow_action(self, action, **kwargs):
    # ... existing code ...
    
    if action == "Approve" and self.status == "Approved":
        # All lines approved
        self._maybe_post_internal_charge_je_on_approval()

def _maybe_post_internal_charge_je_on_approval(self):
    """Post JE when IC is fully approved if mode = 'Auto JE on IC Approval'."""
    settings = utils.get_settings()
    if settings.get("internal_charge_posting_mode") != "Auto JE on IC Approval":
        return
    
    try:
        expense_request = frappe.get_doc("Expense Request", self.expense_request)
    except Exception:
        return
    
    # Call existing JE posting logic (extract from workflow.maybe_post_internal_charge_je)
    from imogi_finance.budget_control import workflow
    workflow._post_internal_charge_je_impl(
        ic_doc=self,
        expense_request=expense_request,
        ref_doctype="Internal Charge Request",
        ref_name=self.name
    )
```

### 5.4 Recommendation 3: Budget Control Entry on IC Approval (MEDIUM Priority)

**Problem:** BCE hanya dibuat saat ER approval, tidak ada record saat IC approval.

**Solution:** Tambahkan entry type "IC_ALLOCATION" untuk tracking.

```python
# In: budget_control_entry.py
class BudgetControlEntry(Document):
    VALID_ENTRY_TYPES = {
        "RESERVATION", "CONSUMPTION", "RELEASE", 
        "RECLASS", "SUPPLEMENT", "REVERSAL",
        "IC_ALLOCATION"  # NEW
    }
    
    VALID_COMBINATIONS = {
        # ... existing ...
        "IC_ALLOCATION": ["OUT"]  # NEW
    }
```

```python
# In: internal_charge_request.py
def before_workflow_action(self, action, **kwargs):
    # ... existing code ...
    
    if action == "Approve" and self.status == "Approved":
        self._record_ic_allocation_entries()

def _record_ic_allocation_entries(self):
    """Record IC allocation in Budget Control Entry for tracking."""
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return
    
    if not settings.get("record_ic_allocation_entries"):
        return  # Feature toggle
    
    try:
        expense_request = frappe.get_doc("Expense Request", self.expense_request)
    except Exception:
        return
    
    # Build allocation slices
    slices = workflow._build_allocation_slices(
        expense_request,
        settings=settings,
        ic_doc=self
    )
    
    # Create IC_ALLOCATION entries (informational, not affecting availability)
    for dims, amount in slices:
        ledger.post_entry(
            "IC_ALLOCATION",
            dims,
            float(amount or 0),
            "OUT",
            ref_doctype="Internal Charge Request",
            ref_name=self.name,
            remarks=_("Internal Charge allocation for {0}").format(
                self.expense_request
            )
        )
```

### 5.5 Recommendation 4: IC Allocation Report (LOW Priority)

**Solution:** Create dedicated report "Internal Charge Allocation Report"

```sql
-- Report: Internal Charge Allocation Report
SELECT
  ic.name as internal_charge_request,
  ic.expense_request,
  ic.total_amount,
  ic.status,
  icl.target_cost_center,
  icl.amount as line_amount,
  icl.line_status,
  bce.entry_type,
  bce.account,
  bce.amount as budget_entry_amount,
  bce.direction,
  bce.posting_date
FROM `tabInternal Charge Request` ic
LEFT JOIN `tabInternal Charge Line` icl ON icl.parent = ic.name
LEFT JOIN `tabBudget Control Entry` bce 
  ON bce.ref_doctype IN ('Internal Charge Request', 'Expense Request')
  AND (bce.ref_name = ic.name OR bce.ref_name = ic.expense_request)
WHERE ic.docstatus = 1
  AND ic.allocation_mode = 'Allocated via Internal Charge'
ORDER BY ic.creation DESC, icl.idx;
```

---

## 6. Summary: Jawaban Langsung

### Q1: Apakah Internal Charge connect ke Budget Control Entry?
**A: YA** ✅

- Internal Charge menggunakan Budget Control Entry melalui mekanisme **allocation_slices**
- Setiap IC line menghasilkan multiple BCE (per account × per cost center)
- BCE dibuat saat:
  - ER Approval → RESERVATION entries
  - PI Submit → CONSUMPTION entries
- BCE memiliki `ref_doctype` dan `ref_name` untuk tracing

### Q2: Apakah perlu ledger khusus untuk Internal Charge?
**A: TIDAK** ❌

- Budget Control Entry **ADALAH** ledger untuk IC tracking
- Journal Entry hanya untuk GL reclass, bukan budget tracking
- Semua budget impact tercatat di BCE dengan:
  - `ref_doctype = "Expense Request"` (untuk RESERVATION)
  - `ref_doctype = "Purchase Invoice"` (untuk CONSUMPTION)
  - Filter by ER yang pakai IC untuk get IC-specific entries

### Q3: Apa yang perlu di-improve?
**A: 4 Area** ⚠️

1. **🔴 HIGH: Budget validation on IC approval** - Prevent IC approval jika target CC tidak punya budget
2. **🟡 MEDIUM: Flexible JE posting modes** - Allow JE posting on IC/ER approval
3. **🟡 MEDIUM: IC_ALLOCATION entry type** - Track IC approval in BCE
4. **🟢 LOW: IC allocation report** - Better visibility untuk IC impact

### Q4: Bagaimana cara query budget entries untuk specific IC?
**A: Via Expense Request reference**

```sql
-- Get all budget entries for IC
SELECT * FROM `tabBudget Control Entry`
WHERE ref_doctype = 'Expense Request'
  AND ref_name = (
    SELECT expense_request 
    FROM `tabInternal Charge Request` 
    WHERE name = 'IC-2024-00001'
  )
  AND docstatus = 1;
```

---

## 7. File Structure Reference

```
imogi_finance/
├─ budget_control/
│  ├─ workflow.py                     # reserve/consume/release budget
│  │  ├─ _build_allocation_slices()   # ← KEY: IC allocation logic
│  │  ├─ _require_internal_charge_ready()
│  │  ├─ reserve_budget_for_request()
│  │  ├─ consume_budget_for_purchase_invoice()
│  │  └─ maybe_post_internal_charge_je()
│  │
│  ├─ ledger.py                       # Budget Control Entry CRUD
│  │  ├─ post_entry()                 # Create BCE
│  │  ├─ get_reserved_total()
│  │  ├─ get_availability()
│  │  └─ check_budget_available()
│  │
│  ├─ service.py                      # High-level budget API
│  │  ├─ resolve_dims()
│  │  ├─ check_budget_available()
│  │  └─ record_reclass()
│  │
│  └─ utils.py                        # Settings & helpers
│
├─ imogi_finance/doctype/
│  ├─ internal_charge_request/
│  │  ├─ internal_charge_request.py   # IC approval logic
│  │  │  ├─ before_workflow_action()  # Approval enforcement
│  │  │  ├─ _validate_approve_permission()
│  │  │  ├─ _populate_line_routes()
│  │  │  ├─ _sync_status()
│  │  │  └─ _sync_workflow_state()
│  │  │
│  │  └─ internal_charge_request.json
│  │
│  ├─ internal_charge_line/
│  │  └─ internal_charge_line.json    # IC line fields
│  │
│  ├─ budget_control_entry/
│  │  ├─ budget_control_entry.py      # BCE validation
│  │  └─ budget_control_entry.json
│  │
│  └─ budget_control_settings/
│     ├─ budget_control_settings.py
│     └─ budget_control_settings.json # Feature toggles
│
└─ events/
   ├─ internal_charge_request.py      # IC event hooks
   └─ purchase_invoice.py              # PI event hooks
      ├─ consume_budget_for_purchase_invoice()
      └─ maybe_post_internal_charge_je()
```

---

## 8. Testing Recommendations

### 8.1 Existing Tests
- ✅ `test_internal_charge_workflow.py` - Workflow & approval
- ✅ `test_budget_control.py` - Budget lock & consumption

### 8.2 Additional Tests Needed

```python
# test_internal_charge_budget_integration.py

def test_ic_allocation_slices_generation():
    """Test allocation slices correctly split amounts per IC lines."""
    pass

def test_budget_control_entry_created_for_ic():
    """Test BCE created with correct ref_doctype/ref_name for IC."""
    pass

def test_ic_approval_without_budget_allows_overrun():
    """Test IC can be approved even with insufficient budget (current behavior)."""
    pass

def test_ic_approval_with_budget_validation_blocks():
    """Test IC approval blocked when budget insufficient (after improvement)."""
    pass

def test_ic_budget_entries_queryable():
    """Test BCE for IC can be queried via ER reference."""
    pass

def test_je_posting_modes():
    """Test JE posting on IC/ER/PI based on settings."""
    pass
```

---

## 9. Implementation Priority

### Phase 1 (HIGH): Budget Validation on IC Approval
- [ ] Add `internal_charge_validate_budget_on_approval` to settings
- [ ] Implement `_validate_budget_for_lines()` in IC approval
- [ ] Add tests for budget validation
- [ ] Update documentation

**Timeline:** 1-2 days  
**Impact:** Prevents IC approval failures downstream

### Phase 2 (MEDIUM): Flexible JE Posting Modes
- [ ] Expand `internal_charge_posting_mode` options
- [ ] Implement JE posting on IC/ER approval
- [ ] Refactor `maybe_post_internal_charge_je` to support multiple triggers
- [ ] Add tests

**Timeline:** 2-3 days  
**Impact:** More flexible accounting workflow

### Phase 3 (MEDIUM): IC Allocation Tracking
- [ ] Add `IC_ALLOCATION` entry type
- [ ] Implement `_record_ic_allocation_entries()`
- [ ] Add setting toggle
- [ ] Update BCE validation
- [ ] Add tests

**Timeline:** 1-2 days  
**Impact:** Better audit trail for IC approvals

### Phase 4 (LOW): IC Allocation Report
- [ ] Create report doctype
- [ ] Implement SQL query
- [ ] Add filters (date, cost center, status)
- [ ] Add charts/visualizations

**Timeline:** 2-3 days  
**Impact:** Better visibility and analysis

---

## 10. Conclusion

**Key Takeaways:**
1. ✅ Internal Charge **SUDAH** connected ke Budget Control Entry
2. ✅ Mechanism: allocation_slices → BCE per (cost_center × account)
3. ⚠️ Main gap: No budget validation during IC approval
4. 🎯 Priority improvement: Add budget check before IC approval

**Next Steps:**
1. Review recommendations dengan team
2. Prioritize improvements based on business needs
3. Implement Phase 1 (budget validation) first
4. Add comprehensive tests
5. Update user documentation

---

**Document Version:** 1.0  
**Last Updated:** January 16, 2026  
**Reviewed By:** [To be filled]
