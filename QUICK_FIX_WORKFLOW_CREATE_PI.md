# Quick Fix: Workflow Actions "Create PI" & "Mark Paid" Tidak Bekerja

## Masalah
- Klik workflow action **"Create PI"** → Status berubah → **Purchase Invoice tidak terbentuk**

## Penyebab
Workflow hanya mengubah status, tidak memanggil fungsi untuk membuat PI.

## Solusi yang Sudah Diimplementasikan

### Perubahan Kode
1. **Handler otomatis untuk "Create PI"**
   - Memanggil fungsi create PI yang sebenarnya
   - Update field linked_purchase_invoice
   - Handle error dengan jelas

2. **Status "Paid" otomatis dari Payment Entry**
   - Hook di payment_entry.py on_submit
   - Status berubah ke "Paid" ketika Payment Entry di-submit
   - Tidak ada workflow action manual

3. **Validasi ketat di on_workflow_action**
   - Status "PI Created" hanya bisa terjadi jika PI benar-benar ada
   - Status "Paid" hanya bisa terjadi dari "PI Created" dengan PI yang valid
   - Mencegah bypass manual

### File yang Diubah
- ✅ `expense_request.py` (handler + validasi)
- ✅ `expense_request_workflow.json` (dokumentasi)
- ✅ `test_expense_request_workflow.py` (unit tests)
- ✅ Dokumentasi lengkap di `docs/workflow_create_pi_fix.md`

## Cara Pakai (Untuk User)

### Langkah Benar
1. Pastikan ER status **"Approved"**
2. Pastikan **semua requirement terpenuhi**:
   - Budget sudah locked (jika enforce aktif)
   - Tax invoice sudah Verified (jika setting require_verification aktif)
   - IC Request sudah dibuat (jika allocation mode "Internal Charge")
3. Klik workflow action **"Create PI"**
4. Jika berhasil → PI terbentuk + status berubah
5. Jika gagal → Error message jelas + status tidak berubah

### Error Messages Umum

| Error | Penyebab | Solusi |
|-------|----------|--------|
| "Tax Invoice must be verified..." | Tax invoice belum Verified | Verify tax invoice dulu |
| "Budget must be locked..." | Budget belum locked | Lock budget dulu |
| "IC Request required..." | Belum ada IC Request | Buat IC Request dulu |
| "Already has draft Purchase Invoice..." | Ada PI draft | Submit/cancel PI draft yang ada |

### Alternative: Tombol di Form
Selain workflow action, bisa juga pakai tombol **"Create Purchase Invoice"** di dashboard ER.
Hasilnya sama.

### Status "Paid" Otomatis
Status berubah ke **"Paid"** secara otomatis ketika:
1. Payment Entry dibuat dengan link ke Expense Request
2. Payment Entry di-submit
3. Hook di `payment_entry.py` otomatis update status ER ke "Paid"

## Untuk ER yang Bermasalah (Status "PI Created" tapi Tidak Ada PI)

### Fix Manual
1. **Reopen** ER ke status "Approved"
   - Gunakan action "Reopen" (jika allowed) atau
   - Minta System Manager untuk ubah status
2. Pastikan semua requirement terpenuhi
3. Klik **"Create PI"** lagi
4. Verifikasi PI terbentuk

## Testing Checklist

### Development/Staging
- [ ] Test happy path (semua requirement OK)
- [ ] Test error handling (budget not locked)
- [ ] Test error handling (tax invoice not verified)
- [ ] Test validation (manual status change prevented)
- [ ] Cek error logs

### Production
- [ ] Deploy code
- [ ] Monitor error logs 24-48 jam
- [ ] Training user jika perlu
- [ ] Dokumentasi SOP

## Status
✅ **Code Ready**  
⏳ Pending: Testing & Deployment

## Need Help?
Lihat dokumentasi lengkap di:
- `docs/workflow_create_pi_fix.md` (detail teknis)
- `WORKFLOW_FIX_SUMMARY.md` (summary untuk developer)

---
**Last Updated**: 12 Januari 2026
