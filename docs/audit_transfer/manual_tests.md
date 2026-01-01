# Manual Test Checklist — Transfer Application

## Phase 1 — Document & Workflow
- [ ] Create Transfer Application with company, beneficiary/bank details, amount, purpose, requested_transfer_date.
- [ ] Verify reference_doctype options only show existing doctypes; selecting one filters reference_name to submitted docs.
- [ ] Ensure amount_in_words auto-fills and expected_amount mirrors amount.
- [ ] Walk through workflow: Draft → Finance Review → Approved for Transfer → Awaiting Bank Confirmation; confirm status field mirrors workflow_state.
- [ ] Use **Transfer Application - Bank Form** print preview; check two blank signature areas and placeholders for names/titles.
- [ ] Click **Mark as Printed**; printed_by/printed_at populate.

## Phase 1 — Payment Entry Integration
- [ ] From an Approved/Awaiting document, click **Create Payment Entry** → confirm draft Payment Entry is created, linked back, and opens in form.
- [ ] Submit Payment Entry; Transfer Application status/workflow_state update to Paid with paid_date/paid_amount populated.
- [ ] Cancel Payment Entry; link is cleared and status reverts to Awaiting Bank Confirmation.
- [ ] Attempt to create another Payment Entry while one is active → system warns/blocks duplication.

## Phase 2 — Bank Transaction Matching
- [ ] Import/create a Bank Transaction (withdrawal/debit) matching a Transfer Application (amount within tolerance, beneficiary/hint in description).
- [ ] On submit/update, Bank Transaction links to Transfer Application, sets match_confidence=Strong, and adds timeline note.
- [ ] If auto-create setting is OFF, confirm no Payment Entry is generated; when ON, verify Payment Entry is created/submitted and Transfer Application moves to Paid.
- [ ] Create ambiguous amount match without hint/name → match_confidence=Weak/Manual and no auto link.
- [ ] Create multiple strong candidates → Bank Transaction flagged Manual with notes listing candidates.
