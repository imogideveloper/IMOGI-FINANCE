# Catatan Kontrol Workflow Expense Request

Dokumen ini merangkum konfigurasi sensitif dan risiko operasional di workflow **Expense Request**.
Gunakan sebagai panduan saat mengaktifkan flag situs atau mengubah konfigurasi persetujuan.

## Override reopen dengan link aktif

- Flag situs `imogi_finance_allow_reopen_with_active_links` **atau** checkbox dokumen `allow_reopen_with_active_links` mengizinkan reopen ketika masih ada Payment Entry/Purchase Invoice/Asset aktif. Sistem akan menambah komentar audit dan log peringatan, tetapi dokumen downstream tetap terbuka sehingga duplikasi transaksi tetap mungkin jika pengguna tidak menutupnya dulu.
- Rekomendasi:
  - Prioritaskan penutupan/cancel dokumen downstream sebelum reopen; gunakan override hanya ketika perlu audit/penyelarasan.
  - Wajibkan checklist verifikasi internal (mis. custom field “Reopen Checklist” berisi item pengecekan Payment Entry/PI/Asset) sebelum menyalakan override.
  - Pastikan timeline comment dari audit reopen ditinjau oleh reviewer agar ada jejak siapa yang memaksa override.

## Penutupan tanpa rute

- Flag situs `imogi_finance_allow_unrestricted_close` melewati validasi approver pada aksi **Close**. Jika diaktifkan global, kontrol pemisahan tugas hilang karena siapa pun dengan hak workflow dapat menutup tanpa pengecekan rute.
- Rekomendasi:
  - Biarkan flag **OFF** secara default; gunakan hanya untuk kondisi darurat dan nyalakan sementara (time-boxed) dengan persetujuan manajemen.
  - Tambahkan catatan audit manual pada dokumen yang ditutup selama flag aktif (mis. komentar “Ditutup dengan unrestricted close pada <timestamp> oleh <user>”).
  - Setelah selesai, matikan kembali flag dan pastikan konfigurasi route terbaru sudah tervalidasi.

## Rute tidak otomatis mengikuti perubahan konfigurasi

- Rute disimpan di dokumen saat submit dan disnapshot ketika Approved untuk validasi Close. Recompute otomatis hanya terjadi ketika:
  - Dokumen di-reopen (rute dihitung ulang dan status direset).
  - Field kunci berubah pada status Pending (amount, cost center, atau daftar akun biaya) — status turun ke Pending Level 1 dengan rute baru.
- Perubahan aturan persetujuan di tengah jalan **tidak** langsung diterapkan ke dokumen yang sudah pending jika tidak ada pemicu di atas.
- Rekomendasi SOP:
  - Setelah mengubah konfigurasi route, lakukan “refresh route” pada dokumen pending dengan reopen terkontrol atau ubah minor key field yang aman (mis. re-set nilai sama) agar rute dihitung ulang.
  - Hindari persetujuan lebih lanjut sebelum refresh dilakukan supaya tidak ada dokumen yang lolos memakai rute lama.

## Hak edit luas saat pending

- Workflow `allow_edit` untuk Pending Level 1–3 disetel ke `All`, sehingga semua pengguna dapat mengubah detail selama docstatus 1. Perubahan field kunci memicu reset ke Pending Level 1, tetapi field lain (mis. deskripsi atau lampiran) dapat berubah tanpa log khusus.
- Rekomendasi:
  - Batasi edit di lingkungan production dengan role/profile tambahan atau custom permission jika data non-kunci perlu dikunci.
  - Dorong penggunaan komentar/timeline untuk mencatat perubahan penting saat pending.
  - Pertimbangkan audit trail tambahan (mis. Enable Versioning) untuk menutup celah modifikasi tanpa jejak.
