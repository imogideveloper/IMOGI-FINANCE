from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_STANDARD_FIELD_MAP = {
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

DEFAULT_FIELD_MAP: dict[str, dict[str, str]] = {
    "Purchase Invoice": deepcopy(DEFAULT_STANDARD_FIELD_MAP),
    "Expense Request": deepcopy(DEFAULT_STANDARD_FIELD_MAP),
    "Branch Expense Request": deepcopy(DEFAULT_STANDARD_FIELD_MAP),
    "Sales Invoice": {
        "fp_no": "out_fp_no",
        "fp_date": "out_fp_date",
        "npwp": "out_fp_npwp",
        "dpp": "out_fp_dpp",
        "ppn": "out_fp_ppn",
        "ppnbm": "out_fp_ppnbm",
        "ppn_type": "out_fp_ppn_type",
        "status": "out_fp_status",
        "notes": "out_fp_verification_notes",
        "duplicate_flag": "out_fp_duplicate_flag",
        "npwp_match": "out_fp_npwp_match",
        "ocr_status": "out_fp_ocr_status",
        "ocr_confidence": "out_fp_ocr_confidence",
        "ocr_raw_json": "out_fp_ocr_raw_json",
        "tax_invoice_pdf": "out_fp_tax_invoice_pdf",
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

DEFAULT_COPY_KEYS: tuple[str, ...] = (
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


def _load_field_map_data() -> tuple[dict[str, dict[str, str]], tuple[str, ...]]:
    json_path = Path(__file__).resolve().parent / "public" / "json" / "tax_invoice_field_maps.json"
    if not json_path.exists():
        return deepcopy(DEFAULT_FIELD_MAP), DEFAULT_COPY_KEYS

    try:
        data: Mapping[str, object] = json.loads(json_path.read_text())
        json_field_maps = data.get("field_maps") or {}
        json_copy_keys = data.get("copy_keys") or ()

        field_maps: dict[str, dict[str, str]] = deepcopy(DEFAULT_FIELD_MAP)
        if isinstance(json_field_maps, dict):
            for doctype, mapping in json_field_maps.items():
                if isinstance(mapping, dict):
                    field_maps[doctype] = mapping

        copy_keys: list[str] = list(DEFAULT_COPY_KEYS)
        if isinstance(json_copy_keys, (list, tuple)):
            copy_keys = [str(key) for key in json_copy_keys] or copy_keys

        return field_maps, tuple(copy_keys)
    except Exception:
        return deepcopy(DEFAULT_FIELD_MAP), DEFAULT_COPY_KEYS


FIELD_MAP, COPY_KEYS = _load_field_map_data()

UPLOAD_LINK_FIELDS: dict[str, str] = {
    "Purchase Invoice": "ti_tax_invoice_upload",
    "Expense Request": "ti_tax_invoice_upload",
    "Branch Expense Request": "ti_tax_invoice_upload",
    "Sales Invoice": "out_fp_tax_invoice_upload",
}

def get_field_map(doctype: str) -> dict[str, str]:
    return FIELD_MAP.get(doctype) or FIELD_MAP["Purchase Invoice"]


def get_field_maps() -> dict[str, dict[str, str]]:
    return deepcopy(FIELD_MAP)


def get_supported_doctypes() -> set[str]:
    return set(FIELD_MAP)


def get_upload_link_field(doctype: str) -> str | None:
    return UPLOAD_LINK_FIELDS.get(doctype)


def iter_copy_keys() -> Iterable[str]:
    return COPY_KEYS


def get_copy_keys() -> tuple[str, ...]:
    return COPY_KEYS


def get_tax_invoice_fields(doctype: str) -> set[str]:
    return set(get_field_map(doctype).values())
