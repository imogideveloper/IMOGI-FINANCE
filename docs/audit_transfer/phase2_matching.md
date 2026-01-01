# Phase 2 — Bank Statement Matching

## Settings (Single)
- **Transfer Application Settings** controls matching:
  - `enable_bank_txn_matching` (default ON)
  - `enable_auto_create_payment_entry_on_strong_match` (default OFF)
  - `default_paid_from_account`, `default_paid_to_account` (optional fallbacks for Payment Entry creation)
  - `matching_amount_tolerance` (currency, default 0)

## Custom Fields
- **Payment Entry**: `transfer_application` (Link) to enforce unique linkage and update statuses on submit/cancel.
- **Bank Transaction**: `transfer_application` (Link), `match_confidence` (Select Strong/Medium/Weak/Manual), `match_notes` (Small Text) for traceability.

## Matching Triggers
- Runs on Bank Transaction submit/update (docstatus 1) when status is Unreconciled/Pending Reconciliation and matching is enabled.
- Considers only withdrawals/debits (or negative `amount`) to avoid matching incoming funds.

## Candidate Selection
- Transfer Applications with status in **Approved for Transfer** or **Awaiting Bank Confirmation**, no Payment Entry, docstatus < 2.
- Amount must match `expected_amount` (or `amount`) within tolerance.

## Match Strength
- **Strong**: amount within tolerance AND account number/hint/name/TA ID appears in bank description/reference text. Unique strong match → link Bank Transaction.transfer_application, set confidence=Strong, comment on both docs.
- **Medium**: amount match + beneficiary name in remark; flagged for review with confidence=Medium.
- **Weak/Manual**: amount match only or multiple strong candidates → confidence set accordingly, note added for manual review.

## Auto Payment Entry (optional)
- If setting `enable_auto_create_payment_entry_on_strong_match` is ON and Bank Transaction has no existing payment link, system auto-creates & submits a Payment Entry (Pay) using Transfer Application details, posting date from bank transaction date, and the matched amount.
- Safeguards: skips when Transfer Application already has an active Payment Entry or Bank Transaction already has a payment link; errors are logged + noted on Bank Transaction.
- On success, Transfer Application is updated to Paid with payment_entry/paid_date/paid_amount populated.

## Review Queues
- Filter suggestions:
  - Bank Transaction where `transfer_application` is empty AND status = Unreconciled to find unmatched debits.
  - Transfer Application where status = Awaiting Bank Confirmation AND payment_entry is empty to chase pending payouts.
