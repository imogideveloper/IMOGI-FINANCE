# Catatan Kontrol Workflow Expense Request

Dokumen ini merangkum konfigurasi sensitif dan risiko operasional di workflow **Expense Request**.
Gunakan sebagai panduan saat mengaktifkan flag situs atau mengubah konfigurasi persetujuan.

## Override reopen dengan link aktif

- Flag situs `imogi_finance_allow_reopen_with_active_links` **atau** checkbox dokumen `allow_reopen_with_active_links` mengizinkan reopen ketika masih ada Payment Entry/Purchase Invoice/Asset aktif. Sistem akan menambah komentar audit dan log peringatan, tetapi dokumen downstream tetap terbuka sehingga duplikasi transaksi tetap mungkin jika pengguna tidak menutupnya dulu.
- Rekomendasi:
  - Prioritaskan penutupan/cancel dokumen downstream sebelum reopen; gunakan override hanya ketika perlu audit/penyelarasan.
  - Wajibkan checklist verifikasi internal (mis. custom field “Reopen Checklist” berisi item pengecekan Payment Entry/PI/Asset) sebelum menyalakan override; jika ada link aktif, pastikan checklist ini menghasilkan tugas untuk menutup/cancel dokumen downstream sebelum approval lanjut.
  - Pastikan timeline comment dari audit reopen ditinjau oleh reviewer agar ada jejak siapa yang memaksa override, siapa yang memverifikasi, dan apa tindak lanjutnya.
  - Batasi hak menyalakan override ke role tertentu dan time-box penggunaannya (mis. aktif maksimal 1 hari kerja) untuk mencegah bypass SOP berlarut.
  - Jika override dipakai, pastikan tidak ada “link aktif” tersisa sebelum melanjutkan approval untuk menutup risiko double payment.

## Penutupan tanpa rute

- Flag situs `imogi_finance_allow_unrestricted_close` melewati validasi approver pada aksi **Close**. Jika diaktifkan global, kontrol pemisahan tugas hilang karena siapa pun dengan hak workflow dapat menutup tanpa pengecekan rute.
- Rekomendasi:
  - Biarkan flag **OFF** secara default; gunakan hanya untuk kondisi darurat dan nyalakan sementara (time-boxed) dengan persetujuan manajemen dan catatan kontrol perubahan.
  - Tambahkan catatan audit manual pada dokumen yang ditutup selama flag aktif (mis. komentar “Ditutup dengan unrestricted close pada <timestamp> oleh <user>”) dan wajibkan reviewer menyetujui catatan tersebut sebelum penutupan dianggap final.
  - Setelah selesai, matikan kembali flag, lakukan re-validasi route terbaru, dan dokumentasikan waktu on/off untuk pelacakan.

## Rute tidak otomatis mengikuti perubahan konfigurasi

- Rute disimpan di dokumen saat submit dan disnapshot ketika Approved untuk validasi Close. Recompute otomatis hanya terjadi ketika:
  - Dokumen di-reopen (rute dihitung ulang dan status direset).
  - Field kunci berubah pada status Pending (amount, cost center, atau daftar akun biaya) — status turun ke Pending Level 1 dengan rute baru.
- Perubahan aturan persetujuan di tengah jalan **tidak** langsung diterapkan ke dokumen yang sudah pending jika tidak ada pemicu di atas.
- Rekomendasi SOP:
  - Setelah mengubah konfigurasi route, lakukan “refresh route” pada dokumen pending dengan reopen terkontrol atau ubah minor key field yang aman (mis. re-set nilai sama) agar rute dihitung ulang (rebuild tidak otomatis hanya karena konfigurasi berubah).
  - Dokumentasikan langkah refresh di runbook dan track eksekusi (mis. checklist ops) agar tidak ada pending yang tertinggal memakai rute lama.
  - Hindari persetujuan lebih lanjut sebelum refresh dilakukan supaya tidak ada dokumen yang lolos memakai rute lama.

## Hak edit luas saat pending

- Workflow `allow_edit` untuk Pending Level 1–3 disetel ke `All`, sehingga semua pengguna dapat mengubah detail selama docstatus 1. Perubahan field kunci memicu reset ke Pending Level 1, tetapi field lain (mis. deskripsi atau lampiran) dapat berubah tanpa log khusus.
- Rekomendasi:
  - Batasi edit di lingkungan production dengan role/profile tambahan atau custom permission jika data non-kunci perlu dikunci; minimalkan surface area edit untuk non-owner/non-approver supaya kontrol pemisahan tugas tidak hanya bergantung pada guard di controller.
  - Dorong penggunaan komentar/timeline untuk mencatat perubahan penting saat pending dan jadikan komentar ini bagian dari definition of done tiap perubahan.
  - Aktifkan audit trail (mis. Enable Versioning atau log perubahan custom) khusus untuk status Pending sehingga modifikasi field non-kunci tercatat sebelum validasi Save terjadi.

## Self-submission dibatasi

- Aksi **Submit** hanya boleh dijalankan oleh creator dokumen (owner). Ini mengurangi spoofing atau submit oleh pihak lain.
- Implikasi:
  - Untuk skenario delegasi, perlukan mekanisme resmi (mis. user proxy atau pergantian ownership) karena workflow tidak mengizinkan submit oleh user lain; sertakan SLA untuk pengalihan ownership ketika owner tidak tersedia agar proses tidak tertahan.
  - Sosialisasikan batasan ini ke tim approval agar eskalasi tidak macet saat owner sedang tidak aktif, dan catat delegasi yang aktif di komentar dokumen untuk transparansi.

## Guard validasi status workflow

- Perubahan status di luar aksi workflow akan ditolak oleh guard. Integritas status terjaga, tetapi automation/manual patch perlu mengatur flag dengan benar supaya tidak gagal diam-diam.
- Rekomendasi:
  - Pastikan script atau API call yang memicu aksi terkontrol menetapkan `workflow_action_allowed` (atau `frappe.flags` setara) ketika bypass diperlukan dan sudah disetujui.
  - Dokumentasikan penggunaan bypass di log/audit trail agar reviewer tahu ada perubahan status non-standar.
