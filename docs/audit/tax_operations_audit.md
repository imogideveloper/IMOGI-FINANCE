# Tax Operations Audit (PPN/PPh/PB1, CoreTax, OCR) – IMOGI Finance

## 1) Executive Summary

- **Overall status:** **Partial** – core DocTypes, custom fields, and registers exist, but OCR execution is stubbed, verification is manual, and Sales Invoice gating is light. CoreTax exports now validate required mappings and direction before running, and Tax Profiles require complete account coverage. Tax payments are native-first (Payment Entry/Journal Entry) with no custom GL hooks.
- **Key risks**
  - OCR flow cannot run end-to-end because providers are stubbed; buttons enqueue jobs that immediately fail with configuration errors.【F:imogi_finance/tax_invoice_ocr.py†L198-L205】
  - Tax invoice verification is manual (buttons only) and only enforced for Purchase Invoice submit/Expense Request ➜ PI creation; Sales Invoices and non-OCR PI edits are not auto-validated for duplicates/NPWP/PPN tolerance, though PPN/PPh templates/types are now enforced during validate on PI/SI.
  - Tax Period Closing locks edits, but duplicate/tolerance rules are not re-checked on submit; reliance on user action may allow unchecked data through.
  - Default PPN templates/tax-rule flags exist in settings but are unused in code paths, risking inconsistent tax mapping defaults.

## 2) Inventory (As-Is)

### Settings
- **Tax Invoice OCR Settings (Single):** OCR flags, provider/lang/page/size/confidence limits, JSON storage, verification gates, NPWP normalization, duplicate blocking, PPN input/output accounts, default PPN type, effective-date flag, default/zero PPN templates.【F:imogi_finance/imogi_finance/doctype/tax_invoice_ocr_settings/tax_invoice_ocr_settings.json†L10-L159】
- **Helper:** `imogi_finance.tax_invoice_ocr.get_settings()` exposes defaults/DB overrides; `imogi_finance.tax_settings.get_tax_invoice_ocr_settings` re-exports.【F:imogi_finance/tax_invoice_ocr.py†L15-L96】【F:imogi_finance/tax_settings.py†L1-L11】
- **CoreTax Export Settings:** Require at least one column mapping, validate direction (Input/Output), and enforce mappings for DPP, PPN, NPWP, and faktur date before exports run.【F:imogi_finance/imogi_finance/doctype/coretax_export_settings/coretax_export_settings.py†L7-L22】【F:imogi_finance/tax_operations.py†L195-L270】【F:imogi_finance/tax_operations.py†L343-L370】

### Tax profile / mapping
- **Tax Profile:** per-company PPN input/output/payable, PB1 payable, PPh payable table, tolerance/rounding, default CoreTax settings; validation now requires PPN Input/Output, PB1, and at least one PPh payable account entry.【F:imogi_finance/imogi_finance/doctype/tax_profile/tax_profile.json†L1-L123】【F:imogi_finance/imogi_finance/doctype/tax_profile/tax_profile.py†L10-L61】
- **PPh mapping child:** `Tax Profile PPh Account` table (pph_type/payable_account).【F:imogi_finance/imogi_finance/doctype/tax_profile_pph_account/tax_profile_pph_account.json†L1-L52】

### Custom fields (fixtures)
- **Purchase Invoice:** OCR attach/status/confidence/raw JSON; faktur metadata (no/date/NPWP/DPP/PPN/type); verification status/notes/duplicate/NPWP match; expense request links.【F:imogi_finance/fixtures/custom_field.json†L37-L202】
- **Expense Request:** mirror OCR + faktur fields for gating; verification flags; prevent PI if not ready; allocation/internal charge helpers.【F:imogi_finance/fixtures/custom_field.json†L203-L380】
- **Sales Invoice:** output faktur section with OCR+metadata+verification flags/buyer tax ID.【F:imogi_finance/fixtures/custom_field.json†L381-L555】

### Client scripts & APIs
- **Buttons:** Run OCR + Verify on Purchase Invoice and Sales Invoice; Create Purchase Invoice gating + OCR/Verify on Expense Request.【F:imogi_finance/public/js/purchase_invoice_tax_invoice.js†L1-L51】【F:imogi_finance/public/js/sales_invoice_tax_invoice.js†L1-L52】【F:imogi_finance/imogi_finance/doctype/expense_request/expense_request.js†L121-L229】
- **API endpoints:** `run_ocr_for_*`, `verify_*` map to OCR/verification helpers (roles enforced only on verify).【F:imogi_finance/api/tax_invoice.py†L1-L35】

### Backend flows
- **Expense Request ➜ Purchase Invoice:** `create_purchase_invoice_from_request` enforces approved status, duplicate PI guard, budget lock/internal charge, optional tax verification gate, maps faktur metadata, applies PPN template when present.【F:imogi_finance/accounting.py†L160-L280】
- **Purchase Invoice submit gate:** blocks submit unless Verified when setting enabled.【F:imogi_finance/events/purchase_invoice.py†L19-L28】
- **Tax period lock:** prevents tax-field edits inside closed periods (unless privileged), covering PI/SI/Expense Request fields and tax mappings.【F:imogi_finance/tax_operations.py†L104-L151】
- **PPN/PPh validation:** DocEvents enforce PPN templates and PPh types/base amounts during validate for PI/SI (plus existing ER validation), using shared FinanceValidator rules.【F:imogi_finance/validators/finance_validator.py†L15-L58】【F:imogi_finance/hooks.py†L146-L189】

### OCR & verification logic
- Parsing, NPWP normalization, duplicate checks across PI/ER/SI, NPWP match vs party tax_id/npwp, PPN vs DPP tolerance; OCR provider stub raises configuration errors for all providers.【F:imogi_finance/tax_invoice_ocr.py†L198-L377】

### Tax operations / closing / payments
- **Tax Period Closing:** computes register snapshot, CoreTax exports, optional VAT netting JE creation; status set to Closed on submit.【F:imogi_finance/imogi_finance/doctype/tax_period_closing/tax_period_closing.py†L10-L119】
- **Tax Payment Batch:** per-period payment draft with payable/payment accounts, party/mode, references; builds native JE/Payment Entry only (no custom GL).【F:imogi_finance/imogi_finance/doctype/tax_payment_batch/tax_payment_batch.py†L10-L91】
- **CoreTax Export Settings & Column Mapping** exist and are ensured on install/migrate; migration reload also refreshes related reports and tax doctypes.【F:imogi_finance/imogi_finance/doctype/coretax_export_settings/coretax_export_settings.json†L1-L67】【F:imogi_finance/imogi_finance/utils.py†L8-L19】【F:imogi_finance/patches/post_model_sync/ensure_coretax_export_settings.py†L1-L21】

### Reports / registers
- **VAT Input/Output Register (Verified)** driven by ti/out_fp metadata and filtered to Verified statuses; uses PPN input/output account filters from settings.【F:imogi_finance/imogi_finance/report/vat_input_register_verified/vat_input_register_verified.py†L10-L66】【F:imogi_finance/imogi_finance/report/vat_output_register_verified/vat_output_register_verified.py†L10-L67】
- **Withholding Register:** GL-based using PPh payable accounts from Tax Profile.【F:imogi_finance/imogi_finance/report/withholding_register/withholding_register.py†L6-L57】
- **PB1 Register:** GL-based using PB1 payable account from Tax Profile.【F:imogi_finance/imogi_finance/report/pb1_register/pb1_register.py†L6-L53】

## 3) Gap Analysis (Requirement vs. Current State)

| Requirement | Current State | Gap / Priority |
| --- | --- | --- |
| OCR runnable with provider & background job success | Provider stubs always raise; queue leads to Failed status | **P0:** Implement provider integration or guard button when provider unusable.【F:imogi_finance/tax_invoice_ocr.py†L198-L247】 |
| Enforce verification before submit across PI/SI | PI enforced; SI not enforced; ER ➜ PI gate exists | **P0:** Add Sales Invoice verify gate (before_submit/validate) with override roles. |
| Duplicate/NPWP/PPN tolerance auto-check on save/submit | Checks only when user clicks Verify; no auto-trigger | **P1:** Trigger verification or validation hook on PI/SI/ER changes or submit. |
| Default PPN templates/tax rule effective date usage | Fields exist in settings, unused in flows | **P2:** Wire defaults into PI creation (ER ➜ PI) and validation logic. |
| CoreTax export coverage for verified invoices | Exports block when required PPN/DPP/NPWP/date mappings are missing or direction mismatches settings | **Closed (validation added):** Mapping completeness enforced during settings save/export generation.【F:imogi_finance/tax_operations.py†L195-L270】【F:imogi_finance/imogi_finance/doctype/coretax_export_settings/coretax_export_settings.py†L7-L22】 |
| Tax Profile presence per company | Required by helper; validation now enforces key PPN/PB1/PPh accounts when profile exists | **P1:** Add onboarding validation in UI/setup wizard to ensure profile creation. |
| Payment batch amounts source of truth | Computes from closing snapshot or GL totals; no reconciliation with registers list | **P2:** Add drill-down/reconcile UI to references and validation of linked vouchers. |

## 4) Recommendations (Action Plan)

### Quick Wins
- Disable/guard OCR buttons when provider is “Manual Only” or credentials missing; surface configuration guidance instead of queueing failing jobs.【F:imogi_finance/public/js/purchase_invoice_tax_invoice.js†L5-L30】【F:imogi_finance/tax_invoice_ocr.py†L198-L247】
- Add Sales Invoice verification gate (validate/before_submit) mirroring PI rule, with Tax Reviewer/Accounts Manager override flag.
- Auto-run lightweight verification (duplicate/NPWP/PPN tolerance) on PI/SI/ER validate when relevant fields change, setting status to Needs Review with notes; keep manual verify button for re-check/override.

### Phase 2
- Use Tax Invoice OCR Settings defaults (default/zero PPN templates, use_tax_rule_effective_date) when creating PI from Expense Request and when mapping taxes on PI to align with policy.
- Attach CoreTax export logs to Tax Period Closing (mapping coverage already enforced).
- Add setup checklist to ensure Tax Profile per company and PPN/PPh/PB1 accounts configured before enabling OCR/verification.

### Phase 3
- Optional: Introduce workflow or dashboard for “Needs Review” queues across PI/ER/SI with bulk verify (role-gated).
- Add reconciliation helpers in Tax Payment Batch to list linked register rows/GL entries and prevent overpayment.

## 5) Risks & Mitigations

- **OCR unusable → user frustration:** Guard buttons, provide manual entry guidance, and log clear errors; enable provider feature flag only after credentials tested.
- **Unverified Sales Invoices slipping through:** Add submit gate + role-based override; periodic report of out_fp_status ≠ Verified.
- **Data drift vs. registers/CoreTax:** Auto-verify on save and enforce mapping presence before closing export; retain snapshot JSON for audit trail (already stored).
- **Workflow conflicts:** Current hooks avoid workflow overrides; any new gate should remain validate/before_submit so existing approvals (Expense Request workflow) stay intact.
- **Performance:** Duplicate checks query PI/ER/SI across company; consider adding index on custom fields (ti_fp_no/out_fp_no) if dataset grows.
