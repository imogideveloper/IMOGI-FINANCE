from __future__ import annotations

from typing import Iterable

STANDARD_FIELD_MAP = {
    "fp_no": "ti_fp_no",
    "fp_date": "ti_fp_date",
    "npwp": "ti_fp_npwp",
    "dpp": "ti_fp_dpp",
    "ppn": "ti_fp_ppn",
    "ppnbm": "ti_fp_ppnbm",
    "ppn_type": "ti_fp_ppn_type",
    "status": "ti_verification_status",
    "notes": "ti_verification_notes",
    "duplicate_flag": "ti_duplicate_flag",
    "npwp_match": "ti_npwp_match",
    "ocr_status": "ti_ocr_status",
    "ocr_confidence": "ti_ocr_confidence",
    "ocr_raw_json": "ti_ocr_raw_json",
    "tax_invoice_pdf": "ti_tax_invoice_pdf",
}

FIELD_MAP: dict[str, dict[str, str]] = {
    "Purchase Invoice": STANDARD_FIELD_MAP,
    "Expense Request": STANDARD_FIELD_MAP,
    "Branch Expense Request": STANDARD_FIELD_MAP,
    "Sales Invoice": {
        "fp_no": "out_fp_no",
        "fp_date": "out_fp_date",
        "npwp": "out_buyer_tax_id",
        "dpp": "out_fp_dpp",
        "ppn": "out_fp_ppn",
        "ppn_type": "out_fp_ppn_type",
        "status": "out_fp_status",
        "notes": "out_fp_verification_notes",
        "duplicate_flag": "out_fp_duplicate_flag",
        "npwp_match": "out_fp_npwp_match",
        "ocr_status": "out_fp_ocr_status",
        "ocr_confidence": "out_fp_ocr_confidence",
        "ocr_raw_json": "out_fp_ocr_raw_json",
        "tax_invoice_pdf": "out_fp_pdf",
    },
    "Tax Invoice OCR Upload": {
        "fp_no": "fp_no",
        "fp_date": "fp_date",
        "npwp": "npwp",
        "dpp": "dpp",
        "ppn": "ppn",
        "ppnbm": "ppnbm",
        "ppn_type": "ppn_type",
        "status": "verification_status",
        "notes": "verification_notes",
        "duplicate_flag": "duplicate_flag",
        "npwp_match": "npwp_match",
        "ocr_status": "ocr_status",
        "ocr_confidence": "ocr_confidence",
        "ocr_raw_json": "ocr_raw_json",
        "tax_invoice_pdf": "tax_invoice_pdf",
    },
}

UPLOAD_LINK_FIELDS: dict[str, str] = {
    "Purchase Invoice": "ti_tax_invoice_upload",
    "Expense Request": "ti_tax_invoice_upload",
    "Branch Expense Request": "ti_tax_invoice_upload",
    "Sales Invoice": "out_fp_tax_invoice_upload",
}

COPY_KEYS: tuple[str, ...] = (
    "fp_no",
    "fp_date",
    "npwp",
    "dpp",
    "ppn",
    "ppnbm",
    "ppn_type",
    "status",
    "notes",
    "duplicate_flag",
    "npwp_match",
)


def get_field_map(doctype: str) -> dict[str, str]:
    return FIELD_MAP.get(doctype) or FIELD_MAP["Purchase Invoice"]


def get_supported_doctypes() -> set[str]:
    return set(FIELD_MAP)


def get_upload_link_field(doctype: str) -> str | None:
    return UPLOAD_LINK_FIELDS.get(doctype)


def iter_copy_keys() -> Iterable[str]:
    return COPY_KEYS


def get_tax_invoice_fields(doctype: str) -> set[str]:
    return set(get_field_map(doctype).values())
