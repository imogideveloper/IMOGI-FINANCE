### Imogi Finance

App for Manage Expense IMOGI

### BCA Bank Statement Import (Native-First)

This app now includes a native-first adapter for importing BCA bank CSV statements into ERPNext:

- Use the **BCA Bank Statement Import** DocType to upload a CSV export from BCA internet banking.
- Click **Parse CSV BCA** to validate headers, amounts, and detect duplicate uploads via file hash.
- Parsing now auto-converts rows into native ERPNext `Bank Transaction` records (with duplicate detection), and the **Convert to Bank Transaction** action remains available for retries.
- Use the **Open Bank Reconciliation Tool** button to jump directly into reconciliation with the parsed date range and bank account.
- Flow summary: **Upload BCA → Parse → Convert → buka Bank Reconciliation Tool (otomatis lewat tombol).**

### Kontrol dan Risiko Workflow Expense Request

Lihat [Catatan Kontrol Workflow Expense Request](WORKFLOW_GUARDRAILS.md) untuk memahami dampak flag situs, perilaku rebuild rute, dan rekomendasi audit ketika melakukan reopen/close.

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

Gunakan contoh snippet berikut di bench console untuk memastikan validasi baru bekerja (mis. status belum Approved atau sudah terhubung ke dokumen lain):

```python
request = frappe.get_doc("Expense Request", "<NAMA_REQUEST>")
# Harus melempar error bila status belum Approved atau docstatus bukan 1
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)

# Tandai request sudah terhubung agar memicu error duplikasi
request.db_set("linked_purchase_invoice", "PI-TEST")
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)
# Untuk request tipe Asset, gunakan Purchase Invoice (Flow JE manual dihapus)
request.db_set({"linked_purchase_invoice": None, "request_type": "Asset"})
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)
```

### License

mit
