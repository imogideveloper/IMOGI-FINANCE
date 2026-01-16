# Tax Invoice OCR Validation Before Submit

## Problem
Ketika user submit Expense Request atau Branch Expense Request dengan Tax Invoice OCR Upload, tidak ada validasi untuk memastikan:
1. NPWP dari OCR sesuai dengan NPWP Supplier (Tax ID)
2. DPP, PPN, dan PPnBM dari OCR sesuai dengan nilai yang dihitung dari expense request (dalam toleransi)

Validasi seharusnya dilakukan **sebelum submit**, bukan sebelum save, agar user bisa memperbaiki data tanpa mengubah status dokumen.

## Solution

### 1. Validasi NPWP
Membandingkan NPWP yang di-scan oleh OCR (`ti_fp_npwp`) dengan Tax ID Supplier. Kedua nilai di-normalize terlebih dahulu (menghapus karakter non-digit) sebelum dibandingkan.

**Error jika:** NPWP tidak match

### 2. Validasi DPP
Membandingkan DPP dari OCR (`ti_fp_dpp`) dengan Total Expense (`amount`) dari Expense Request.

**Error jika:** Selisih > toleransi (default: IDR 10)

**Catatan:** DPP biasanya sama dengan total expense sebelum pajak. Namun ada kasus dimana DPP bisa berbeda karena:
- Pembulatan oleh vendor
- Biaya tambahan yang tidak tercatat
- Error OCR

Maka dari itu kita gunakan **tolerance** untuk mengakomodasi selisih kecil.

### 3. Validasi PPN
Membandingkan PPN dari OCR (`ti_fp_ppn`) dengan PPN yang dihitung dari DPP × rate% (rate dari PPN template).

**Expected PPN = Total Expense × PPN Rate / 100**

Default rate = 11% (bisa berbeda sesuai template)

**Error jika:** Selisih > toleransi (default: IDR 10)

**Catatan:** PPN calculation bisa berbeda karena:
- Vendor menggunakan pembulatan yang berbeda
- DPP di faktur pajak berbeda dengan total expense
- Rate PPN berbeda (misal: zero-rated, exempt)

### 4. Validasi PPnBM
Saat ini belum ada validasi khusus untuk PPnBM karena jarang digunakan. Akan ditambahkan jika diperlukan.

## Implementation

### Expense Request
**File:** `/imogi_finance/imogi_finance/doctype/expense_request/expense_request.py`

```python
def before_submit(self):
    """Prepare for submission - resolve approval route and initialize state."""
    self.validate_submit_permission()
    
    # Validate tax invoice OCR data if OCR is enabled and applicable
    self.validate_tax_invoice_ocr_before_submit()
    
    # ... existing code ...
```

**New Method:**
```python
def validate_tax_invoice_ocr_before_submit(self):
    """Validate tax invoice OCR data before submit: NPWP, DPP, PPN, PPnBM."""
```

### Branch Expense Request
**File:** `/imogi_finance/imogi_finance/doctype/branch_expense_request/branch_expense_request.py`

```python
def before_submit(self):
    # ... existing validations ...
    
    # Validate tax invoice OCR data if OCR is enabled and applicable
    self.validate_tax_invoice_ocr_before_submit()
    
    # ... existing code ...
```

**New Method:**
```python
def validate_tax_invoice_ocr_before_submit(self):
    """Validate tax invoice OCR data before submit: NPWP, DPP, PPN, PPnBM."""
```

## Validation Flow

```
Submit Clicked
    ↓
before_submit()
    ↓
validate_tax_invoice_ocr_before_submit()
    ↓
Check: OCR enabled? → No → Skip validation
    ↓ Yes
Check: Has OCR Upload? → No → Skip validation
    ↓ Yes
Check: PPN applicable? → No → Skip validation
    ↓ Yes
Validate NPWP
    ↓
Validate DPP (with tolerance)
    ↓
Validate PPN (with tolerance)
    ↓
All OK? → Continue submit
    ↓
Error? → Throw error with details
```

## Error Message Format

Jika ada error, sistem akan menampilkan pesan seperti:

```
Validasi Faktur Pajak Gagal:
• NPWP dari OCR (12.345.678.9-012.000) tidak sesuai dengan NPWP Supplier (98.765.432.1-098.000)
• DPP dari OCR (Rp 10,500,000) berbeda dengan Total Expense (Rp 10,000,000). Selisih: Rp 500,000 (toleransi: Rp 10)
• PPN dari OCR (Rp 1,155,000) berbeda dengan PPN yang dihitung (Rp 1,100,000). Selisih: Rp 55,000 (toleransi: Rp 10)
```

## Configuration

Tolerance untuk validasi DPP dan PPN dikonfigurasi di **Tax Invoice OCR Settings**:
- Field: `tolerance_idr`
- Default: `10` (IDR 10)

Untuk mengubah tolerance:
1. Buka Tax Invoice OCR Settings
2. Edit field "Tolerance (IDR)"
3. Save

## Skip Conditions

Validasi akan di-skip jika:
1. OCR tidak diaktifkan (`enable_tax_invoice_ocr = 0`)
2. Tidak ada Tax Invoice OCR Upload yang di-link
3. PPN tidak applicable (`is_ppn_applicable = 0`)
4. Tidak ada supplier (untuk validasi NPWP)

## Testing

### Test Case 1: Valid OCR Data
**Given:**
- OCR enabled
- OCR Upload linked
- PPN applicable
- NPWP match
- DPP match (within tolerance)
- PPN match (within tolerance)

**Expected:** Submit success

### Test Case 2: NPWP Mismatch
**Given:**
- NPWP di OCR: 12.345.678.9-012.000
- NPWP Supplier: 98.765.432.1-098.000

**Expected:** Submit blocked with error message

### Test Case 3: DPP Exceeds Tolerance
**Given:**
- DPP OCR: 10,500,000
- Total Expense: 10,000,000
- Tolerance: 10
- Selisih: 500,000

**Expected:** Submit blocked with error message

### Test Case 4: PPN Exceeds Tolerance
**Given:**
- PPN OCR: 1,155,000
- PPN Calculated: 1,100,000
- Tolerance: 10
- Selisih: 55,000

**Expected:** Submit blocked with error message

### Test Case 5: Within Tolerance
**Given:**
- DPP OCR: 10,000,005
- Total Expense: 10,000,000
- Tolerance: 10
- Selisih: 5

**Expected:** Submit success (within tolerance)

## Future Enhancements

1. **PPnBM Validation**: Add specific validation for luxury tax if needed
2. **Configurable Tolerance Percentage**: Allow tolerance as percentage instead of fixed amount
3. **Warning Mode**: Option to show warning instead of blocking submit
4. **Override Permission**: Allow certain roles to override validation errors
5. **Detailed Logging**: Log all validation attempts for audit trail

## Files Modified
1. `/imogi_finance/imogi_finance/doctype/expense_request/expense_request.py`
2. `/imogi_finance/imogi_finance/doctype/branch_expense_request/branch_expense_request.py`

## Date
January 16, 2026
