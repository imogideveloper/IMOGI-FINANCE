### Imogi Finance

App for Manage Expense IMOGI

### Ringkasan Fitur Terbaru

- **Expense Request dengan rute persetujuan dinamis**: rute dihitung dari Expense Approval Setting per Cost Center + akun biaya + amount, disimpan di dokumen, dan wajib segar sebelum approve (deteksi perubahan konfigurasi otomatis menolak approval sampai rute direfresh). Submit hanya boleh oleh creator, approver harus sesuai user/role di rute, dan tidak boleh melompati level.
- **Kontrol edit & status setelah submit**: perubahan amount/cost center/akun biaya saat Pending mereset status ke Pending Level 1 dengan audit comment; status Approved/Linked/Closed tidak boleh ubah field kunci. Pending edits dibatasi ke owner atau approver, dan semua penolakan/override dicatat di timeline.
- **Reopen & Close terjaga**: reopen hanya untuk System Manager kecuali ada override, memaksa audit jika masih ada link Payment Entry/Purchase Invoice/Asset aktif. Aksi Close perlu validasi rute terbaru atau snapshot akhir; bisa override via flag darurat dengan jejak audit.
- **Alur akuntansi terintegrasi**: Expense Request terhubung ke Purchase Invoice/Payment Entry/Asset melalui hook submit/cancel dengan validasi status, tipe request (Expense/Asset), dan duplikasi link. Pembuatan Purchase Invoice memeriksa PPN/PPh, jumlah item, serta menandai pending/submitted link agar pembayaran tidak ganda.
- **Guardrails status**: perubahan status di luar workflow diblokir; rute approval disnapshot ketika Approved untuk audit dan validasi Close.

### BCA Bank Statement Import (Native-First)

Adapter native untuk impor statement CSV BCA ke ERPNext:

- Upload file di DocType **BCA Bank Statement Import**, sistem menghitung hash untuk mencegah upload berulang dan memvalidasi header/angka (mampu mendeteksi kolom gabung/"sep=" preamble).
- Klik **Parse CSV BCA** untuk mem-parsing baris, menghitung ringkasan saldo, dan menandai parsing sukses/gagal; baris yang hanya saldo/pending otomatis diskip.
- Parsing otomatis mencoba **Convert to Bank Transaction**: membuat `Bank Transaction` dengan status Unreconciled, mencegah duplikasi berdasarkan tanggal+amount+referensi/deskripsi, dan tetap bisa diulang via tombol **Convert to Bank Transaction** bila ada kegagalan sebagian.
- Tombol **Open Bank Reconciliation Tool** membuka rekonsiliasi dengan rentang tanggal & akun bank yang sama.

### Kontrol dan Risiko Workflow Expense Request

Lihat [Catatan Kontrol Workflow Expense Request](WORKFLOW_GUARDRAILS.md) untuk memahami dampak flag situs, perilaku rebuild rute, dan rekomendasi audit ketika melakukan reopen/close.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app imogi_finance
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/imogi_finance
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### Bench console checks

Gunakan contoh snippet berikut di bench console untuk memastikan validasi baru bekerja (mis. status belum Approved atau sudah terhubung ke dokumen lain):

```python
request = frappe.get_doc("Expense Request", "<NAMA_REQUEST>")
# Harus melempar error bila status belum Approved atau docstatus bukan 1
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)

# Tandai request sudah terhubung agar memicu error duplikasi
request.db_set("linked_purchase_invoice", "PI-TEST")
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)
# Untuk request tipe Asset, gunakan Purchase Invoice (Flow JE manual dihapus)
request.db_set({"linked_purchase_invoice": None, "request_type": "Asset"})
frappe.call("imogi_finance.accounting.create_purchase_invoice_from_request", expense_request_name=request.name)
```

### License

mit
