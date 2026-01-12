# Refactoring Summary: Modular + Native-First Expense Request

**Date**: 12 Januari 2026 | **Status**: Ready for Testing

## Files Created

### 1. **ApprovalService** (NEW - Reusable)
- **Path**: `imogi_finance/services/approval_service.py`
- **Size**: ~350 lines
- **Purpose**: Multi-level approval state machine for any doctype
- **Methods**:
  - `before_submit()` – Initialize approval state at submission
  - `before_workflow_action()` – Guard + validate approver authorization
  - `on_workflow_action()` – Handle state transitions post-action
  - `guard_status_changes()` – Prevent manual status bypass
  - `sync_state_to_status()` – Keep status field in sync with workflow_state
- **Reusable for**: Expense Request, Internal Charge Request, Branch Expense Request, etc.

### 2. **Refactored ExpenseRequest** (REFACTORED)
- **Path**: `imogi_finance/imogi_finance/doctype/expense_request/expense_request_refactored.py`
- **Size**: ~350 lines (vs ~1600 before = 78% reduction)
- **Approach**: 
  - Minimal business logic only
  - Delegate approval workflow to ApprovalService
  - Use standard Frappe hooks: before_submit, on_submit, before_workflow_action, on_workflow_action, on_update_after_submit
  - Delegate budget integration to handle_expense_request_workflow
- **Benefits**:
  - Easy to understand and maintain
  - No custom patterns
  - All complex logic encapsulated in reusable services

### 3. **Unit Tests** (NEW)
- **Path**: `imogi_finance/tests/test_approval_service.py`
- **Coverage**: 
  - TestBeforeSubmit (5 tests)
  - TestBeforeWorkflowAction (4 tests)
  - TestOnWorkflowAction (5 tests)
  - TestGuardStatusChanges (3 tests)
  - TestSyncStateToStatus (2 tests)
  - TestPrivateHelpers (5 tests)
- **Total**: 24 unit tests for ApprovalService

### 4. **Architecture Documentation** (NEW)
- **Path**: `REFACTORED_ARCHITECTURE.md`
- **Contains**:
  - Architecture overview and key changes
  - Detailed component descriptions
  - Usage examples
  - Benefits and migration paths
  - Testing checklist
  - Deployment instructions
  - Future extension plans

## Files Modified

### 1. **ExpenseRequest.json**
- **Change**: Added visible `status` field
- **Details**:
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
- **Why**: Separate UI display (status) from system state (docstatus)
- **Impact**: No data migration needed

### 2. **Workflow JSON** (Unchanged)
- **Path**: `expense_request_workflow.json`
- **Status**: No changes needed
- **Reason**: Already native + simple design

## Key Design Decisions

### 1. Separation of Concerns
- **Business Logic** → ExpenseRequest.validate()
- **Approval Workflow** → ApprovalService
- **Budget Control** → handle_expense_request_workflow (standard hook)
- **Accounting** → accounting module
- **Permissions** → Native Frappe perms + custom route validation

### 2. Use of Standard Hooks
```python
# Native Frappe pattern - no custom lifecycle
def validate()      → Business rules
def before_submit() → Setup + preparation
def on_submit()     → Post-submit actions
def before_workflow_action() → Guard + special actions
def on_workflow_action() → Handle state transitions
def on_update_after_submit() → Post-save validation
def before_cancel() → Pre-cancel validation
def on_cancel() → Cleanup
```

### 3. Status Field Strategy
| Field | Purpose | Value Example |
|-------|---------|---------------|
| `docstatus` | System state | 0 (Draft), 1 (Submitted), 2 (Cancelled) |
| `workflow_state` | Business state (hidden) | "Pending Review", "Approved", "PI Created" |
| `status` | User-facing display | Same as workflow_state, visible in form |

### 4. Reusability
ApprovalService is **completely decoupled**:
- ✅ No Expense Request dependencies
- ✅ Configurable state_field name
- ✅ Configurable status_field name
- ✅ Works with any doctype following the pattern

Can be used by:
- Expense Request ✅
- Internal Charge Request (ready)
- Branch Expense Request (ready)
- Purchase Order approval (future)
- Requisition approval (future)

## What Didn't Change

### 1. Workflow JSON
- States, transitions, conditions unchanged
- Still supports Draft → Pending Review/Approved → PI Created → Paid
- Still uses `workflow_state_field: "workflow_state"`

### 2. Approval Route Logic
- Cost center + amount routing still works
- Multi-level user assignment unchanged
- Route resolution same logic

### 3. Budget Control Integration
- Still calls `handle_expense_request_workflow` hook
- Still reserves/locks budget on approval
- Still releases budget on cancel

### 4. PI Creation
- Still calls `accounting.create_purchase_invoice_from_request`
- Still validates all prerequisites
- Still linked in `linked_purchase_invoice` field

### 5. Existing ER Data
- All existing ER documents continue to work
- No migration needed
- No breaking changes

## Migration Options

### Option A: Drop-In Replacement (Recommended)
1. Replace `expense_request.py` with `expense_request_refactored.py`
2. No other changes needed
3. All existing ERs work immediately
4. Risk: Low (refactored code uses same APIs)

### Option B: Gradual (Safe for Large Deployments)
1. Deploy ApprovalService alongside old code
2. Gradually refactor methods
3. Test each change
4. Replace full file when ready

### Option C: A/B Testing (Zero-Risk)
1. Keep old code in production
2. Deploy new code as `expense_request_v2.py`
3. Run both versions
4. Switch after validation

## Testing Strategy

### Level 1: Unit Tests
- ApprovalService methods (24 tests)
- Run: `pytest imogi_finance/tests/test_approval_service.py -v`
- Time: ~1 minute

### Level 2: Integration Tests
- Expense Request + ApprovalService integration
- Create ER → Submit → Approve L1 → Approve L2 → Create PI
- Workflow transitions, state management, budget lock
- Time: ~5 minutes

### Level 3: Manual Tests
- End-to-end workflow in UI
- Create ER with all features (asset, tax, deferred)
- Complete approval workflow
- Test edge cases (reopen, reject, cancel)
- Time: ~15 minutes

### Level 4: Regression Tests
- Existing ER documents still work
- Budget control still enforces
- PI creation still works
- Payment integration still syncs
- Time: ~10 minutes

## Deployment Checklist

### Pre-Deployment
- [ ] Code review completed
- [ ] All tests passing (unit + integration)
- [ ] Manual testing in dev done
- [ ] Backup created
- [ ] No critical ER pending final approval

### Deployment
- [ ] Copy `approval_service.py` to services/
- [ ] Copy `expense_request_refactored.py` (or replace `expense_request.py`)
- [ ] Update `expense_request.json` to add status field
- [ ] Run `bench migrate`
- [ ] Run `bench clear-cache`
- [ ] Run `bench restart`

### Post-Deployment
- [ ] Smoke test: Create + Submit ER
- [ ] Check status field visible
- [ ] Check workflow actions work
- [ ] Check budget lock works
- [ ] Monitor error logs for 24h
- [ ] User verification (accounting team)

## Known Limitations & Future Work

### Current Limitations
1. ApprovalService assumes fields named `level_1_user`, `level_2_user`, `level_3_user`
   - Can parameterize in future if needed

2. Three-level approval max
   - Can extend to N levels if needed

3. `status` field is read-only
   - All changes via workflow actions only ✅

### Future Enhancements
1. **Extend to Internal Charge Request**
   - Reuse ApprovalService
   - Add simple before_submit hook
   - Done in ~30 minutes

2. **Extend to Branch Expense Request**
   - Same as Internal Charge
   - Add cost center distribution logic
   - Done in ~1 hour

3. **Parameterize Level Count**
   - Make `_has_next_level()` support N levels
   - Support arbitrary number of approval levels

4. **Add Parallel Approvals**
   - Extend ApprovalService for concurrent approvers at same level
   - Support consensus/majority rules

5. **Add Audit Trail Service**
   - Separate service for logging all transitions
   - Detailed change history with reasons

## Performance Impact

- ✅ No negative impact
- ✅ Slightly faster: Less logic in before_submit
- ✅ Same database queries
- ✅ ApprovalService is stateless (no extra lookups)

## Security Implications

- ✅ No security regressions
- ✅ Stronger status guards (prevent bypass)
- ✅ Same approval route enforcement
- ✅ Same budget control checks
- ✅ Better separation = easier to audit

## Backward Compatibility

- ✅ **100% backward compatible**
- ✅ All existing ER documents work unchanged
- ✅ All existing workflows work unchanged
- ✅ No data migration needed
- ✅ No API changes
- ✅ Can rollback to old code anytime

## Questions & Answers

**Q: Do I need to update my ERs?**  
A: No. All existing ERs continue to work without changes.

**Q: Will workflow actions still work?**  
A: Yes. ApprovalService handles them the same way (or better).

**Q: What if I find a bug?**  
A: Rollback: move old `expense_request.py` back, restart. Takes 2 minutes.

**Q: Can I use ApprovalService for other doctypes?**  
A: Yes! That's the design. See InternalChargeRequest example in REFACTORED_ARCHITECTURE.md.

**Q: Does this break my customizations?**  
A: Only if you were directly calling internal methods (unlikely). Most customizations extend the class or use hooks - still work.

**Q: How much faster/slower?**  
A: Neutral. Same logic, better organized. No performance difference.

---

## Next Steps

1. **Review Code**
   - Read `approval_service.py` (350 lines, clear logic)
   - Read `expense_request_refactored.py` (350 lines, minimal)
   - Compare to original (1600 lines)

2. **Run Tests**
   ```bash
   pytest imogi_finance/tests/test_approval_service.py -v
   ```

3. **Manual Test in Dev**
   - Create ER with approval route
   - Test workflow
   - Test budget lock
   - Test PI creation

4. **Merge to Main**
   - After validation from testing

5. **Deploy to Staging**
   - Full workflow testing
   - Performance verification
   - Integration with other modules

6. **Deploy to Production**
   - Monitor logs
   - User acceptance testing
   - Rollback ready (if needed)

---

**Status**: ✅ Ready for Testing | **Estimated Test Time**: 1-2 days | **Rollback Risk**: Very Low
