### Imogi Finance

App for Manage Expense IMOGI

### Fitur Utama

#### Expense Request & Persetujuan

- **Rute persetujuan dinamis**: rute dihitung dari Expense Approval Setting per Cost Center + akun biaya + amount, disimpan di dokumen, dan wajib segar sebelum approve (deteksi perubahan konfigurasi otomatis menolak approval sampai rute direfresh). Submit hanya boleh oleh creator, approver harus sesuai user/role di rute, dan tidak boleh melompati level.
- **Kontrol edit & status setelah submit**: perubahan amount/cost center/akun biaya saat Pending mereset status ke Pending Level 1 dengan audit comment; status Approved/Linked/Closed tidak boleh ubah field kunci. Pending edits dibatasi ke owner atau approver, dan semua penolakan/override dicatat di timeline.
- **Reopen & Close terjaga**: reopen hanya untuk System Manager kecuali ada override, memaksa audit jika masih ada link Payment Entry/Purchase Invoice/Asset aktif. Aksi Close perlu validasi rute terbaru atau snapshot akhir; bisa override via flag darurat dengan jejak audit.
- **Guardrails status & jejak audit**: perubahan status di luar workflow diblokir, rute approval disnapshot ketika Approved untuk validasi Close, dan komentar otomatis tercatat untuk deny workflow, edit pending, atau reopen override.

#### Akuntansi & Dokumen Turunan

- **Pembuatan Purchase Invoice dari Expense Request**: helper whitelisted memastikan request Approved, tipe (Expense/Asset) sesuai, tidak ada link ganda, menyalin item (termasuk PPN/PPH) dengan penandaan pending/submitted untuk mencegah invoice dobel.
- **Link Asset & Payment Entry**: hooks pada Asset, Purchase Invoice, dan Payment Entry menjaga status request, menolak link ganda, dan memvalidasi dokumen turunan sudah submitted sebelum pembayaran. Request otomatis di-Closed setelah Payment Entry berhasil.

#### Customer Receipt & Validasi Pembayaran

- **Dokumen Customer Receipt**: menentukan desain default dari Finance Control Settings, memvalidasi referensi Sales Invoice/Sales Order sesuai customer & company, mengunci item setelah Issued, dan menghitung status Issued/Partially Paid/Paid berdasarkan pembayaran masuk.
- **Pembayaran terjaga**: Payment Entry hook menegakkan mode "Mandatory Strict" (harus link ke Customer Receipt saat ada open receipt), memblokir over-allocation atau referensi lain kecuali mode mixed payment, dan otomatis memperbarui/cabut catatan pembayaran di Receipt saat submit/cancel.
- **Otomasi penerimaan**: tombol `make_payment_entry` di Receipt membuat Payment Entry dengan alokasi otomatis sesuai outstanding per referensi.
- **Kebijakan stempel & utilitas Jinja**: Receipt menerapkan kebijakan stempel digital/physical sesuai konfigurasi (mandatory/threshold/fallback) dan menyediakan filter Jinja `terbilang_id` serta `build_verification_url` untuk template cetak.

#### Rekonsiliasi & Impor Bank

- **BCA Bank Statement Import**: upload CSV BCA, sistem menghitung hash untuk mencegah upload berulang, memvalidasi header/angka (deteksi kolom gabung/"sep=" preamble), menghitung saldo, dan skip baris saldo/pending. Tombol **Parse CSV BCA** mempersiapkan baris lalu **Convert to Bank Transaction** membuat Bank Transaction Unreconciled dengan pencegahan duplikasi dan pelaporan gagal/sukses. Aksi **Open Bank Reconciliation Tool** membawa rentang tanggal & akun bank yang sama.
- **Kontrol Bank Transaction**: transaksi berstatus Unreconciled tidak bisa dibatalkan (backend guard + tombol Cancel disembunyikan di form) untuk menjaga histori rekonsiliasi.

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
