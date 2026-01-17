# Customer Receipt - Before/After Billing Implementation

## Overview
Modul Customer Receipt telah diperbaiki untuk memastikan pilihan "Before Billing" dan "After Billing" berfungsi dengan benar dengan auto-fetch data dari dokumen terkait.

## Fitur yang Diimplementasikan

### 1. Pilihan Receipt Purpose
- **Before Billing (Sales Order)**: Untuk menerima pembayaran sebelum invoice dibuat
  - Hanya mengisi field `Sales Order`
  - Fetch data dari Sales Order (customer, company, transaction date, grand total, advance paid)
  - Calculate outstanding: grand_total - advance_paid
  
- **Billing (Sales Invoice)**: Untuk menerima pembayaran setelah invoice dibuat
  - Hanya mengisi field `Sales Invoice`
  - Fetch data dari Sales Invoice (customer, company, posting date, outstanding amount)
  - Outstanding langsung dari field outstanding_amount

### 2. Auto-Fetch Data
Ketika user memilih Sales Order atau Sales Invoice, sistem otomatis mengambil data:
- **Customer**: Divalidasi harus sama dengan Customer di header
- **Company**: Divalidasi harus sama dengan Company di header  
- **Reference Date**: Transaction date (SO) atau Posting date (SI)
- **Reference Outstanding**: Sisa yang belum dibayar
- **Amount to Collect**: Otomatis diisi dengan outstanding amount

### 3. Validasi
#### Client-side (JavaScript):
- Clear items ketika Receipt Purpose berubah
- Clear items ketika Customer atau Company berubah
- Filter Sales Order/Invoice hanya menampilkan yang sesuai customer & company
- Validasi dokumen harus sudah submitted
- Validasi customer & company harus match
- Auto-clear field yang tidak sesuai receipt purpose

#### Server-side (Python):
- Validasi hanya satu jenis reference yang boleh diisi per row
- Validasi Sales Invoice wajib diisi jika "Billing (Sales Invoice)"
- Validasi Sales Order wajib diisi jika "Before Billing (Sales Order)"
- Validasi amount to collect tidak boleh melebihi outstanding
- Validasi customer & company harus match dengan header

## Files Modified

### 1. customer_receipt.js (NEW)
File JavaScript baru untuk handle client-side logic:
- Event handlers untuk receipt_purpose, customer, company changes
- Auto-fetch data dari Sales Invoice
- Auto-fetch data dari Sales Order
- Query filters untuk dropdown
- Validasi client-side

### 2. customer_receipt_item.js (NEW)
Placeholder file untuk child table

### 3. customer_receipt_item.json (UPDATED)
- Added `mandatory_depends_on` untuk Sales Invoice dan Sales Order
- Memastikan field wajib diisi sesuai receipt purpose

### 4. customer_receipt.py (UPDATED)
- Enhanced `validate_items()` method dengan validasi tambahan:
  - Cek bahwa hanya satu jenis reference yang diisi
  - Validasi field wajib berdasarkan receipt purpose
  - Error messages yang lebih jelas dengan row number

## Usage Guide

### Membuat Customer Receipt - Before Billing

1. Buat Customer Receipt baru
2. Pilih **Company** dan **Customer**
3. Pilih **Receipt Purpose**: "Before Billing (Sales Order)"
4. Klik "Add Row" di tabel Items
5. Pilih **Sales Order** (hanya Sales Order yang muncul dengan outstanding > 0)
6. Data otomatis terisi:
   - Reference Date dari transaction date
   - Reference Outstanding = grand_total - advance_paid
   - Amount to Collect = reference outstanding
7. Adjust amount to collect jika perlu
8. Save dan Submit

### Membuat Customer Receipt - After Billing

1. Buat Customer Receipt baru
2. Pilih **Company** dan **Customer**
3. Pilih **Receipt Purpose**: "Billing (Sales Invoice)"
4. Klik "Add Row" di tabel Items
5. Pilih **Sales Invoice** (hanya Sales Invoice dengan outstanding > 0)
6. Data otomatis terisi:
   - Reference Date dari posting date
   - Reference Outstanding dari outstanding_amount
   - Amount to Collect = reference outstanding
7. Adjust amount to collect jika perlu
8. Save dan Submit

## Validation Rules

### Before Billing (Sales Order)
✅ **Allowed**: Fill Sales Order only
❌ **Not Allowed**: Fill Sales Invoice
❌ **Not Allowed**: Leave Sales Order empty

### After Billing (Sales Invoice)
✅ **Allowed**: Fill Sales Invoice only
❌ **Not Allowed**: Fill Sales Order
❌ **Not Allowed**: Leave Sales Invoice empty

### Common Validations
- Document harus submitted (docstatus = 1)
- Customer harus match dengan Customer Receipt
- Company harus match dengan Customer Receipt
- Amount to Collect tidak boleh > Reference Outstanding
- Minimum 1 item harus diisi

## Testing

### Test Case 1: Before Billing
```
1. Create Sales Order dengan customer "ABC Ltd" dan grand_total 10,000,000
2. Create Customer Receipt:
   - Customer: ABC Ltd
   - Receipt Purpose: Before Billing (Sales Order)
   - Add item dengan Sales Order yang baru dibuat
3. Expected: Reference Outstanding = 10,000,000
4. Expected: Amount to Collect auto-filled = 10,000,000
5. Try to fill Sales Invoice → Should be hidden/cleared
6. Submit → Success
```

### Test Case 2: After Billing
```
1. Create Sales Invoice dengan customer "XYZ Corp" dan outstanding 5,000,000
2. Create Customer Receipt:
   - Customer: XYZ Corp
   - Receipt Purpose: Billing (Sales Invoice)
   - Add item dengan Sales Invoice yang baru dibuat
3. Expected: Reference Outstanding = 5,000,000
4. Expected: Amount to Collect auto-filled = 5,000,000
5. Try to fill Sales Order → Should be hidden/cleared
6. Submit → Success
```

### Test Case 3: Validation Errors
```
1. Create Customer Receipt with "Before Billing"
2. Manually try to fill Sales Invoice → Should show error
3. Change to "After Billing" 
4. Items should be cleared
5. Try to save without items → Error
```

## Benefits

1. **User Experience**: Auto-fetch data mengurangi manual entry
2. **Data Integrity**: Validasi memastikan consistency
3. **Error Prevention**: Clear field yang tidak sesuai otomatis
4. **Clarity**: User jelas field mana yang harus diisi
5. **Filtering**: Dropdown hanya tampilkan dokumen yang relevan

## Migration Notes

Tidak ada migration diperlukan karena:
- Struktur database tidak berubah
- Hanya menambahkan JavaScript files
- Update Python validation (backward compatible)
- Update JSON metadata (backward compatible)

## Next Steps

1. Test di development environment
2. Reload DocTypes:
   ```bash
   bench --site [site-name] reload-doc imogi_finance "DocType" "Customer Receipt"
   bench --site [site-name] reload-doc imogi_finance "DocType" "Customer Receipt Item"
   ```
3. Clear cache:
   ```bash
   bench --site [site-name] clear-cache
   ```
4. Test dengan real data
5. Deploy to production

## Support

Jika ada masalah:
1. Clear browser cache
2. Hard refresh (Ctrl+Shift+R atau Cmd+Shift+R)
3. Check browser console untuk JavaScript errors
4. Check Frappe logs untuk Python errors
5. Verify DocType sudah di-reload
