# Tax Invoice OCR - Manual Upload Field Fix

## Problem
Ketika Tax Invoice OCR diaktifkan di **Tax Invoice OCR Settings**, field manual tax invoice (Tax Invoice No, Tax Invoice Date, Tax Invoice File) masih muncul di Expense Request. Ini membingungkan user karena seharusnya hanya menggunakan OCR Upload saja ketika OCR diaktifkan.

## Solution
### 1. Expense Request
Menambahkan kondisi `depends_on` pada field manual tax invoice untuk menyembunyikan mereka ketika OCR diaktifkan:

**File Modified:** `expense_request.json`
- Field `tax_invoice_number` → `depends_on: "eval:doc.is_ppn_applicable && !doc.__ocr_enabled"`
- Field `tax_invoice_date` → `depends_on: "eval:doc.is_ppn_applicable && !doc.__ocr_enabled"`  
- Field `tax_invoice_attachment` → `depends_on: "eval:doc.is_ppn_applicable && !doc.__ocr_enabled"`
- Label diubah menjadi "Tax Invoice No (Manual)", "Tax Invoice Date (Manual)", "Tax Invoice File (Manual)" untuk kejelasan

**File Modified:** `expense_request.js`
- Menambahkan function `checkOcrEnabled()` untuk mengecek status OCR dari settings
- Memanggil `checkOcrEnabled()` pada `refresh()` dan `is_ppn_applicable()` events
- Function ini mengset `frm.doc.__ocr_enabled` yang digunakan oleh `depends_on` condition

### 2. Branch Expense Request  
Branch Expense Request tidak memiliki field manual tax invoice (sudah dari awal dirancang hanya untuk OCR), tetapi ditambahkan function `checkOcrEnabledBer()` untuk konsistensi dan kemungkinan penggunaan di masa depan.

**File Modified:** `branch_expense_request.js`
- Menambahkan function `checkOcrEnabledBer()`
- Memanggil function pada `refresh()` event

### 3. Purchase Invoice
Purchase Invoice sudah tidak memiliki field manual tax invoice dan sudah sepenuhnya menggunakan OCR, sehingga tidak perlu perubahan.

## Behavior
### Ketika OCR Enabled (enable_tax_invoice_ocr = 1):
- ✅ Field "Tax Invoice OCR Upload" muncul
- ✅ Field OCR Data muncul (FP No, FP Date, dll - read-only)
- ❌ Field manual tax invoice (Manual) **disembunyikan**

### Ketika OCR Disabled (enable_tax_invoice_ocr = 0):
- ❌ Field "Tax Invoice OCR Upload" tidak muncul  
- ❌ Field OCR Data tidak muncul
- ✅ Field manual tax invoice (Manual) **muncul**

## Testing Checklist
- [ ] Aktifkan Tax Invoice OCR Settings
- [ ] Buka Expense Request baru
- [ ] Centang "Apply PPN"
- [ ] Verify: Manual tax invoice fields TIDAK muncul
- [ ] Verify: OCR Upload field muncul
- [ ] Nonaktifkan Tax Invoice OCR Settings
- [ ] Refresh Expense Request
- [ ] Verify: Manual tax invoice fields muncul
- [ ] Verify: OCR Upload field tidak muncul

## Files Changed
1. `/imogi_finance/imogi_finance/doctype/expense_request/expense_request.json`
2. `/imogi_finance/imogi_finance/doctype/expense_request/expense_request.js`
3. `/imogi_finance/imogi_finance/doctype/branch_expense_request/branch_expense_request.js`

## Related Documentation
See [TAX_INVOICE_OCR_VALIDATION_BEFORE_SUBMIT.md](TAX_INVOICE_OCR_VALIDATION_BEFORE_SUBMIT.md) for validation logic before submit.

## Date
January 16, 2026
