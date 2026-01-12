# Workflow Fix: Create PI Action & Auto Paid Status

## Masalah yang Diperbaiki

### 1. Create PI Action
Sebelumnya, ketika user mengklik action **"Create PI"** di workflow Expense Request, sistem hanya mengubah status menjadi "PI Created" **tanpa benar-benar membuat dokumen Purchase Invoice**. Ini menyebabkan:

- Status Expense Request berubah ke "PI Created"
- Timeline menunjukkan "Administrator PI Created"
- Tetapi list Purchase Invoice tetap kosong
- Field `linked_purchase_invoice` di Expense Request kosong

### 2. Mark Paid Action (Removed)
Sebelumnya ada workflow action "Mark Paid" yang manual. Ini **tidak sesuai dengan desain sistem** karena status "Paid" seharusnya **sinkron otomatis** dari Payment Entry, bukan manual action.

## Solusi yang Diimplementasikan

### 1. Handler di `before_workflow_action`

Ditambahkan logika di method `before_workflow_action` pada class `ExpenseRequest` yang:

- Mendeteksi ketika action "Create PI" dipilih
- Memanggil `accounting.create_purchase_invoice_from_request()` untuk membuat dokumen PI yang sebenarnya
- Mengupdate field `linked_purchase_invoice` dan `pending_purchase_invoice` di dokumen ER
- Menangkap error jika PI creation gagal (misalnya budget belum locked, tax invoice belum verified) dan menampilkan pesan error yang jelas

```python
if action == "Create PI":
    next_state = kwargs.get("next_state")
    if next_state == "PI Created":
        try:
            pi_name = accounting.create_purchase_invoice_from_request(self.name)
            if not pi_name:
                frappe.throw(...)
            self.linked_purchase_invoice = pi_name
            self.pending_purchase_invoice = None
        except Exception as e:
            frappe.throw(...)
```

### 2. Validasi di `on_workflow_action`

Ditambahkan validasi di method `on_workflow_action` yang:

- Memastikan status "PI Created" hanya bisa diset jika field `linked_purchase_invoice` sudah ada
- Mencegah perubahan status manual yang bypass pembuatan PI
- Memberikan error message yang jelas jika validasi gagal

```python
if action == "Create PI" and next_state == "PI Created":
    if not getattr(self, "linked_purchase_invoice", None):
        frappe.throw(
            _("Cannot set status to 'PI Created' without a linked Purchase Invoice...")
        )
```

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

### Workflow Action yang Benar
Status "Paid" Otomatis

**Tidak ada workflow action "Mark Paid"** - status berubah otomatis:

1. Setelah ER status "PI Created", buat Payment Entry
2. Link Payment Entry ke Expense Request
3. **Submit Payment Entry**
4. Hook di `payment_entry.py` otomatis set status ER ke "Paid"

### 
1. Buka Expense Request yang sudah **Approved**
2. Klik action **"Create PI"** (bukan mengubah status manual)
3. Sistem akan:
   - Validasi semua requirement (budget lock, tax invoice verification, dll)
   - Membuat Purchase Invoice baru
   - Link PI ke ER
   - Ubah status ke "PI Created"
4. Jika berhasil, akan muncul alert hijau dengan nama PI yang dibuat
5. Jika gagal, akan muncul error message yang jelas

### Tombol "Create Purchase Invoice" di Form

Alternatif, bisa tetap menggunakan tombol **"Create Purchase Invoice"** yang muncul di dashboard/form ER (bukan workflow action). Keduanya sekarang menghasilkan output yang sama.

## Error Messages yang Mungkin Muncul

### "Tax Invoice must be verified before creating a Purchase Invoice"

**Penyebab**: Setting `require_verification_before_create_pi_from_expense_request` aktif, tapi tax invoice belum diverifikasi.

**Solusi**: Verify tax invoice dulu sebelum klik "Create PI".

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
