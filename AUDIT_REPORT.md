# Administrative Payment Voucher Audit (ERPNext v15+)

## Phase 0 — Inventory
- `imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.py`: Server-side controller, validations, workflow guards, Payment Entry orchestration.
- `imogi_finance/imogi_finance/doctype/administrative_payment_voucher/payment_service.py`: New centralized Payment Entry creation/idempotency/locking service.
- `imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.js`: Form button to create/view Payment Entry.
- `imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher_list.js`: List filter for Branch.
- `imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.json`: DocType definition, status fields, permissions.
- `imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher_dashboard.py`: Dashboard link to Payment Entry.
- `imogi_finance/fixtures/workflow.json` (workflow `Administrative Payment Voucher Workflow`): Draft → Pending Approval → Approved → Posted (docstatus 1) → Cancelled.
- `imogi_finance/fixtures/custom_field.json`: Custom Link field `Payment Entry.imogi_administrative_payment_voucher` for source tracking.
- `imogi_finance/imogi_finance/doctype/finance_control_settings/finance_control_settings.json`: APV settings (enforce branch/cost center, require Accounts Manager, target bank/cash policy, default MOP, attachment rules).
- Entry points that create/submit Payment Entry: controller `create_payment_entry`, workflow action `Post`, whitelisted `create_payment_entry_from_client` button, controller `before_submit` safety net.

Overlapping ERPNext features considered: native Payment Entry handling, Accounting Dimensions/Branch helpers (`imogi_finance.branching`), fiscal year validation, tax period locks, and Payment Entry custom link field.

## Phase 1 — Findings
| ID | Severity | Description | Evidence | Fix/Resolution |
| --- | --- | --- | --- | --- |
| APV-1 | HIGH | Payment Entry creation bypassed permissions via `ignore_permissions`, lacked idempotency, and could be called on draft/without locking → duplicate or unauthorized PEs. | Controller `create_payment_entry` inserted with `ignore_permissions=True` and no locking/idempotency. 【imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.py†L207-L258】 | Added `payment_service.ensure_payment_entry` with DB row lock, reuse checks, alignment validation, and standard permissioned insert/submit; controller now delegates and enforces state/role gates. |
| APV-2 | HIGH | Missing validation for reference targets and party/account combinations; target bank/cash allowed even when disallowed; bank account root type not enforced. | Validation methods skipped `frappe.db.exists` and target account type checks. 【imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.py†L236-L276】【imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.py†L295-L317】 | Strengthened validations: existence checks, bank/cash root-type enforcement, target bank disallow policy, party alignment guards, and attachment requirement safeguards. |
| APV-3 | MEDIUM | Posting workflow could create Payment Entry before submit and without concurrency safety, risking duplicate posting and status desync. | Workflow action `Post` called `create_payment_entry` directly without lock/flag; no fallback on submit. 【imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.py†L420-L456】 | Added shared `_ensure_payment_entry` with workflow flag, called from workflow Post and `before_submit`; service applies status sync, audit log, and reuse logic. |
| APV-4 | MEDIUM | Cancellation path did not surface clear errors when Payment Entry could not be cancelled/reconciled. | `_attempt_cancel_payment_entry` swallowed specific errors. 【imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.py†L512-L535】 | Hardened cancellation to raise actionable error with underlying message and timeline comment for success. |
| APV-5 | LOW | Optional dimension/Branch handling could crash when columns absent; apply_optional_dimension relied solely on DB column. | `apply_optional_dimension` used `frappe.db.has_column` without meta guard. 【imogi_finance/imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher.py†L106-L124】 | Added meta-aware dimension setter with safe DB fallback and reused in payment service; branch applied only when supported. |
| APV-6 | LOW | Test harness lacked shared Frappe stubs causing import failures across suite (utils, exceptions, db helpers). | Pytest errors importing `frappe.utils`/`frappe.exceptions`. | Added root `conftest.py` and test-level guards for missing DB helpers; reordered dataclass fields to satisfy Python validation. |

## Recommendations
- Short term: keep APV workflow in sync with controller status mapping; monitor Payment Entry creation logs for duplicate attempts to validate idempotency in production.
- Medium term: add site-configurable role list for posting/cancel permissions (beyond Accounts Manager) and extend dimension propagation to additional accounting dimensions if configured.
- Long term: consider migrating APV posting to queued job with retry-aware locks for high-volume sites.

## Runbook
1. `bench migrate`
2. `bench --site <site> run-tests --app imogi_finance`
3. UI validation: create APV → Approve → Post → ensure Payment Entry is created/linked; attempt duplicate post (should reuse); cancel APV with unreconciled PE (cancels) vs reconciled (raises). 

## Summary Table
| Area | Status | Notes |
| --- | --- | --- |
| Payment Entry creation | Hardened | Centralized service with lock/idempotency, alignment checks, and audit logs. |
| Validations | Hardened | Bank/cash policy, reference existence, party/account alignment, fiscal year guard retained. |
| Cancellation | Hardened | Clear error surfacing and timeline logging. |
| Dimensions/Branch | Compatible | Meta-aware setters avoid crashes when fields absent. |
| Tests | Updated | New regression coverage for posting guards/idempotency and shared Frappe stubs; suite green. |
