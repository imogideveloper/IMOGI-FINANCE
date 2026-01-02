import json
import sys
import types

from imogi_finance.tax_invoice_ocr import parse_faktur_pajak_text
from imogi_finance import tax_invoice_ocr


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


def test_google_vision_ocr_uses_full_text_when_filtered_blocks_miss_details(monkeypatch, tmp_path):
    def make_block(text: str, y_min: float, y_max: float, conf: float = 0.95) -> dict:
        words = [{"symbols": [{"text": char} for char in word]} for word in text.split()]
        return {
            "boundingBox": {"normalizedVertices": [{"y": y_min}, {"y": y_max}, {"y": y_max}, {"y": y_min}]},
            "confidence": conf,
            "paragraphs": [{"words": words}],
        }

    header_block = make_block("Header Only", 0.05, 0.12)
    body_block = make_block(
        "Pembeli Barang Kena Pajak Nama CAKRA ADHIPERKASA OPTIMA NPWP 0953808789017000 Dasar Pengenaan Pajak 874.478,00 "
        "Jumlah PPN 104.937,00",
        0.5,
        0.55,
    )

    full_text = (
        "Faktur Pajak\n"
        "Kode dan Nomor Seri Faktur Pajak: 04002500432967499\n"
        "Pengusaha Kena Pajak: METROPOLITAN LAND TBK NPWP: 0016573131054000\n"
        "Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak:\n"
        "Nama CAKRA ADHIPERKASA OPTIMA NPWP 0953808789017000\n"
        "Dasar Pengenaan Pajak 874.478,00\n"
        "Jumlah PPN 104.937,00\n"
    )

    responses = [
        {
            "fullTextAnnotation": {"text": full_text, "pages": [{"blocks": [header_block, body_block], "confidence": 0.88}]}
        }
    ]

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return {"responses": self.payload}

    fake_requests = types.SimpleNamespace(post=lambda *args, **kwargs: DummyResponse(responses))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setattr(tax_invoice_ocr, "_load_pdf_content_base64", lambda file_url: ("dummy.pdf", ""))
    monkeypatch.setattr(tax_invoice_ocr, "_get_google_vision_headers", lambda settings: {})

    text, raw_json, confidence = tax_invoice_ocr._google_vision_ocr("dummy.pdf", tax_invoice_ocr.DEFAULT_SETTINGS)

    assert "Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak" in text
    assert "874.478,00" in text
    assert "104.937,00" in text
    assert raw_json["responses"] == responses
    assert confidence > 0

    parsed, _ = parse_faktur_pajak_text(text)
    assert parsed["dpp"] == 874478.0
    assert parsed["ppn"] == 104937.0
