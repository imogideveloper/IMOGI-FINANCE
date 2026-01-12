# Workflow Fix (Legacy): Create PI Action & Auto Paid Status

## Masalah yang Diperbaiki

### 1. Create PI Action (historical)
Sebelumnya, ketika user mengklik action **"Create PI"** di workflow Expense Request, sistem hanya mengubah status menjadi "PI Created" **tanpa benar-benar membuat dokumen Purchase Invoice**. Ini menyebabkan:

- Status Expense Request berubah ke "PI Created"
- Timeline menunjukkan "Administrator PI Created"
- Tetapi list Purchase Invoice tetap kosong
- Field `linked_purchase_invoice` di Expense Request kosong

### 2. Mark Paid Action (Removed)
Sebelumnya ada workflow action "Mark Paid" yang manual. Ini **tidak sesuai dengan desain sistem** karena status "Paid" seharusnya **sinkron otomatis** dari Payment Entry, bukan manual action.

## Solusi yang Diimplementasikan (status saat ini)

### 1. Tombol "Create Purchase Invoice" di Form (disarankan)

Implementasi terbaru menggunakan tombol custom **"Create Purchase Invoice"** di form Expense Request (bukan workflow action) yang:

- Memanggil `accounting.create_purchase_invoice_from_request()` untuk membuat dokumen PI yang sebenarnya
- Mengupdate field `linked_purchase_invoice` dan field terkait di dokumen ER
- Menangkap error jika PI creation gagal (misalnya budget belum locked, tax invoice belum verified) dan menampilkan pesan error yang jelas

### 2. (Legacy) Handler di `before_workflow_action` dan `on_workflow_action`

Versi sebelumnya menambahkan handler khusus untuk action workflow **"Create PI"** di `before_workflow_action` dan validasi di `on_workflow_action`. Handler tersebut sekarang sudah dihapus karena jalur resmi adalah lewat tombol form.

### 3. Update Dokumentasi Workflow
Removed "Mark Paid" Workflow Action

Action dan transition "Mark Paid" dihapus dari workflow karena:

- Status "Paid" diset otomatis oleh hook di `payment_entry.py` saat Payment Entry di-submit
- Hook `on_submit` di Payment Entry:
  - Validasi ER status = "PI Created"
  - Set `linked_payment_entry` ke ER
  - Set status ER = "Paid"
- Tidak perlu workflow action manual

### 5. Unit Tests

Ditambahkan test file `test_expense_request_workflow.py` dengan test cases:

- `test_workflow_action_create_pi_calls_accounting_method`: Memastikan method accounting dipanggil
- `test_workflow_action_create_pi_throws_on_failure`: Memastikan error ditangani dengan benar
- `test_on_workflow_action_validates_pi_created_state`: Memastikan validasi bekerja
- `test_payment_entry_sets_paid_status_integration`: Memastikan Payment Entry hook mengubah statusing dipanggil
- `test_workflow_action_create_pi_throws_on_failure`: Memastikan error ditangani dengan benar
- `test_on_workflow_action_validates_pi_created_state`: Memastikan validasi bekerja
- `test_workflow_prevents_manual_status_change_to_pi_created`: Mencegah bypass manual

## Cara Menggunakan (Untuk User)

### Cara Menggunakan (Untuk User)

#### Jalur utama: tombol "Create Purchase Invoice"

1. Buka Expense Request yang sudah **Approved**
2. Klik tombol **"Create Purchase Invoice"** di form (bukan workflow action)
3. Sistem akan:
    - Validasi semua requirement (budget lock, tax invoice verification, dll)
    - Membuat Purchase Invoice baru
    - Link PI ke ER
    - Ubah status ke state PI yang sesuai (misalnya "PI Created" jika digunakan)
4. Jika berhasil, akan muncul alert hijau dengan nama PI yang dibuat
5. Jika gagal, akan muncul error message yang jelas

#### Status "Paid" Otomatis

**Tidak ada workflow action "Mark Paid"** - status berubah otomatis:

1. Setelah ER terkait PI, buat Payment Entry untuk PI tersebut
2. Link Payment Entry ke Purchase Invoice / Expense Request sesuai desain
3. **Submit Payment Entry**
4. Hook di `payment_entry.py` otomatis set status ER ke "Paid"

## Error Messages yang Mungkin Muncul

### "Tax Invoice must be verified before creating a Purchase Invoice"

**Penyebab**: Setting `require_verification_before_create_pi_from_expense_request` aktif, ER bertanda PPN (`is_ppn_applicable = 1`), tapi tax invoice belum diverifikasi.

**Catatan**: Untuk ER non-PPN, error ini **tidak** muncul; tombol "Create Purchase Invoice" tetap bisa digunakan walaupun OCR belum Verified.

**Solusi**: Untuk ER PPN, verify tax invoice dulu sebelum klik tombol **"Create Purchase Invoice"** (atau perbaiki flag PPN jika ER seharusnya non-PPN).

### "Expense Request must be budget locked before creating a Purchase Invoice"

**Penyebab**: Budget control enforcement aktif, tapi ER belum dikunci budget-nya.

**Solusi**: Lock budget dulu atau ubah enforcement mode.

### "Internal Charge Request is required before creating a Purchase Invoice"

**Penyebab**: ER menggunakan allocation mode "Allocated via Internal Charge" tapi belum ada IC Request.

**Solusi**: Buat IC Request dulu sebelum create PI.

### "Expense Request already has draft Purchase Invoice PI-XXXX"

**Penyebab**: Sudah ada PI draft yang terhubung ke ER ini.

**Solusi**: Submit atau cancel PI draft yang ada sebelum membuat yang baru.

## Untuk Developer

### Testing

Run tests:
```bash
pytest imogi_finance/tests/test_expense_request_workflow.py -v
```

### Debugging

Jika ada masalah, cek:

1. **Frappe Error Log**: System Console → Error Log
2. **Timeline Comments**: Di dokumen ER untuk melihat history
3. **Field Values**: Cek `linked_purchase_invoice`, `pending_purchase_invoice`, `status`, `workflow_state`
4. **Budget Lock Status**: Cek field `budget_lock_status` jika budget control aktif

### Rollback Jika Diperlukan

Jika perlu rollback ke behavior lama (hanya ubah status tanpa create PI):

1. Comment out handler di `before_workflow_action`
2. Comment out validasi di `on_workflow_action`
3. Restart bench

**Tidak disarankan** karena akan kembali ke masalah awal.

## Checklist Deployment

- [x] Update `expense_request.py` dengan handler dan validasi
- [x] Update workflow JSON dengan notes
- [x] Tambahkan unit tests
- [x] Buat dokumentasi ini
- [ ] Test di development environment
- [ ] Test di staging environment dengan data real
- [ ] Deploy ke production
- [ ] Monitoring error logs selama 1-2 hari pertama
- [ ] Update user training material jika perlu

## Timeline

- **Implementasi**: 12 Januari 2026
- **Testing**: [TBD]
- **Deployment**: [TBD]

## Contact

Jika ada pertanyaan atau issue, hubungi tim development.
