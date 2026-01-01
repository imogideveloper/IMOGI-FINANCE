# Scan Findings

## SQL Inventory
- Unable to run `SELECT` inventory queries on `tabDocType` / `tabPrint Format` because `bench` is not installed and no Frappe site/database is available in this container.

## Codebase Search
- `rg -n "Transfer Application|Aplikasi Transfer|Payment Order|Transfer Slip|signatory|tanda tangan|wet signature|approval transfer" -S imogi_finance` → **no matches**.

## Existing Related Doctypes / Features
- **Administrative Payment Voucher** (`imogi_finance/imogi_finance/doctype/administrative_payment_voucher`): Custom, submittable voucher that auto-creates and submits Payment Entries (`administrative_payment_voucher.py`) and has its own workflow. Geared to post journals via Payment Entry, not a non-accounting instruction form.
- **Customer Receipt** (`imogi_finance/imogi_finance/doctype/customer_receipt`): Custom incoming receipt flow with Payment Entry enforcement; not a transfer instruction.
- **BCA Bank Statement Import** (`imogi_finance/imogi_finance/doctype/bca_bank_statement_import` + rows): Custom import that creates native **Bank Transaction** records; focuses on statement ingestion.
- **Native ERPNext doctypes** available in target ERPNext stack (assumed): **Payment Entry**, **Bank Transaction**, **Purchase Invoice**, **Expense Claim**, **Payroll Entry/Salary Slip**, **Journal Entry** — none in this app implement a standalone transfer-instruction document.

## Duplication Risk & Reuse Notes
- No existing "Transfer" instruction DocType or print format was found in the codebase search.
- Administrative Payment Voucher already posts Payment Entries; using it would mix accounting postings with the requested non-accounting transfer instruction, so it is not a suitable base.
- Bank Transaction integrations already exist (BCA import), so new matching should reuse the native **Bank Transaction** DocType rather than introducing a new statement DocType.

## Recommendation
- Create a dedicated, non-posting DocType **Transfer Application** with workflow + print format, linked natively to **Payment Entry** and **Bank Transaction**.
- Extend native doctypes with minimal custom fields (Payment Entry link + Bank Transaction matching metadata) instead of creating parallel posting flows.
