### Imogi Finance

App for Manage Expense IMOGI

### BCA Bank Statement Import (Native-First)

This app now includes a native-first adapter for importing BCA bank CSV statements into ERPNext:

- Use the **BCA Bank Statement Import** DocType to upload a CSV export from BCA internet banking.
- Click **Parse CSV BCA** to validate headers, amounts, and detect duplicate uploads via file hash.
- Click **Convert to Bank Transaction** to create native ERPNext `Bank Transaction` records (with duplicate detection).
- Open the standard **Bank Reconciliation Tool** from the same form to continue the native reconciliation flow.

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

### License

mit
