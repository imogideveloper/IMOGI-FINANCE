import json

from imogi_finance.tax_invoice_ocr import parse_faktur_pajak_text


def test_parse_faktur_pajak_text_extracts_amounts_and_buyer_npwp():
    text = """
    Faktur Pajak
    Kode dan Nomor Seri Faktur Pajak: 04002500432967499
    Pengusaha Kena Pajak:
    Nama : METROPOLITAN LAND TBK
    Alamat : M GOLD TOWER OFFICE WING LT 12 SUITE ABCGH & SUITE A-H LT 15 JL LETKOL
    #0016573131054000000000
    NPWP: 0016573131054000
    Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak:
    Nama CAKRA ADHIPERKASA OPTIMA
    Alamat: GEDUNG AD PREMIER OFFICE PARK LT 9 JL TB SIMATUPANG NO.05, RT 005, RW 007, RAGUNAN,
    NPWP0953808789017000
    Harga Jual / Penggantian / Uang Muka / Termin
    Dikurangi Potongan Harga
    Dikurangi Uang Muka yang telah diterima
    Dasar Pengenaan Pajak
    Jumlah PPN (Pajak Pertambahan Nilai)
    Jumlah PPnBM (Pajak Penjualan atas Barang Mewah)
    Harga Jual / Penggantian /
    Uang Muka / Termin
    (Rp)
    953.976,00
    953.976,00
    0,00
    874.478,00
    104.937,00
    0,00
    """

    parsed, confidence = parse_faktur_pajak_text(text)

    assert parsed["fp_no"] == "04002500432967499"
    assert parsed["npwp"] == "0016573131054000"
    assert parsed["dpp"] == 874478.0
    assert parsed["ppn"] == 104937.0
    assert confidence > 0

    summary = json.loads(parsed["notes"])
    buyer = summary["faktur_pajak"]["pembeli"]
    assert buyer["nama"] == "CAKRA ADHIPERKASA OPTIMA"
    assert buyer["npwp"] == "0953808789017000"
