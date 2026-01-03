# Advance Payment Workflow Audit (Multi-Line Allocations)

## 1) Executive Summary
- **Overall status:** **Partial** – Advance Payment Entry records are created automatically from standalone Payment Entries and can be allocated to multiple Purchase Invoices, Expense Claims, or Payroll Entries with UI support. Currency-aware validation and outstanding-capacity checks have been strengthened on both the server and client to prevent silent over-allocation.
- **What's fixed now:** Allocation requests now reject currency mismatches, enforce unallocated balance limits per advance, and cap new allocations by remaining outstanding after considering previous allocations for the same document.【F:imogi_finance/advance_payment/api.py†L95-L278】【F:imogi_finance/public/js/advance_payment_allocation.js†L1-L204】
- **Remaining gaps:** Allocations are informational only—no Journal Entry is generated to move balances from advance to payables/expenses, so financial reconciliation still requires manual Payment Entries or JEs. Payroll-specific carry-forward or deduction handling is not implemented beyond allowing allocations to Payroll Entry documents.【F:imogi_finance/imogi_finance/doctype/advance_payment_entry/advance_payment_entry.py†L11-L148】【F:imogi_finance/advance_payment/api.py†L281-L312】

## 2) Inventory (As-Is)
- **DocTypes:** `Advance Payment Entry` (submittable, tracks allocations/unallocated/base amounts) with child table `Advance Payment Reference`.【F:imogi_finance/imogi_finance/doctype/advance_payment_entry/advance_payment_entry.json†L1-L171】【F:imogi_finance/imogi_finance/doctype/advance_payment_reference/advance_payment_reference.json†L1-L69】
- **Payment Entry hooks:** Standalone Supplier/Employee Payment Entries auto-create or update matching Advance Payment Entries; cancel clears allocations and cancels/deletes the advance.【F:imogi_finance/advance_payment/workflow.py†L15-L106】
- **APIs:** Fetch available advances, fetch existing allocations per reference, allocate advances with party/type validation, and clear/refresh allocations on linked document changes.【F:imogi_finance/advance_payment/api.py†L14-L259】
- **Client UI:** “Get Advances” button + dialog on Purchase Invoice, Expense Claim, and Payroll Entry to select multi-line allocations with outstanding awareness; dashboard shows allocated/unallocated per advance.【F:imogi_finance/public/js/advance_payment_allocation.js†L1-L301】
- **Report:** `Advance Payment Report` lists advances with allocated/unallocated totals and linked references.【F:imogi_finance/imogi_finance/report/advance_payment_report/advance_payment_report.py†L1-L78】

## 3) Findings & Actions
| ID | Status | Notes |
| --- | --- | --- |
| ADV-1 | **Closed** | Outstanding-capacity validation ignored prior allocations for the same invoice/claim, allowing cumulative over-allocation. Server now subtracts previously allocated amounts before accepting new rows, and the client dialog enforces the same cap with user-friendly errors.【F:imogi_finance/advance_payment/api.py†L95-L278】【F:imogi_finance/public/js/advance_payment_allocation.js†L98-L204】 |
| ADV-2 | **Closed** | Cross-currency allocations were silently accepted even when currencies differed. Server-side guard now blocks mismatches; available advances remain filtered by document currency.【F:imogi_finance/advance_payment/api.py†L112-L156】【F:imogi_finance/public/js/advance_payment_allocation.js†L206-L243】 |
| ADV-3 | **Closed** | Users could request amounts above an advance’s remaining balance and only see a generic error after save. Validation now checks against `available_unallocated` and raises a targeted message before saving.【F:imogi_finance/advance_payment/api.py†L118-L220】 |
| ADV-4 | **Open** | Allocations do not generate GL entries or reduce source/target outstanding amounts; Advance Payment Entry acts as an off-ledger tracker. Implement a reconciliation Journal Entry or Payment Entry application step (advance ➜ AP/Salary Payable) to make balances financial-source-of-truth and to support reversals cleanly.【F:imogi_finance/imogi_finance/doctype/advance_payment_entry/advance_payment_entry.py†L11-L148】 |
| ADV-5 | **Open** | Payroll-specific integration is limited to allowing allocations against Payroll Entry totals; no automatic deduction/carry-forward exists for unallocated balances. Extend payroll hooks to pick up employee advances or require a dedicated payroll deduction routine.【F:imogi_finance/advance_payment/api.py†L11-L312】 |

## 4) Checklist (per requirements)
| Feature | Status | Comments/Issues |
| --- | --- | --- |
| Advance Payment Entry Created | ✅ | Auto-generated/updated from standalone Payment Entries for Supplier/Employee parties.【F:imogi_finance/advance_payment/workflow.py†L15-L106】 |
| Journal Entry Posted (Advance) | ❌ | No JE/PE posting is triggered from Advance Payment Entry; financial impact depends on the original Payment Entry only.【F:imogi_finance/imogi_finance/doctype/advance_payment_entry/advance_payment_entry.py†L11-L148】 |
| Multi-Line Allocation Works | ✅ | Server + client support multiple allocations with remaining/unallocated tracking per row/table.【F:imogi_finance/advance_payment/api.py†L94-L156】【F:imogi_finance/public/js/advance_payment_allocation.js†L1-L204】 |
| Validation for Over-Allocation | ✅ | New guards cap allocations by remaining outstanding and advance balance, surfacing clear errors.【F:imogi_finance/advance_payment/api.py†L95-L278】【F:imogi_finance/public/js/advance_payment_allocation.js†L98-L204】 |
| Get Advances Button Functionality | ✅ | Button available on PI/Expense Claim/Payroll Entry forms and opens allocation dialog.【F:imogi_finance/public/js/advance_payment_allocation.js†L78-L205】 |
| Real-Time Unallocated Updates | ✅ | Form script recalculates allocated/unallocated and child remaining amounts on change/remove events.【F:imogi_finance/imogi_finance/doctype/advance_payment_entry/advance_payment_entry.js†L1-L48】 |
| Expense Claim Linking for Employee | ✅ | Employee advances can be fetched and allocated via UI + server party resolution; outstanding computation handles claims.【F:imogi_finance/public/js/advance_payment_allocation.js†L206-L243】【F:imogi_finance/advance_payment/api.py†L156-L265】 |
| Payroll Deduction Integration | ❌ | No automation to deduct or carry forward unallocated employee advances into payroll; only manual allocations to Payroll Entry are possible.【F:imogi_finance/advance_payment/api.py†L11-L312】 |
| Advance Payment Report Accuracy | ✅ | Report surfaces advance/allocated/unallocated with linked references using live DocType values.【F:imogi_finance/imogi_finance/report/advance_payment_report/advance_payment_report.py†L5-L78】 |
