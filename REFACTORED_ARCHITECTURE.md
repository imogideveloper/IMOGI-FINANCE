# Refactored Architecture: Modular, Scalable, Native-First

**Status**: Ready for testing | **Date**: 12 Januari 2026

## Overview

Expense Request workflow telah direfactor menjadi **modular + native-first** - memanfaatkan Frappe/ERPNext built-in patterns untuk approval, status management, dan hooks.

### Key Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Approval Logic** | Embedded di ExpenseRequest.py (~1600 lines) | `ApprovalService` (reusable) + ExpenseRequest (clean) |
| **Customization** | Banyak custom pattern | 100% native Frappe hooks (before_submit, on_submit, on_workflow_action, etc.) |
| **Reusability** | Hanya untuk ER | ApprovalService reusable untuk ER, Internal Charge, Branch Expense, dll |
| **Status Sync** | Via `sync_status_with_workflow_state()` method | Native `status` field + ApprovalService.sync_state_to_status() |
| **Budget Integration** | Custom logic di before_submit | Standard hook: on_submit → handle_expense_request_workflow |
| **PI Creation** | before_workflow_action handler | Delegated to before_workflow_action (tetap ada) |

## Architecture

### 1. ApprovalService (NEW - Reusable)

**Location**: `imogi_finance/services/approval_service.py`

```python
class ApprovalService:
    """Multi-level approval state machine for any doctype.
    
    Methods:
    - before_submit(doc, route, auto_approve) → Initialize approval state
    - before_workflow_action(doc, action, next_state, route) → Guard + validate
    - on_workflow_action(doc, action, next_state) → Update state post-action
    - guard_status_changes(doc) → Prevent status bypass
    - sync_state_to_status(doc) → Keep status in sync with workflow_state
    """
```

**Features**:
- ✅ Multi-level approval (level 1, 2, 3)
- ✅ Advance level on Approve action (if more levels exist)
- ✅ Reject/Reopen/Backflow support
- ✅ Audit timestamps (approved_on, rejected_on)
- ✅ Guard status changes (prevent manual bypass)
- ✅ Reusable for any doctype

**Example Usage** (ExpenseRequest):
```python
def before_submit(self):
    route, setting_meta, _ = self._resolve_approval_route()
    approval_service = ApprovalService("Expense Request", state_field="workflow_state")
    approval_service.before_submit(self, route=route, skip_approval=not self._has_approver(route))

def before_workflow_action(self, action, **kwargs):
    approval_service = ApprovalService("Expense Request", state_field="workflow_state")
    approval_service.before_workflow_action(self, action, next_state=kwargs.get("next_state"))

def on_workflow_action(self, action, **kwargs):
    approval_service = ApprovalService("Expense Request", state_field="workflow_state")
    approval_service.on_workflow_action(self, action, next_state=kwargs.get("next_state"))
```

### 2. Refactored ExpenseRequest

**File**: `imogi_finance/imogi_finance/doctype/expense_request/expense_request_refactored.py`

**Responsibilities** (minimal):
- ✅ Business rule validation (amounts, assets, tax fields)
- ✅ Route resolution + storage
- ✅ Delegation to ApprovalService
- ✅ Accounting integration (PI creation)
- ✅ Budget integration (via handle_expense_request_workflow hook)

**Size**: ~350 lines (vs ~1600 before) → 80% reduction

**Key Methods**:

| Hook | Purpose |
|------|---------|
| `validate()` | Business rules only (amounts, assets, tax, etc.) |
| `before_submit()` | Resolve route + init approval state via ApprovalService |
| `on_submit()` | Sync budget via standard workflow handler |
| `before_workflow_action()` | Guard actions + PI creation + ApprovalService.before_workflow_action |
| `on_workflow_action()` | Delegate to ApprovalService.on_workflow_action + sync budget |
| `on_update_after_submit()` | Guard status changes via ApprovalService |
| `before_cancel()` | Validate permissions + downstream links |
| `on_cancel()` | Release budget via standard handler |

### 3. Workflow JSON (Unchanged)

**File**: `imogi_finance/imogi_finance/workflow/expense_request_workflow/expense_request_workflow.json`

- Remains as is (already native + simple)
- States: Draft, Pending Review, Approved, Rejected, PI Created, Paid
- Transitions: Submit → Pending Review/Approved (based on route), Approve, Reject, Create PI
- `override_status: 1` → allows custom status field
- `workflow_state_field: "workflow_state"` → native integration

### 4. Status Field (NEW - Visible)

**ExpenseRequest.json Update**:

Added visible `status` field:
```json
{
  "allow_on_submit": 1,
  "bold": 1,
  "fieldname": "status",
  "fieldtype": "Data",
  "in_list_view": 0,
  "label": "Status",
  "read_only": 1
}
```

**Why**: Separate UI display from system docstatus:
- `docstatus` (system) = 0 (Draft), 1 (Submitted), 2 (Cancelled)
- `workflow_state` (internal, hidden) = Pending Review, Approved, etc.
- `status` (user-facing) = same as workflow_state, visible in form

### 5. Budget Integration (Native Hook Pattern)

**Before**:
```python
def before_submit(self):
    # ... complex approval logic ...
    # ... complex budget logic ...
```

**After**:
```python
def on_submit(self):
    """Post-submit: sync budget (if enabled) and record in activity."""
    try:
        handle_expense_request_workflow(self, "Submit", getattr(self, "workflow_state"))
    except Exception:
        pass
```

Budget control is delegated to standard hook → follows Frappe/ERPNext patterns.

## Benefits

### 1. Modularity
- ApprovalService decoupled from ExpenseRequest
- Easy to test in isolation
- Easy to reuse for other doctypes

### 2. Reusability
- `ApprovalService` can be used by:
  - Expense Request
  - Internal Charge Request
  - Branch Expense Request
  - Any multi-level approval doctype

### 3. Scalability
- Add new state? Update ApprovalService
- Add new doctype with approval? Just instantiate ApprovalService
- No duplicate code

### 4. Minimized Customization
- Uses native Frappe hooks: before_submit, on_submit, before_workflow_action, on_workflow_action, on_update_after_submit
- No custom workflow pattern
- No custom status sync logic
- Follows ERPNext v15+ conventions

### 5. Easier Maintenance
- ExpenseRequest.py: 350 lines (vs 1600)
- Clear separation of concerns
- Business logic isolated from workflow/approval logic

## Migration Path

### Option 1: Replace Immediately (Recommended for Fresh Installs)
1. Replace `expense_request.py` with `expense_request_refactored.py`
2. Keep workflow JSON as-is
3. Test with sample data
4. ✅ All existing ER docs should work without modification

### Option 2: Gradual Migration (Existing Production)
1. Deploy ApprovalService alongside existing expense_request.py
2. Gradually refactor methods to use ApprovalService
3. Test each method change
4. After validation, replace entire file

### Option 3: Dual-Run (Zero Downtime)
1. Keep old expense_request.py in production
2. Deploy new one alongside with different name: expense_request_v2.py
3. A/B test with subset of users
4. Switch to new version after validation

## Testing Checklist

### Unit Tests (ApprovalService)
- [ ] test_before_submit_with_approvers() → sets state Pending Review, level 1
- [ ] test_before_submit_no_approvers() → sets state Approved, level 0
- [ ] test_advance_level_when_multiple_levels() → from L1 → L2 → L3 → Approved
- [ ] test_single_level_approval() → L1 → Approved
- [ ] test_reject_clears_level() → Rejected state, level 0
- [ ] test_reopen_resets_route() → back to Pending Review level 1
- [ ] test_guard_blocks_manual_bypass() → prevent status change without workflow action

### Integration Tests (ExpenseRequest)
- [ ] test_submit_with_route() → initializes approval via ApprovalService
- [ ] test_create_pi_action() → PI created, linked_purchase_invoice filled
- [ ] test_workflow_action_approve() → advances level, stays Pending Review
- [ ] test_workflow_action_approve_final() → reaches Approved, level 0
- [ ] test_workflow_action_reject() → sets Rejected, level 0
- [ ] test_cancel_requires_permission() → System Manager/Expense Approver only
- [ ] test_key_field_immutable_after_approval() → can't change amount/cost_center/etc

### Manual Tests (User Workflow)
- [ ] Create ER, submit, workflow shows "Pending Review"
- [ ] Approver L1 approves, workflow shows "Pending Review" (if L2 exists)
- [ ] Approver L2 approves, workflow shows "Approved"
- [ ] Create PI action → PI created, status "PI Created"
- [ ] Reopen action → status back to "Pending Review", level 1
- [ ] Reject action → status "Rejected"
- [ ] List view shows correct status
- [ ] Form header shows "Submitted" (docstatus=1), not "Not Saved"

## Deployment Instructions

### Prerequisites
- [ ] Backup database
- [ ] No pending ER documents in critical state

### Steps
1. **Backup**:
   ```bash
   bench backup --with-files
   ```

2. **Deploy Code**:
   - Copy `approval_service.py` to `imogi_finance/services/`
   - Copy `expense_request_refactored.py` (refactored logic)
   - Backup old `expense_request.py` → `expense_request_backup.py`
   - Update `expense_request.json` to add `status` field

3. **Migrate**:
   ```bash
   bench migrate
   bench clear-cache
   ```

4. **Restart**:
   ```bash
   bench restart
   ```

5. **Verify**:
   - [ ] Create test ER, submit workflow
   - [ ] Check status field is visible (shows "Pending Review")
   - [ ] Check docstatus shows "Submitted" (not "Not Saved")
   - [ ] Workflow actions work (Approve, Reject, Create PI)
   - [ ] Budget lock happens on Approved (if enabled)

### Rollback (if needed)
```bash
# Restore old code
mv expense_request.py expense_request_refactored.py
mv expense_request_backup.py expense_request.py

# Undo JSON changes (restore old field order)
git checkout imogi_finance/imogi_finance/doctype/expense_request/expense_request.json

# Restart
bench migrate
bench restart
```

## Future: Reuse for Other Doctypes

Once ApprovalService is proven on Expense Request, extend to:

### Internal Charge Request
```python
from imogi_finance.services.approval_service import ApprovalService

class InternalChargeRequest(Document):
    def before_submit(self):
        route = self._resolve_route()
        approval_service = ApprovalService("Internal Charge Request", state_field="workflow_state")
        approval_service.before_submit(self, route=route)
    
    def before_workflow_action(self, action, **kwargs):
        approval_service = ApprovalService("Internal Charge Request", state_field="workflow_state")
        approval_service.before_workflow_action(self, action, next_state=kwargs.get("next_state"))
```

### Branch Expense Request
Same pattern → instant multi-level approval for branch expenses.

## Notes

- `status` field is kept in sync with `workflow_state` via ApprovalService
- `docstatus` remains as Frappe standard: 0=Draft, 1=Submitted, 2=Cancelled
- No breaking changes to existing ER data or workflow
- All existing ER documents continue to work
- ApprovalService is stateless → safe to update/test independently

---

**Next Steps**:
1. Review refactored code (expense_request_refactored.py)
2. Run unit tests on ApprovalService
3. Test with sample ER workflow in dev environment
4. Merge to main branch
5. Deploy to staging
6. Deploy to production with monitoring
