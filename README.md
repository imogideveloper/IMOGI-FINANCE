### Imogi Finance

App for managing expenses at IMOGI.

### Key Features

#### Expense Request & Approvals

- **Dynamic approval routes**: routes are calculated from Expense Approval Settings per Cost Center + expense account + amount, stored on the document, and must be refreshed before approval (configuration changes are detected and block approval until refreshed). Submit is restricted to the creator, approvers must match the user/role on the route, and levels cannot be skipped.
- **Edit controls & post-submit states**: changing amount/cost center/expense account while Pending resets to Pending Review (level 1) with an audit comment; key fields cannot change in Approved/Linked/Closed. Pending edits are limited to the owner or approver, and all rejections/overrides are recorded in the timeline.
- **Protected reopen & close**: reopen is reserved for System Manager unless an override flag is set; it enforces audit when active links to Payment Entry/Purchase Invoice/Asset exist. Close validates the latest route or final snapshot; an emergency override flag is available with audit trail.
- **Status guardrails & audit trail**: off-workflow status changes are blocked, approval routes are snapshotted when Approved to validate Close, and automatic comments are posted for denied workflow actions, pending edits, or reopen overrides.

#### Budget Control & Internal Charge

- **Staged budget lock**: Budget Control Settings can lock budgets at Approved/Linked, reserving per Cost Center + Account (+Project/Branch) and releasing automatically on Reject/Reopen. Consumption occurs on Purchase Invoice submit and is reversed on cancel.
- **Overrun handling & special role**: the `allow_budget_overrun_role` can permit overruns when reservation fails. Lock status (`Locked/Overrun Allowed/Consumed/Released`) is synchronized to the Expense Request.
- **Integrated internal charge**: the “Allocated via Internal Charge” mode requires an Approved Internal Charge Request before approval/PI; the `create_internal_charge_from_expense_request` helper auto-creates a draft with a starter line. “Auto JE on PI Submit” posts a reclass Journal Entry across Cost Centers according to allocation.

#### Accounting & Downstream Documents

- **Purchase Invoice creation from Expense Request**: a whitelisted helper ensures the request is Approved, type (Expense/Asset) matches, no duplicate links exist, and copies items (including VAT/WHT) with pending/submitted markers to prevent duplicate invoices.
- **Asset & Payment Entry linking**: hooks on Asset, Purchase Invoice, and Payment Entry maintain request status, prevent duplicate links, and verify downstream documents are submitted before payment. Requests are automatically Closed after Payment Entry succeeds.
- **Multi-branch compliance**: branch is derived from Cost Center/Finance Control Settings when creating PI from Expense Request; PI/PE/Asset links validate branch alignment when enforcement is enabled.

#### Customer Receipt & Payment Validation

- **Customer Receipt document**: chooses default print layout from Finance Control Settings, validates Sales Invoice/Sales Order references by customer & company, locks items after Issued, and computes Issued/Partially Paid/Paid status based on incoming payments.
- **Payment safeguards**: Payment Entry hook enforces “Mandatory Strict” mode (must link to a Customer Receipt when open receipts exist), blocks over-allocation or unrelated references except in mixed payment mode, and automatically updates/removes payment notes on Receipt during submit/cancel.
- **Collection automation**: the `make_payment_entry` button on Receipt creates Payment Entry with automatic allocation per outstanding reference.
- **Stamp policy & Jinja utilities**: Receipts apply digital/physical stamp policy per configuration (mandatory/threshold/fallback) and expose Jinja filters `terbilang_id` and `build_verification_url` for print templates.

#### Reconciliation & Bank Imports

- **BCA Bank Statement Import**: upload BCA CSV, the system hashes to prevent re-uploads, validates headers/numbers (detecting merged columns/“sep=” preamble), computes balances, and skips balance/pending rows. **Parse CSV BCA** prepares rows then **Convert to Bank Transaction** creates Unreconciled Bank Transactions with duplicate prevention and success/failure reporting. **Open Bank Reconciliation Tool** opens with the same date range & bank account.
- **Bank Transaction controls**: Unreconciled transactions cannot be cancelled (backend guard + hidden Cancel button) to preserve reconciliation history.

#### Transfer Application & Payment Automation

- **Automatic Payment Entry creation**: helper button creates Payment Entry from Transfer Application with paid_from/paid_to defaults from settings or company accounts; can auto-submit and copy document references.
- **Bank Transaction matching**: on Bank Transaction submit/update, the system searches Transfer Application candidates by amount (with tolerance), account number/hint/payee name, and marks confidence Strong/Medium/Weak for review. Strong matches can auto-create Payment Entry and mark the TA as Paid.
- **Link protection**: Payment Entry hooks ensure a TA is not linked to multiple payments, update status/paid_amount/paid_date on submit, and clear links on cancel.

#### Tax, OCR, & CoreTax Export

- **Tax Invoice OCR**: OCR configuration (provider/size limit/threshold) for Purchase Invoice, Expense Request, and Sales Invoice; parses tax invoice text (NPWP, number/date, DPP/VAT) with NPWP normalization and duplicate flag. Verification status can be enforced as Verified before submitting PI or creating PI from Expense Request.
- **Tax profile controls**: Each company’s Tax Profile requires PPN input/output, PB1 payable, and PPh payable accounts so registers, closings, and payments post to the right ledgers.
- **Tax period closure**: Tax Period Closing blocks changes to tax/tax-mapping fields on ER/PI/SI when the period is Closed, except for System Manager/Tax Reviewer roles; validation uses posting date/bill date/request date.
- **Reporting & exports**: utilities compute snapshots for input/output VAT registers, withholding tax, and PB1; require CoreTax mappings for DPP, PPN, NPWP, and faktur date before exporting CSV/XLSX rows; provide Payment Entry/Journal Entry creation for Tax Payment Batch and VAT netting (calculate debit output/credit input/payable).

### Expense Request Workflow Controls & Risks

See [Expense Request Workflow Guardrails](WORKFLOW_GUARDRAILS.md) to understand site flag impacts, route rebuild behavior, and audit recommendations for reopen/close actions.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app imogi_finance
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/imogi_finance
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### Bench console checks

Use the following bench console snippet to verify the validations (e.g., status not yet Approved or already linked to other documents):

```python
request = frappe.get_doc("Expense Request", "<NAMA_REQUEST>")
# Should throw an error if status is not Approved or docstatus is not 1
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)

# Mark the request as linked to trigger duplicate error
request.db_set("linked_purchase_invoice", "PI-TEST")
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)
# For Asset requests, use Purchase Invoice (manual JE flow removed)
request.db_set({"linked_purchase_invoice": None, "request_type": "Asset"})
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)
```

### License

mit
