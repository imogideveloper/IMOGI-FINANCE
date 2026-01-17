# Tax Variance Handling - Pengelolaan Selisih Pajak OCR

## Overview

Ketika menggunakan Tax Invoice OCR, seringkali ada selisih (variance) antara nilai yang dibaca dari OCR dengan nilai yang dihitung dari Expense Request:

```
DPP dari OCR:        Rp 1,005,000  ← Dari scan faktur pajak
DPP Expected:        Rp 1,000,000  ← Dari total ER
Selisih (variance):  Rp     5,000  ← Perlu dicatat
```

Variance ini bisa terjadi karena:
- Pembulatan di faktur pajak
- Biaya tambahan yang tidak termasuk di ER items
- Kesalahan input di ER
- Kesalahan OCR reading

## Solusi: Variance sebagai Line Item Tambahan

Sistem secara otomatis menambahkan **DPP variance sebagai line item tambahan** di Purchase Invoice. Ini adalah approach yang paling simple dan efektif karena:

✅ Variance langsung masuk ke expense account
✅ PPN otomatis terhitung dari total (termasuk variance)
✅ Tidak perlu Journal Entry terpisah
✅ Audit trail jelas di PI items
✅ Supplier payable otomatis akurat

## Field Variance di Expense Request

Sistem otomatis menyimpan variance di field:

### 1. `ti_dpp_variance` (DPP Variance)
- **Type**: Currency
- **Formula**: `OCR DPP - Expected DPP`
- **Bisa positif atau negatif**
- **Contoh**:
  - OCR: Rp 1,005,000, Expected: Rp 1,000,000 → Variance: **+Rp 5,000**
  - OCR: Rp 995,000, Expected: Rp 1,000,000 → Variance: **-Rp 5,000**

### 2. `ti_ppn_variance` (PPN Variance)
- **Type**: Currency
- **Formula**: `OCR PPN - Expected PPN`
- **Bisa positif atau negatif**
- **Contoh**:
  - OCR: Rp 110,550, Expected: Rp 110,000 → Variance: **+Rp 550**
  - OCR: Rp 109,450, Expected: Rp 110,000 → Variance: **-Rp 550**

## Konfigurasi Variance Account

Di **Tax Invoice OCR Settings**, konfigurasikan account untuk mencatat variance:

### DPP Variance Account
- **Path**: Tax Invoice OCR Settings → DPP Variance Account
- **Recommended**: Expense account atau "Misc Expense" account
- **Example**: "5990 - Miscellaneous Expenses" atau "5991 - Tax Adjustments"
- **Purpose**: Untuk mencatat selisih DPP sebagai line item di PI

⚠️ **Penting**: Jika DPP Variance Account tidak dikonfigurasi, variance **tidak akan ditambahkan** sebagai line item dan nilai PI akan tidak match dengan faktur pajak.

## Cara Kerja: Variance sebagai Line Item

Ketika Purchase Invoice dibuat dari Expense Request:

### 1. Sistem Check Variance
```python
dpp_variance = ER.ti_dpp_variance  # Sudah dihitung saat ER submit
if dpp_variance != 0:
    # Tambahkan line item untuk variance
```

### 2. Line Item Otomatis Ditambahkan

**Contoh: Variance Positif (+Rp 5,000)**

Purchase Invoice Items:
```
No  Description                    Account              Qty  Rate          Amount
─────────────────────────────────────────────────────────────────────────────────
1   Office Supplies               5130 - Expense         1   1,000,000   1,000,000
2   DPP Variance Adjustment       5990 - Misc Expense    1       5,000       5,000  ← Auto
─────────────────────────────────────────────────────────────────────────────────
Total Items:                                                            1,005,000
PPN 11%:                                                                  110,550  ← Auto calc
PPh 23 2%:                                                                (20,000) ← Auto calc
─────────────────────────────────────────────────────────────────────────────────
Grand Total:                                                            1,095,550  ✅
```

**Contoh: Variance Negatif (-Rp 5,000)**

Purchase Invoice Items:
```
No  Description                    Account              Qty  Rate          Amount
─────────────────────────────────────────────────────────────────────────────────
1   Office Supplies               5130 - Expense         1   1,000,000   1,000,000
2   DPP Variance Reduction        5990 - Misc Expense    1      -5,000      -5,000  ← Auto
─────────────────────────────────────────────────────────────────────────────────
Total Items:                                                              995,000
PPN 11%:                                                                  109,450  ← Auto calc
PPh 23 2%:                                                                (20,000) ← Auto calc
─────────────────────────────────────────────────────────────────────────────────
Grand Total:                                                            1,084,450  ✅
```

### 3. GL Entry Otomatis (Standard ERPNext)

Saat PFully Implemented:
1. ✅ Field `ti_dpp_variance` dan `ti_ppn_variance` di Expense Request
2. ✅ Variance otomatis dihitung saat validate ER
3. ✅ Field `dpp_variance_account` di Tax Invoice OCR Settings
4. ✅ **Variance otomatis ditambahkan sebagai line item di PI**
5. ✅ Variance di-copy ke PI fields untuk reference
6. ✅ PPN otomatis terhitung dari total (termasuk variance)
7. ✅ GL entry otomatis via standard ERPNext flow

### 🎯 No Custom Code Needed:
- Tidak perlu Journal Entry terpisah
- Tidak perlu custom GL posting logic
- Semua menggunakan standard ERPNext Purchase Invoice flow

## Contoh Kasus Lengkap

### Scenario: ER dengan Variance Positif

**Expense Request:**
- Item: Office Supplies - Rp 1,000,000
- PPN Template: 11%
- PPh 23 2% applicable pada Rp 1,000,000

**OCR Reading:**
- DPP (OCR): Rp 1,005,000 → Variance: **+Rp 5,000**
- PPN (OCR): Rp 110,550

**Saat Create PI dari ER:**

1. **System otomatis create 2 line items:**
   ```
   Item 1: Office Supplies
   - Account: 5130 - Expense
   - Amount: Rp 1,000,000
   
   Item 2: DPP Variance Adjustment  ← AUTO ADDED
   - Account: 5990 - Misc Expense
   - Amount: Rp 5,000
   - Description: "Tax invoice variance adjustment (OCR vs Expected): 5,000.00"
   ```

2. **Total & Taxes auto-calculated:**
   ```
   Total Items:    Rp 1,005,000  (1,000,000 + 5,000)
   PPN 11%:        Rp   110,550  (11% dari 1,005,000) ✅ Match dengan OCR
   PPh 23 2%:     -Rp    20,000  (2% dari 1,000,000 base)
   Grand Total:    Rp 1,095,550  ✅ Match dengan faktur pajak
   ```

3. **GL Entry (saat PI submit):**
   ```
   Dr. 5130 - Expense              1,000,000
   Dr. 5990 - Misc Expense             5,000  ← Variance
   Dr. 2110 - PPN Input              110,550
   Cr. 2120 - PPh 23 Payable          20,000
   Cr. 2100 - Supplier Payable     1,095,550
   ```

### Scenario: ER dengan Variance Negatif

**Expense Request:**
- Item: Consulting Fee - Rp 1,000,000

**OCR Reading:**
- DPP (OCR): Rp 995,000 → Variance: **-Rp 5,000**
- PPN (OCR): Rp 109,450

**Saat Create PI:**

1. **Line items:**
   ```
   Item 1: Consulting Fee - Rp 1,000,000
   Item 2: DPP Variance Reduction - Rp -5,000  ← AUTO (negative)
   ```

2. **Totals:**
   ```
   Total Items:    Rp 995,000   (1,000,000 - 5,000)
   PPN 11%:        Rp 109,450   ✅ Match dengan OCR
   Grand Total:    Rp 1,104,450
   ```

3. **GL Entry:**
   ```
   Dr. 5130 - Expense              1,000,000
   Cr. 5990 - Misc Expense             5,000  ← Variance (credit = reduce)
   Dr. 2110 - PPN Input              109,450
   Cr. 2100 - Supplier Payable     1,104,450xpense_request=request)
        if je_name:
            frappe.msgprint(
                f"Variance adjustment posted: {je_name}",
                indicator="blue",
                alert=True
            )
    except Exception as e:
        # Log error but don't block PI submit
        frappe.log_error(
            title=f"Variance JE Failed for PI {doc.name}",
            message=f"Error: {str(e)}\n\n{frappe.get_traceback()}"
        )
    
    maybe_post_internal_charge_je(doc, expense_request=request)
```

## Contoh Kasus Lengkap

### Scenario: ER dengan Variance Positif

**Expense Request:**
- Total Expense: Rp 1,000,000
- PPN Template: 11%
- PPh 23 2% applicable

**OCR Reading:**
- DPP (OCR): Rp 1,005,000 → Variance: **+Rp 5,000**
- PPN (OCR): Rp 110,550 → Variance: **+Rp 550** (11% dari 1,005,000)

**Purchase Invoice Submit:**

1. **PI Normal GL Entry** (via ERPNext standard):
   ```
   Dr. Expense Account          1,000,000
   Dr. PPN Input                  110,550  ← Dari OCR
   Cr. PPh 23 Payable              20,000
   Cr. Supplier Payable         1,090,550
   ```

2. **Variance Adjustment JE** (via custom function):
   ```
   Dr. DPP Variance Account       5,000  ← Selisih DPP
   Dr. PPN Variance Account         550  ← Selisih PPN
   Cr. Supplier Payable           5,550  ← Total variance
   ```

3. **Net Result**:
   ```
   Total Expense:    Rp 1,000,000 + Rp 5,000 = Rp 1,005,000 ✅
   Total PPN Input:  Rp 110,550 ✅
   Total Payable:    Rp 1,090,550 + Rp 5,550 = Rp 1,096,100 ✅
                    (sesuai dengan OCR faktur pajak)
   ```

## Best Practices

### 1. Konfigurasikan DPP Variance Account
```
Tax Invoice OCR Settings → DPP Variance Account
Recommended: "5990 - Miscellaneous Expenses"
```

Tanpa account ini, variance **tidak akan ditambahkan** dan PI amount akan berbeda dari faktur pajak.

### 2. Set Tolerance yang Masuk Akal
```python
# Tax Invoice OCR Settings
tolerance_idr = 10000  # Rp 10,000
tolerance_percentage = 1.0  # 1%
```

Variance **dalam toleransi** akan diizinkan tapi tetap dicatat untuk audit.

### 3. Review Line Items di PI
Sebelum submit PI, check:
- ✅ Ada line item "DPP Variance Adjustment"?
- ✅ Amount variance sesuai dengan yang expected?
- ✅ Total PI match dengan faktur pajak OCR?

### 4. Monitor Variance Patterns
Buat custom report untuk track:
- Total variance per bulan
- Supplier dengan variance tinggi
- Pattern variance (selalu positif/negatif?)

### 5. Edit Line Item Jika Perlu
Line item variance bisa di-edit manual:
- Ubah description untuk lebih jelas
- Adjust amount jika ada correction
- Change account jika perlu classification berbeda

## FAQ

### Q: Apakah variance mempengaruhi PPh calculation?
**A**: Tidak. PPh dihitung dari `pph_base_amount` di ER items yang applicable, bukan dari total (termasuk variance).

### Q: Bagaimana jika DPP variance account tidak dikonfigurasi?
**A**: Variance **tidak akan ditambahkan** sebagai line item. PI total akan sama dengan ER total (tidak match dengan faktur pajak).

### Q: Apakah variance boleh negatif?
**A**: Ya. Variance negatif artinya OCR lebih kecil dari expected, line item amount akan negatif (mengurangi total).

### Q: Apakah line item variance bisa diedit?
**A**: Ya, sebelum submit. Description, amount, dan account bisa diubah manual jika diperlukan.

### Q: Apakah variance account harus expense account?
**A**: Tidak harus, tapi recommended. Bisa juga pakai account khusus seperti "Tax Adjustments" atau "Variance Account".

### Q: Bagaimana jika variance sangat besar?
**A**: Review dulu:
1. Apakah ada missing items di ER?
2. Apakah OCR reading correct?
3. Apakah faktpajak match dengan ER?
4. Jika valid, proceed dan document reason di notes.

### Q: Bagaimana dengan Branch Expense Request?
**A**: Sama. BER juga punya field `ti_dpp_variance`, implementasi sama dengan ER.

### Q: Apakah PPN variance juga ditambahkan sebagai line item?
**A**: Tidak perlu. PPN variance akan **otomatis ter-adjust** karena PPN dihitung dari total items (yang sudah termasuk DPP variance). Jadi PPN final akan otomatis match dengan OCR.

## Kesimpulan

Dengan approach **variance sebagai line item**, sistem menjadi:

1. ✅ **Lebih simple** - Tidak perlu Journal Entry terpisah
2. ✅ **Lebih akurat** - Total PI otomatis match dengan faktur pajak
3. ✅ **Lebih transparan** - Variance jelas terlihat sebagai line item
4. ✅ **Lebih flexible** - Line item bisa di-edit manual jika perlu
5. ✅ **Standard ERPNext** - Menggunakan flow normal, tidak ada custom GL posting

Variance handling memastikan bahwa:
- ✅ **Nilai GL match dengan faktur pajak** (untuk audit dan rekonsiliasi)
- ✅ **Expense breakdown jelas** (expense asli + variance terpisah)
- ✅ **Variance tercatat** (untuk analysis dan investigation)
- ✅ **Supplier payable akurat** (sesuai faktur pajak)

---

**Last Updated**: January 17, 2026
**Status**: ✅ Fully Implemented
**Approach**: Variance as additional line item in Purchase Invoice
