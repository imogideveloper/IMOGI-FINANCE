# Tax Module Full Audit & Fix – IMOGI Finance

## Inventory (As-Is)
- **Settings**: Single doctype *Tax Invoice OCR Settings* drives OCR toggles, verification gates, tolerance/duplicate flags, and PPN account mappings.【F:imogi_finance/imogi_finance/doctype/tax_invoice_ocr_settings/tax_invoice_ocr_settings.json†L10-L118】
- **Tax mapping**: *Tax Profile* stores per-company PPN input/output/payable, PB1 payable, and PPh payable table with CoreTax defaults.【F:imogi_finance/imogi_finance/doctype/tax_profile/tax_profile.json†L14-L109】
- **Hooks & locking**: Tax fields on PI/SI/ER validated against closed periods; PI submit gated; closing/export/netting handled via Tax Period Closing.【F:imogi_finance/hooks.py†L146-L197】【F:imogi_finance/tax_operations.py†L131-L200】【F:imogi_finance/imogi_finance/doctype/tax_period_closing/tax_period_closing.py†L21-L161】
- **Payment**: Tax Payment Batch computes period amounts, fills payable accounts from Tax Profile, and builds native Payment Entry/Journal Entry drafts.【F:imogi_finance/imogi_finance/doctype/tax_payment_batch/tax_payment_batch.py†L19-L129】
- **Reports/exports**: Verified VAT registers for PI/SI, withholding & PB1 registers, and CoreTax export generator using column mappings.【F:imogi_finance/imogi_finance/report/vat_input_register_verified/vat_input_register_verified.py†L10-L72】【F:imogi_finance/imogi_finance/report/vat_output_register_verified/vat_output_register_verified.py†L10-L72】【F:imogi_finance/tax_operations.py†L299-L371】
- **Discovery map**: Centralized constants for doctypes/fields/methods/reports for regression coverage.【F:imogi_finance/tests/_tax_discovery.py†L7-L82】

## Findings (P0/P1) & Fixes
| Severity | Finding | Evidence | Fix |
| --- | --- | --- | --- |
| P1 | Expense Request duplicate detection used cost center string, so company-scoped duplicate checks could be bypassed. | Duplicate check resolves company from doc.company only; cost center wasn’t translated to company before filters were built.【F:imogi_finance/tax_invoice_ocr.py†L324-L339】 | Resolve company via cost center → company lookup before duplicate check to enforce correct scope.【F:imogi_finance/tax_invoice_ocr.py†L328-L336】 |
| P1 | VAT Input/Output registers silently fell back to total_taxes_and_charges when PPN account mapping was missing, risking overstated tax amounts. | Register tax extraction previously ignored missing mapping and could sum unrelated taxes (no warning).【F:imogi_finance/imogi_finance/report/vat_input_register_verified/vat_input_register_verified.py†L75-L92】【F:imogi_finance/imogi_finance/report/vat_output_register_verified/vat_output_register_verified.py†L75-L92】 | Added explicit warnings when mappings are absent and return 0 until configured, avoiding silent misreporting.【F:imogi_finance/imogi_finance/report/vat_input_register_verified/vat_input_register_verified.py†L75-L92】【F:imogi_finance/imogi_finance/report/vat_output_register_verified/vat_output_register_verified.py†L75-L92】 |

## Fixes Applied
- Hardened tax invoice verification to resolve company from cost center for Expense Requests before duplicate checks run.【F:imogi_finance/tax_invoice_ocr.py†L328-L336】
- VAT registers now warn on missing PPN account mapping and avoid inaccurate fallbacks.【F:imogi_finance/imogi_finance/report/vat_input_register_verified/vat_input_register_verified.py†L75-L92】【F:imogi_finance/imogi_finance/report/vat_output_register_verified/vat_output_register_verified.py†L75-L92】
- Added discovery constants and regression suite covering gates, duplicate checks, registers, CoreTax export, payment batch, and period locking.【F:imogi_finance/tests/_tax_discovery.py†L7-L82】【F:imogi_finance/tests/test_tax_module_regression.py†L30-L446】
- Test scaffolding extended to stub Frappe model/xlsx utilities for isolated regression execution.【F:imogi_finance/tests/conftest.py†L1-L59】

## Remaining Gaps / Backlog (P2)
- OCR provider implementations remain stubbed; running OCR with “Manual Only” or unconfigured providers still raises configuration errors (no actual OCR integration).【F:imogi_finance/tax_invoice_ocr.py†L203-L210】
- Default PPN template/effective-date flags in settings are not yet auto-applied to PI creation beyond existing mapping (behavior unchanged).【F:imogi_finance/imogi_finance/doctype/tax_invoice_ocr_settings/tax_invoice_ocr_settings.json†L21-L31】

## Regression Tests
- `imogi_finance/tests/test_tax_module_regression.py` covers submit/create gates, duplicate checks (PI/SI/ER), VAT registers, CoreTax export filtering, tax payment batch outputs, and tax-period locking.【F:imogi_finance/tests/test_tax_module_regression.py†L30-L446】

## Smoke Checklist
- PI submit blocked when verification required (settings on).【F:imogi_finance/events/purchase_invoice.py†L19-L27】
- ER → PI creation blocked unless verified when enforced; mapping carries faktur data/PPN template.【F:imogi_finance/accounting.py†L180-L276】
- VAT registers require Verified and mapped PPN accounts; warn when mapping missing.【F:imogi_finance/imogi_finance/report/vat_input_register_verified/vat_input_register_verified.py†L26-L92】【F:imogi_finance/imogi_finance/report/vat_output_register_verified/vat_output_register_verified.py†L26-L92】
- Tax period closing locks tax fields; privileged roles only bypass.【F:imogi_finance/tax_operations.py†L158-L200】
- Tax Payment Batch produces native PE/JE with configured accounts.【F:imogi_finance/tax_operations.py†L364-L434】

## CI / Test Command
- `bench --site <site> run-tests --app imogi_finance`
