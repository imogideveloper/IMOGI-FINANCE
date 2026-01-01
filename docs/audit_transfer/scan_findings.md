# Scan Findings

## SQL Inventory
- Unable to run `SELECT` inventory queries on `tabDocType` / `tabPrint Format` because `bench` is not installed and no Frappe site/database is available in this container.

## Codebase Search
- `rg -n "Transfer Application|Aplikasi Transfer|Payment Order|Transfer Slip|signatory|tanda tangan|wet signature|approval transfer" -S imogi_finance` → matches across the Transfer Application module, including:
  - DocType: `imogi_finance/imogi_finance/doctype/transfer_application/transfer_application.json` (submittable, non-accounting document with signatory placeholders, payment tracking, and reference links).
  - Server/Client logic: `transfer_application.py` (validation, amount-in-words, payment sync, payment entry creation) and `transfer_application.js` (reference options, create Payment Entry, mark as printed).
  - Payment Entry helper/hooks: `transfer_application/payment_entries.py` and `transfer_application/payment_entry_hooks.py`.
  - Bank Transaction matching automation: `transfer_application/matching.py` and settings helper `transfer_application/settings.py`.
  - Print Format: `print_format/transfer_application_bank_form/transfer_application_bank_form.*`.
  - Workflow fixture: `fixtures/workflow.json` entry `Transfer Application Workflow`.
  - Custom Fields: `fixtures/custom_field.json` entries for Payment Entry ↔ Transfer Application link, and Bank Transaction matching fields (`transfer_application`, `match_confidence`, `match_notes`).

## Existing Related Doctypes / Features
- **Transfer Application** (custom, submittable) — already present as the requested non-accounting transfer instruction doc, with workflow, print format, payment link, and matching utilities.
- **Transfer Application Settings** (Single DocType) — controls bank transaction matching + auto Payment Entry creation settings.
- **Payment Entry custom link** (`fixtures/custom_field.json` → `Payment Entry-transfer_application`) — enforces single active link to a Transfer Application; hooks update TA on submit/cancel.
- **Bank Transaction custom fields** (`transfer_application`, `match_confidence`, `match_notes`) — used by matching automation to record linkage and review notes.
- **Workflow:** `Transfer Application Workflow` fixture defining Draft → Finance Review → Approved for Transfer → Awaiting Bank Confirmation → Paid states.
- **Print Format:** `Transfer Application - Bank Form` Jinja template with dual wet-signature placeholders.
- **Administrative Payment Voucher** (`imogi_finance/imogi_finance/doctype/administrative_payment_voucher`): Custom voucher that auto-creates/submits Payment Entries; posts accounting entries and is not suited for non-accounting transfer instructions.
- **Customer Receipt** (`imogi_finance/imogi_finance/doctype/customer_receipt`): Incoming receipt flow; not applicable to outbound transfers.
- **BCA Bank Statement Import** (`imogi_finance/imogi_finance/doctype/bca_bank_statement_import`) and related row child tables: statement ingestion that creates native **Bank Transaction** entries (reusable for matching).

## Duplication Risk & Reuse Notes
- A dedicated **Transfer Application** module already exists in this app and aligns with the requested non-accounting transfer instruction flow (workflow, print format, Payment Entry linkage, Bank Transaction matching).
- Administrative Payment Voucher already posts Payment Entries; reusing it would mix non-accounting instructions with posting logic, so it remains unsuitable.
- Bank Transaction integrations already exist (BCA import) and should be reused for matching rather than introducing new bank statement doctypes.

## Recommendation
- Continue using and extending the existing **Transfer Application** DocType as the canonical non-accounting transfer instruction record.
- Keep leveraging native **Payment Entry** for postings via the provided create-and-link utilities, and **Bank Transaction** for evidence-based matching using the existing custom fields + automation.
