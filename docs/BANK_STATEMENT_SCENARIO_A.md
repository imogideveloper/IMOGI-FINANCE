# Bank Statement Import - Scenario A (Native Integration)

## Overview

Menggunakan **native Frappe "Bank Statement Import"** dengan custom field `imogi_bank` untuk bank selection, dan hook ke Python logic untuk dynamic parsing berdasarkan bank configuration.

---

## Architecture

```
User membuka "Bank Statement Import" (native)
    ↓
    Isi: Company, Bank Account, imogi_bank (BCA/Mandiri/dll), Import File
    ↓
Click "Submit"
    ↓
Hook: bank_statement_import_before_submit()
    ↓
get_bank_config(imogi_bank) → Load config dari Bank Statement Bank List
    ↓
parse_csv_by_bank() → Parse dengan config (header_map, skip_markers, etc)
    ↓
Populate import_rows (native field)
    ↓
Native Bank Statement Import → Create Bank Transactions
```

---

## Setup

### 1. Load Fixtures
```bash
bench clear-cache
bench reload-doc imogi_finance "Bank Statement Bank List" "BCA"
```

### 2. Verify Custom Field
Native **Bank Statement Import** sekarang punya field:
- `imogi_bank` (Link to Bank)
- Required
- Visible di list view

### 3. Verify BCA Config
Buka **Bank Statement Bank List**:
- ✓ BCA entry sudah ada
- ✓ CSV Dialect: comma
- ✓ Date Format: dd-mm-yyyy
- ✓ Header Aliases: 8 entries
- ✓ Enabled: Yes

---

## User Workflow

### Step 1: Open Native Bank Statement Import
- Accounting → Bank Statement Import (native Frappe)

### Step 2: Fill Form
```
Company: [Select Company]
Bank Account: [Select Bank Account]
imogi_bank: BCA ← NEW FIELD (dropdown)
Import File: [Upload CSV]
Custom delimiters: [uncheck, config auto from imogi_bank]
```

### Step 3: Submit
- Click **Submit**
- System automatically:
  1. Load BCA config from Bank Statement Bank List
  2. Parse CSV with BCA header mapping
  3. Populate import_rows
  4. Create Bank Transactions (native)

---

## Files Modified/Created

| File | Status | Tujuan |
|------|--------|--------|
| `fixtures/custom_field.json` | ✅ UPDATE | Add `imogi_bank` custom field to native Bank Statement Import |
| `fixtures/bank_statement_bank_list.json` | ✅ CREATE | BCA config (auto-load) |
| `doctype/bank_statement_bank_list/...` | ✅ CREATE | Config DocType |
| `doctype/bank_statement_field_alias/...` | ✅ CREATE | Alias mapping DocType |
| `doctype/bca_bank_statement_import/bca_bank_statement_import.py` | ✅ CREATE | Python utility functions |
| `hooks/bank_statement_import.py` | ✅ CREATE | Hooks untuk native Bank Statement Import |
| `hooks.py` | ✅ UPDATE | Register hooks untuk Bank Statement Import |

---

## How It Works

### Hook 1: `bank_statement_import_on_before_insert()`
```python
- Validate imogi_bank field required
- Calculate file hash untuk duplicate detection
- Check apakah file sudah pernah di-import
```

### Hook 2: `bank_statement_import_before_submit()`
```python
- Load config dari Bank Statement Bank List menggunakan imogi_bank
- Parse CSV dengan header_map dari config
- Skip markers dari config
- Populate import_rows native field
- Set import_status = "Processed"
```

---

## Adding New Bank

Admin bisa menambah bank baru tanpa code:

1. **Bank Statement Bank List** → **+ New**
2. Fill:
   - **Bank**: Mandiri (atau bank baru)
   - **CSV Dialect**: comma/semicolon/tab
   - **Date Format**: dd-mm-yyyy/mm-dd-yyyy/yyyy-mm-dd
   - **Skip Markers**: pend,pending,saldo awal,...
   - **Amount Markers**: dr,cr,db,...
   - **Header Aliases** (table):
     ```
     posting_date → "Tanggal Posting,Tgl,Date,..."
     description → "Narasi,Keterangan,..."
     debit → "Debit,DEBIT,..."
     credit → "Kredit,KREDIT,..."
     balance → "Saldo,SALDO,..."
     (+ reference_number, currency, amount)
     ```
3. **Save**

Done! Users bisa select "Mandiri" di `imogi_bank` field sekarang.

---

## Key Features

✅ **Native Integration** - Pakai native Bank Statement Import (tidak custom DocType)  
✅ **Flexible Config** - Setiap bank bisa punya parsing rules berbeda  
✅ **Auto-Load Fixtures** - BCA config auto-load, user tidak perlu input manual  
✅ **Duplicate Detection** - Hash-based duplicate file detection  
✅ **Dynamic Header Mapping** - Header aliases dari config, bukan hardcoded  
✅ **Easy Extension** - Tambah bank baru di UI, tidak perlu code  

---

## Testing

### Test Case 1: Import BCA CSV
```
1. Open "Bank Statement Import"
2. Company: Test Company
3. Bank Account: BCA Account
4. imogi_bank: BCA
5. Upload: BCA_sample.csv
6. Submit
7. Verify: import_rows populated, Bank Transactions created
```

### Test Case 2: Add Mandiri Bank
```
1. Open "Bank Statement Bank List"
2. + New
3. Bank: Mandiri
4. CSV Dialect: semicolon
5. Header Aliases: (configure for Mandiri)
6. Save
7. Open Bank Statement Import
8. Select imogi_bank: Mandiri
9. Upload Mandiri CSV
10. Verify parsing works correctly
```

---

## Troubleshooting

### Error: "Bank is required"
- Fill `imogi_bank` field before submit

### Error: "Could not locate header row"
- Check CSV has proper header row
- Verify csv_dialect in Bank Statement Bank List matches file

### Error: "This file has already been imported"
- File hash matches existing import
- Use different file or check duplicate

### Error: "Bank Statement Bank List not found"
- Ensure Bank (e.g., BCA) exists in system
- Load fixtures: `bench reload-doc imogi_finance "Bank Statement Bank List" "BCA"`

---

## Comparison: Scenario A vs Other Approaches

| Aspect | Scenario A (Native) | Custom DocType | Hardcoded |
|--------|-------------------|-----------------|-----------|
| User Interface | Native Frappe | Custom | Custom |
| Config Flexibility | ✅ High (per bank) | ✅ High | ❌ Low |
| Code Maintenance | ✅ Easy (hooks) | ⚠️ Medium | ❌ Hard |
| Native Integration | ✅ Full | ❌ Partial | ❌ None |
| Fixture Auto-Load | ✅ Yes | ✅ Yes | ❌ No |
| Learning Curve | ✅ Easy | ⚠️ Medium | ❌ Steep |

---

## Summary

**Scenario A** adalah solusi terbaik karena:
- ✅ Leverage native Frappe Bank Statement Import
- ✅ Flexible config per bank (via Bank Statement Bank List)
- ✅ Dynamic parsing via hooks
- ✅ User-friendly (no custom DocType)
- ✅ Easy to maintain dan extend

