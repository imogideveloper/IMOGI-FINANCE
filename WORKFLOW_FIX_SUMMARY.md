# Summary Perbaikan: Workflow "Create PI" Tidak Membuat Purchase Invoice

## Masalah
Ketika user mengklik action workflow **"Create PI"** di Expense Request:
- Status berubah ke "PI Created" ✓
- Timeline menunjukkan "Administrator PI Created" ✓
- **Tetapi Purchase Invoice tidak terbentuk** ✗
- Field `linked_purchase_invoice` tetap kosong ✗

## Root Cause
Workflow transition dari "Approved" → "PI Created" dengan action "Create PI" **hanya mengubah status**, tidak memanggil fungsi `accounting.create_purchase_invoice_from_request()` yang sebenarnya membuat dokumen PI.

## Solusi Implementasi

### File yang Diubah

1. **`imogi_finance/imogi_finance/doctype/expense_request/expense_request.py`**
   - ✅ Tambahkan handler di `before_workflow_action()` untuk action "Create PI"
     - Memanggil `accounting.create_purchase_invoice_from_request()`
     - Update `linked_purchase_invoice` dan `pending_purchase_invoice`
     - Handle error dengan message yang jelas
   
   - ✅ Tambahkan validasi di `on_workflow_action()` untuk state "PI Created"
     - Memastikan `linked_purchase_invoice` tidak kosong
     - Throw error jika PI belum ada tapi status mau diubah ke "PI Created"

2. **`imogi_finance/imogi_finance/workflow/expense_request_workflow/expense_request_workflow.json`**
   - ✅ Update field `notes` untuk dokumentasi bahwa action "Create PI" otomatis membuat PI

3. **`imogi_finance/tests/test_expense_request_workflow.py`** (baru)
   - ✅ Test `test_workflow_action_create_pi_calls_accounting_method`
   - ✅ Test `test_workflow_action_create_pi_throws_on_failure`
   - ✅ Test `test_on_workflow_action_validates_pi_created_state`
   - ✅ Test `test_workflow_prevents_manual_status_change_to_pi_created`

4. **`docs/workflow_create_pi_fix.md`** (baru)
   - ✅ Dokumentasi lengkap tentang fix
   - ✅ Panduan untuk user
   - ✅ Troubleshooting error messages
   - ✅ Checklist deployment

## Cara Kerja Sekarang

### Sebelum Fix
```
User klik "Create PI" → Workflow transition → Status berubah → SELESAI (PI tidak dibuat)
```

### Setelah Fix
```
User klik "Create PI" 
  → before_workflow_action() dipanggil
  → accounting.create_purchase_invoice_from_request() dijalankan
  → PI dibuat dan disimpan
  → linked_purchase_invoice diisi
  → on_workflow_action() validasi PI ada
  → Status berubah ke "PI Created"
  → SELESAI (PI berhasil dibuat)
```

## Testing

### Syntax Check
```bash
✓ python3 -m py_compile imogi_finance/imogi_finance/doctype/expense_request/expense_request.py
  (No errors)
```

### Unit Tests
Tests sudah dibuat di `test_expense_request_workflow.py`. Untuk menjalankan:
```bash
pytest imogi_finance/tests/test_expense_request_workflow.py -v
```

### Manual Testing Checklist
Sebelum deploy ke production, test scenario berikut:

1. **Happy Path**
   - [ ] ER status Approved
   - [ ] Budget sudah locked (jika enforce aktif)
   - [ ] Tax invoice sudah Verified (jika require_verification aktif)
   - [ ] Klik workflow action "Create PI"
   - [ ] Verifikasi PI terbentuk
   - [ ] Verifikasi field linked_purchase_invoice terisi
   - [ ] Verifikasi status berubah ke "PI Created"

2. **Error Handling - Budget Not Locked**
   - [ ] ER status Approved tapi budget belum locked
   - [ ] Klik "Create PI"
   - [ ] Harus muncul error "Expense Request must be budget locked..."
   - [ ] Status tidak berubah
   - [ ] PI tidak dibuat

3. **Error Handling - Tax Invoice Not Verified**
   - [ ] ER status Approved, is_ppn_applicable = 1
   - [ ] Tax invoice belum Verified
   - [ ] Setting require_verification aktif
   - [ ] Klik "Create PI"
   - [ ] Harus muncul error "Tax Invoice must be verified..."
   - [ ] Status tidak berubah
   - [ ] PI tidak dibuat

4. **Validation Check**
   - [ ] Coba ubah status manual ke "PI Created" tanpa linked_purchase_invoice
   - [ ] Harus ditolak dengan error message

## Deployment Plan

### Pre-Deployment
- [x] Code changes implemented
- [x] Unit tests created
- [x] Documentation created
- [ ] Manual testing in development
- [ ] Code review
- [ ] Testing in staging with real data

### Deployment
- [ ] Backup database
- [ ] Deploy code changes
- [ ] Run `bench migrate`
- [ ] Clear cache (`bench clear-cache`)
- [ ] Restart workers

### Post-Deployment
- [ ] Monitor error logs for 24-48 hours
- [ ] Check with accounting team for any issues
- [ ] Update user training materials if needed
- [ ] Document any edge cases found

## Rollback Plan

Jika ada masalah serius:

1. Revert changes di `expense_request.py`:
   ```bash
   git revert <commit-hash>
   bench restart
   ```

2. Atau comment out handler sementara dan restart:
   - Comment lines di `before_workflow_action` untuk action "Create PI"
   - Comment validasi di `on_workflow_action`
   - `bench restart`

3. Users bisa gunakan tombol "Create Purchase Invoice" di form sebagai workaround

## Impact Analysis

### Positif
- ✅ Bug fixed: PI sekarang benar-benar dibuat saat action "Create PI"
- ✅ Validasi lebih ketat: Status "PI Created" tidak bisa terjadi tanpa PI
- ✅ Error handling lebih baik: Message jelas kenapa PI creation gagal
- ✅ Test coverage bertambah

### Potensi Risk
- ⚠️ Perubahan behavior: User yang biasa klik workflow action harus pastikan semua validasi terpenuhi
- ⚠️ Performance: PI creation jadi synchronous dalam workflow action (bisa lambat jika data besar)

### Mitigation
- Dokumentasi jelas untuk user tentang requirement sebelum klik "Create PI"
- Error messages yang informatif
- Fallback: Tombol "Create Purchase Invoice" di form masih tersedia

## Questions & Answers

**Q: Apakah tombol "Create Purchase Invoice" di form masih bisa digunakan?**  
A: Ya, masih bisa dan menghasilkan hasil yang sama dengan workflow action.

**Q: Bagaimana dengan ER yang sudah ada di status "PI Created" tapi tidak ada PI?**  
A: Perlu diperbaiki manual:
1. Reopen ER ke status "Approved"
2. Gunakan tombol/action "Create PI" lagi

**Q: Apakah perlu migrate data?**  
A: Tidak perlu migrate. Ini hanya perubahan logic, tidak ada perubahan schema database.

**Q: Apakah backward compatible?**  
A: Ya. ER yang sudah ada tidak terpengaruh. Hanya workflow action ke depan yang berubah.

## Contact

Untuk pertanyaan atau issue terkait fix ini, hubungi:
- Development Team
- GitHub Issues: [link-to-repo]

---
**Tanggal**: 12 Januari 2026  
**Status**: ✅ Code Ready, Pending Testing & Deployment
