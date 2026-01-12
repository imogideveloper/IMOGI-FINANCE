# Deployment Checklist: Modular Expense Request Refactoring

**Date**: 12 Januari 2026 | **Target**: Production Deployment | **Risk Level**: 🟢 Low

---

## 📋 Pre-Deployment Phase (Review & Test)

### [ ] Code Review
- [ ] Reviewed `imogi_finance/services/approval_service.py` (350 lines)
  - [ ] Understood `before_submit()` logic
  - [ ] Understood `before_workflow_action()` logic
  - [ ] Understood `on_workflow_action()` logic
  - [ ] Understood `guard_status_changes()` logic
  - [ ] Understood state machine transitions
  
- [ ] Reviewed `expense_request_refactored.py` (350 lines)
  - [ ] Understood delegation pattern
  - [ ] Verified no business logic changes
  - [ ] Verified all hooks present (before_submit, on_submit, etc.)
  - [ ] Verified route resolution still works
  - [ ] Verified budget integration still works

- [ ] Reviewed test file `test_approval_service.py`
  - [ ] Understood test coverage (24 tests)
  - [ ] Verified all scenarios covered
  - [ ] No gaps in testing

### [ ] Documentation Review
- [ ] Read [QUICK_REFERENCE.md](QUICK_REFERENCE.md) (5 min)
- [ ] Read [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) (15 min)
- [ ] Read [REFACTORED_ARCHITECTURE.md](REFACTORED_ARCHITECTURE.md) (30 min)
- [ ] Confirmed understanding of architecture
- [ ] Confirmed understanding of backward compatibility
- [ ] Confirmed understanding of rollback procedure

### [ ] Environment Setup
- [ ] Development environment ready
- [ ] Database backup available
- [ ] Git branch ready (if needed)
- [ ] Deployment user has necessary permissions
- [ ] Monitoring tools configured (if applicable)

### [ ] Unit Testing
```bash
# Run all ApprovalService unit tests
pytest imogi_finance/tests/test_approval_service.py -v
```
- [ ] All 24 tests passing
- [ ] No errors or warnings
- [ ] Execution time acceptable

### [ ] Manual Testing (Dev Environment)

#### Test Case 1: Create & Submit ER
- [ ] Create new Expense Request
- [ ] Fill required fields (Cost Center, Supplier, Items)
- [ ] Save as Draft
- [ ] Submit for approval
- [ ] **Verify**:
  - [ ] Form shows "Submitted" (not "Not Saved")
  - [ ] Status field visible and shows correct value
  - [ ] workflow_state set correctly
  - [ ] current_approval_level = 1 (if approvers configured)
  - [ ] No errors in browser console

#### Test Case 2: Workflow - Approve (Multi-Level)
- [ ] Go to ER in "Pending Review"
- [ ] Click "Approve" action
- [ ] If L2 exists:
  - [ ] Status stays "Pending Review"
  - [ ] current_approval_level advances to 2
  - [ ] If L3 exists: Repeat for L3
- [ ] After final approval:
  - [ ] Status changes to "Approved"
  - [ ] current_approval_level = 0
  - [ ] approved_on timestamp set
  - [ ] No errors

#### Test Case 3: Create PI
- [ ] Approved ER ready
- [ ] Click "Create PI" action
- [ ] **Verify**:
  - [ ] Purchase Invoice created
  - [ ] linked_purchase_invoice field populated
  - [ ] Status changes to "PI Created"
  - [ ] PI is linked correctly to ER
  - [ ] No errors

#### Test Case 4: Budget Lock (if enabled)
- [ ] Approved ER ready (or at configured state)
- [ ] Check Budget Control settings
- [ ] **Verify**:
  - [ ] Budget entries created
  - [ ] Budget marked as "Locked"
  - [ ] Budget amount matches ER total
  - [ ] No errors

#### Test Case 5: Workflow - Reject
- [ ] Another ER in "Pending Review"
- [ ] Click "Reject" action
- [ ] **Verify**:
  - [ ] Status changes to "Rejected"
  - [ ] current_approval_level = 0
  - [ ] rejected_on timestamp set
  - [ ] Cannot approve after reject
  - [ ] Can reopen if permitted
  - [ ] No errors

#### Test Case 6: Reopen
- [ ] Rejected or Approved ER
- [ ] Click "Reopen" action (if permitted)
- [ ] **Verify**:
  - [ ] Status changes back to "Pending Review"
  - [ ] current_approval_level reset to 1
  - [ ] Downstream links cleared
  - [ ] Can continue approval cycle
  - [ ] No errors

#### Test Case 7: Cancel
- [ ] Submitted ER (any status except final)
- [ ] Check permissions (System Manager required)
- [ ] Cancel the ER
- [ ] **Verify**:
  - [ ] Status changes to "Cancelled"
  - [ ] docstatus = 2
  - [ ] Budget reservations released (if any)
  - [ ] No errors in logs

#### Test Case 8: Existing ER Compatibility
- [ ] Pick existing ER from production backup
- [ ] Verify it loads without errors
- [ ] Verify workflow state correct
- [ ] Verify can still interact with it (if not final state)
- [ ] No compatibility issues

#### Test Case 9: Edge Cases
- [ ] Single-level approval (only L1 configured)
  - [ ] L1 approves → immediately "Approved"
- [ ] No approval required
  - [ ] Submit → auto "Approved"
- [ ] Key field change after submit
  - [ ] Change amount → should trigger re-approval
  - [ ] Should reset to "Pending Review" L1
  
#### Test Case 10: Status Field Visibility
- [ ] Form view: Status field visible and read-only
- [ ] List view: Can see status column
- [ ] Form header: Shows "Submitted" for submitted docs
- [ ] No "Not Saved" badge for unchanged docs

### [ ] Integration Testing
- [ ] Created ER → Budget control integration works
- [ ] Approved ER → Payment Entry integration works
- [ ] PI Created ER → No duplicate PI creation
- [ ] Cancelled ER → Budget released
- [ ] No errors in integration logs

### [ ] Performance Testing
- [ ] Create 10 ERs, approve workflow
- [ ] Measure time: < 2 seconds per action
- [ ] No database query increase
- [ ] No memory leak observed
- [ ] Logs show no performance warnings

### [ ] Regression Testing
- [ ] Test existing ER with old data
- [ ] Test workflow with complex routes
- [ ] Test budget control integration
- [ ] Test payment entry integration
- [ ] Test PI creation
- [ ] No regressions found

### [ ] Sign-Offs Required
- [ ] Technical Lead approved code
- [ ] QA approved test results
- [ ] Accounting team reviewed (for workflow implications)
- [ ] DevOps approved deployment plan

---

## 🚀 Deployment Phase

### [ ] Pre-Deployment (1 hour before)

#### Backup
```bash
# Full database backup
bench backup --with-files
```
- [ ] Backup started
- [ ] Backup completed successfully
- [ ] Backup verified (can be restored)
- [ ] Backup location documented

#### Communication
- [ ] Informed users about maintenance window
- [ ] Notified stakeholders of deployment time
- [ ] Documented rollback contact
- [ ] All parties acknowledged

#### Preparation
- [ ] Deployment user logged in
- [ ] Terminal ready
- [ ] Monitoring dashboard open
- [ ] Error logs tail running

### [ ] Execute Deployment (30 minutes)

#### Step 1: Copy Files (5 min)
```bash
# Navigate to repository
cd imogi_finance

# Copy new ApprovalService
cp imogi_finance/services/approval_service.py imogi_finance/services/

# Backup old ExpenseRequest
cp imogi_finance/imogi_finance/doctype/expense_request/expense_request.py \
   imogi_finance/imogi_finance/doctype/expense_request/expense_request_backup_$(date +%Y%m%d_%H%M%S).py

# Copy refactored ExpenseRequest
cp imogi_finance/imogi_finance/doctype/expense_request/expense_request_refactored.py \
   imogi_finance/imogi_finance/doctype/expense_request/expense_request.py
```
- [ ] ApprovalService copied
- [ ] Old ExpenseRequest backed up
- [ ] New ExpenseRequest in place
- [ ] All files verified

#### Step 2: Update Schema (5 min)
```bash
# Already updated in expense_request.json (status field added)
# No additional schema changes needed
bench migrate
```
- [ ] Migration started
- [ ] Migration completed successfully
- [ ] No migration errors

#### Step 3: Clear Cache (2 min)
```bash
bench clear-cache
```
- [ ] Cache cleared successfully
- [ ] No cache errors

#### Step 4: Restart (5 min)
```bash
bench restart
```
- [ ] Services restarting...
- [ ] All services restarted
- [ ] Services responding
- [ ] No startup errors

#### Step 5: Smoke Tests (5 min)

**Test 1: Access Application**
- [ ] Can access Frappe
- [ ] Can access Expense Request list
- [ ] List loads without errors

**Test 2: Create & Submit**
- [ ] Create test ER
- [ ] Save as Draft
- [ ] Submit
- [ ] **Verify**: Shows "Submitted", not "Not Saved"

**Test 3: Check Status**
- [ ] Status field visible
- [ ] Shows "Pending Review" (if approvers configured)
- [ ] Shows "Approved" (if no approvers)

**Test 4: Workflow Action**
- [ ] Click "Approve" (if in Pending Review)
- [ ] **Verify**: State transitions correctly
- [ ] No errors

**Test 5: Error Logs**
```bash
tail -100 logs/bench.log | grep -i error
```
- [ ] No new errors
- [ ] No warnings related to ExpenseRequest
- [ ] Logs clean

### [ ] Post-Deployment (1 hour monitoring)

#### Immediate Monitoring (First 5 min)
- [ ] Application responding normally
- [ ] No error spikes
- [ ] Database queries normal
- [ ] CPU/Memory usage normal

#### Extended Monitoring (30 min)
```bash
# Watch logs in real-time
tail -f logs/bench.log | grep -i expense

# Check for errors periodically
frappe@host:/home/frappe/frappe-bench$ bench console
frappe> frappe.get_last_log_errors(50)
```
- [ ] No new errors appearing
- [ ] No performance degradation
- [ ] No user complaints

#### Full Verification (1 hour)
- [ ] Test complete workflow: Create → Approve → PI Create
- [ ] Test with real data (if safe)
- [ ] Verify budget integration still works
- [ ] Verify payment integration still works
- [ ] Verify existing ERs still accessible

#### Announcement to Users
- [ ] Sent success notification
- [ ] Explained what changed (status field now visible)
- [ ] Explained no action required from users
- [ ] Provided support contact if issues

---

## 🔧 If Issues Occur

### [ ] Issue: Application Won't Start
**Symptoms**: Frappe won't start after restart
**Fix**: 
```bash
# Rollback immediately
cd imogi_finance
cp imogi_finance/imogi_finance/doctype/expense_request/expense_request_backup_*.py \
   imogi_finance/imogi_finance/doctype/expense_request/expense_request.py
bench migrate
bench restart
```
- [ ] Rollback completed
- [ ] Application started
- [ ] Users notified

### [ ] Issue: Workflow Doesn't Work
**Symptoms**: Approve/Reject actions don't transition state
**Fix**: Check logs for ApprovalService errors
```bash
tail -100 logs/bench.log | grep -i approval
```
- [ ] Root cause identified
- [ ] If bug: Create issue, rollback temporarily
- [ ] If configuration: Fix config, restart

### [ ] Issue: Status Field Invisible
**Symptoms**: Status field doesn't show in form
**Fix**:
```bash
# Ensure schema migrated
bench migrate --rebuild-fresh
bench clear-cache
bench restart
```
- [ ] Schema migrated
- [ ] Cache cleared
- [ ] Status field visible

### [ ] Issue: Performance Degradation
**Symptoms**: Slow ER load/save times
**Fix**: Check for N+1 queries or missing indexes
```bash
# Check bench console for slow queries
frappe> frappe.db.set_value("User", frappe.session.user, "debug", 1)
# Perform action that's slow
# Check logs for SQL timing
```
- [ ] Slow queries identified
- [ ] Indexes added if needed
- [ ] Performance restored

### [ ] Rollback Decision
**If any critical issue that can't be fixed quickly:**
```bash
# Complete rollback
cd imogi_finance
cp imogi_finance/imogi_finance/doctype/expense_request/expense_request_backup_*.py \
   imogi_finance/imogi_finance/doctype/expense_request/expense_request.py
# Restore old workflow JSON if modified (it shouldn't be)
git checkout imogi_finance/imogi_finance/doctype/expense_request/expense_request.json
bench migrate
bench restart
```
- [ ] Rollback completed (2-3 minutes)
- [ ] Application back to normal
- [ ] Users notified
- [ ] Post-mortem scheduled

---

## ✅ Post-Deployment Phase (1-7 days)

### [ ] Day 1: Intensive Monitoring
- [ ] Check error logs first thing in morning
- [ ] Test complete ER workflow (create → approve → pay)
- [ ] Verify budget control working
- [ ] Verify payment integration working
- [ ] Get feedback from users

### [ ] Day 2-3: Normal Operations
- [ ] Monitor logs daily
- [ ] Check no complaints from users
- [ ] Verify existing ERs still processable
- [ ] Test edge cases with real data

### [ ] Day 4-7: Validation
- [ ] Verify all ER workflows functioning
- [ ] Confirm budget control working
- [ ] Confirm payment flows working
- [ ] Get sign-off from accounting team

### [ ] Final Sign-Off
- [ ] Technical Lead: Code working as expected
- [ ] QA: No regressions found
- [ ] DevOps: Infrastructure stable
- [ ] Business: Workflow correct

### [ ] Cleanup
- [ ] Remove backup files (keep archived copy)
- [ ] Document deployment in change log
- [ ] Update runbooks if needed
- [ ] Mark issue as deployed

---

## 📊 Deployment Metrics

| Metric | Expected | Actual |
|--------|----------|--------|
| Deployment time | 30 min | ___ min |
| Tests passed | 24/24 | ___/24 |
| Manual tests passed | 10/10 | ___/10 |
| Rollback time (if needed) | < 5 min | ___ min |
| Issues found | 0 | ___ |

---

## 🎯 Success Criteria (All Must Pass)

- [ ] All files deployed correctly
- [ ] No startup errors
- [ ] Can create + submit ER (shows "Submitted")
- [ ] Status field visible in form
- [ ] Workflow actions work (Approve, Reject, Create PI)
- [ ] Budget locks on approval (if enabled)
- [ ] PI created successfully
- [ ] Existing ERs still accessible
- [ ] No new errors in logs (after 1 hour)
- [ ] Users report normal operation
- [ ] Accounting team approves workflow

**If all checked:** ✅ **Deployment Successful!**

---

## 📞 Support During Deployment

| Issue | Contact | Phone | Slack |
|-------|---------|-------|-------|
| Emergency/Blocker | DevOps Lead | +62-XXX-XXXX | #devops |
| Code Issue | Developer | | #dev |
| Accounting Question | Accounting Manager | | #finance |
| User Issue | Support Team | | #support |

---

## 📝 Sign-Off

**Deployment Completed By**: _____________________ Date: ___________

**Technical Lead Sign-Off**: _____________________ Date: ___________

**Operations Lead Sign-Off**: _____________________ Date: ___________

---

**Deployment Duration**: From __________ to __________

**Total Time**: __________ minutes

**Critical Issues**: ☐ Yes ☐ No (If yes, attach incident report)

**Status**: ☐ Successful ☐ Partial ☐ Rolled Back

**Notes**:
```
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
```

---

**Next Deployment Review**: _____________________ (7 days from deployment)
