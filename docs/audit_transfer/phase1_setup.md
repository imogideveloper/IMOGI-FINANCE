# Phase 1 — Transfer Application Setup

## DocType: Transfer Application
- Non-accounting, submittable document with workflow states: Draft → Finance Review → Approved for Transfer → Awaiting Bank Confirmation → Paid (docstatus=1).
- Key fields: company, posting_date, reference_doctype/reference_name (dynamic options filtered to existing doctypes), payee/beneficiary details, transfer method, amount/amount_in_words, requested_transfer_date, transfer_purpose, signatory placeholders (manual names/titles), payment_entry link, paid_amount/paid_date (read-only), printed_by/printed_at audit.
- Defaults: naming series `TA-.YYYY.-.#####`, currency from Company/default, expected_amount mirrors amount, payee_type auto maps party_type for Supplier/Employee.

## Workflow
- Configured via **Transfer Application Workflow** (fixture):
  - Submit for Review (Accounts User) → Approve Transfer (Accounts Manager) → Release to Bank (Accounts User) → Mark Paid (Accounts Manager, only when linked Payment Entry is submitted).
  - Status field mirrors workflow state; Paid state requires submitted Payment Entry.

## Print Format
- **Transfer Application - Bank Form** (Jinja) renders company logo + title “Aplikasi Transfer Dana”, beneficiary/bank/account details, amount & terbilang, purpose, bank reference hint, payment tracking (Payment Entry / paid date/amount), and two blank wet-signature columns using manual signatory labels/names/titles.

## Client Actions
- Dynamic reference options fetched from server; reference_name filtered to submitted docs.
- **Create Payment Entry** button (Actions menu): saves the document, creates a draft Payment Entry (Pay) with party/account mapping + references, links it back to the Transfer Application, and opens the Payment Entry for review.
- **Mark as Printed** button to stamp printed_by/printed_at audit fields.

## Links & Guardrails
- Payment Entry custom link field (`transfer_application`) enforces single active link per Transfer Application via backend validation.
- Payment Entry submission updates Transfer Application payment link + paid date/amount + status/workflow_state=Paid; cancellation clears the link and reverts status to Awaiting Bank Confirmation.
- No GL posting occurs from Transfer Application itself; all postings remain on Payment Entry.
