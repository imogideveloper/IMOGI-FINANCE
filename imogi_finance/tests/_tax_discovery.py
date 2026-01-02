"""Discovery map for tax operations artifacts.

Generated from repository scan to centralize DocType, field, method, and report
names for regression tests.
"""

APP_NAME = "imogi_finance"

DOCTYPE_SETTINGS = "Tax Invoice OCR Settings"
DOCTYPE_TAX_PROFILE = "Tax Profile"
DOCTYPE_PERIOD_CLOSING = "Tax Period Closing"
DOCTYPE_PAYMENT_BATCH = "Tax Payment Batch"
DOCTYPE_CORETAX_SETTINGS = "CoreTax Export Settings"

FIELDS_PI = {
    "fp_no": "ti_fp_no",
    "fp_date": "ti_fp_date",
    "npwp": "ti_fp_npwp",
    "dpp": "ti_fp_dpp",
    "ppn": "ti_fp_ppn",
    "ppn_type": "ti_fp_ppn_type",
    "status": "ti_verification_status",
    "notes": "ti_verification_notes",
    "duplicate": "ti_duplicate_flag",
    "npwp_match": "ti_npwp_match",
    "pdf": "ti_tax_invoice_pdf",
    "ocr_status": "ti_ocr_status",
    "ocr_confidence": "ti_ocr_confidence",
    "ocr_raw_json": "ti_ocr_raw_json",
}

FIELDS_ER = {
    "fp_no": "ti_fp_no",
    "fp_date": "ti_fp_date",
    "npwp": "ti_fp_npwp",
    "dpp": "ti_fp_dpp",
    "ppn": "ti_fp_ppn",
    "ppn_type": "ti_fp_ppn_type",
    "status": "ti_verification_status",
    "notes": "ti_verification_notes",
    "duplicate": "ti_duplicate_flag",
    "npwp_match": "ti_npwp_match",
    "pdf": "ti_tax_invoice_pdf",
    "ocr_status": "ti_ocr_status",
    "ocr_confidence": "ti_ocr_confidence",
    "ocr_raw_json": "ti_ocr_raw_json",
}

FIELDS_BRANCH_ER = {
    "fp_no": "ti_fp_no",
    "fp_date": "ti_fp_date",
    "npwp": "ti_fp_npwp",
    "dpp": "ti_fp_dpp",
    "ppn": "ti_fp_ppn",
    "ppn_type": "ti_fp_ppn_type",
    "status": "ti_verification_status",
    "notes": "ti_verification_notes",
    "duplicate": "ti_duplicate_flag",
    "npwp_match": "ti_npwp_match",
    "pdf": "ti_tax_invoice_pdf",
    "ocr_status": "ti_ocr_status",
    "ocr_confidence": "ti_ocr_confidence",
    "ocr_raw_json": "ti_ocr_raw_json",
}

FIELDS_SI = {
    "fp_no": "out_fp_no",
    "fp_date": "out_fp_date",
    "npwp": "out_buyer_tax_id",
    "dpp": "out_fp_dpp",
    "ppn": "out_fp_ppn",
    "ppn_type": "out_fp_ppn_type",
    "status": "out_fp_status",
    "notes": "out_fp_verification_notes",
    "duplicate": "out_fp_duplicate_flag",
    "npwp_match": "out_fp_npwp_match",
    "pdf": "out_fp_pdf",
    "ocr_status": "out_fp_ocr_status",
    "ocr_confidence": "out_fp_ocr_confidence",
    "ocr_raw_json": "out_fp_ocr_raw_json",
}

METHODS = {
    "create_purchase_invoice_from_request": "imogi_finance.accounting.create_purchase_invoice_from_request",
    "verify_purchase_invoice_tax_invoice": "imogi_finance.api.tax_invoice.verify_purchase_invoice_tax_invoice",
    "verify_expense_request_tax_invoice": "imogi_finance.api.tax_invoice.verify_expense_request_tax_invoice",
    "verify_branch_expense_request_tax_invoice": "imogi_finance.api.tax_invoice.verify_branch_expense_request_tax_invoice",
    "verify_sales_invoice_tax_invoice": "imogi_finance.api.tax_invoice.verify_sales_invoice_tax_invoice",
    "generate_coretax_export": "imogi_finance.tax_operations.generate_coretax_export",
    "create_tax_payment_entry": "imogi_finance.imogi_finance.doctype.tax_payment_batch.tax_payment_batch.create_tax_payment_entry",
    "create_tax_payment_journal_entry": "imogi_finance.imogi_finance.doctype.tax_payment_batch.tax_payment_batch.create_tax_payment_journal_entry",
    "create_vat_netting_entry_for_closing": "imogi_finance.imogi_finance.doctype.tax_period_closing.tax_period_closing.create_vat_netting_entry_for_closing",
}

REPORTS = {
    "vat_input_verified": "imogi_finance.imogi_finance.report.vat_input_register_verified.vat_input_register_verified",
    "vat_output_verified": "imogi_finance.imogi_finance.report.vat_output_register_verified.vat_output_register_verified",
    "withholding_register": "imogi_finance.imogi_finance.report.withholding_register.withholding_register",
    "pb1_register": "imogi_finance.imogi_finance.report.pb1_register.pb1_register",
}
