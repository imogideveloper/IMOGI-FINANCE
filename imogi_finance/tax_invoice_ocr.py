from __future__ import annotations

import base64
import json
import math
import os
import re
import subprocess
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.exceptions import ValidationError
from frappe.utils import cint, flt, get_site_path
from frappe.utils.formatters import format_value

background_jobs = getattr(frappe.utils, "background_jobs", None)

SETTINGS_DOCTYPE = "Tax Invoice OCR Settings"
DEFAULT_SETTINGS = {
    "enable_tax_invoice_ocr": 0,
    "ocr_provider": "Manual Only",
    "ocr_language": "id",
    "ocr_max_pages": 2,
    "ocr_min_confidence": 0.85,
    "ocr_max_retry": 1,
    "ocr_file_max_mb": 10,
    "store_raw_ocr_json": 1,
    "require_verification_before_submit_pi": 1,
    "require_verification_before_create_pi_from_expense_request": 1,
    "npwp_normalize": 1,
    "tolerance_idr": 10000,
    "block_duplicate_fp_no": 1,
    "ppn_input_account": None,
    "ppn_output_account": None,
    "default_ppn_type": "Standard",
    "use_tax_rule_effective_date": 1,
    "google_vision_service_account_file": None,
    "google_vision_endpoint": "https://vision.googleapis.com/v1/files:annotate",
    "tesseract_cmd": None,
}

ALLOWED_OCR_FIELDS = {"fp_no", "fp_date", "npwp", "dpp", "ppn", "ppnbm", "ppn_type", "notes"}

FIELD_MAP = {
    "Purchase Invoice": {
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
    },
    "Expense Request": {
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
    },
    "Branch Expense Request": {
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
    },
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

UPLOAD_LINK_FIELDS = {
    "Purchase Invoice": "ti_tax_invoice_upload",
    "Expense Request": "ti_tax_invoice_upload",
    "Branch Expense Request": "ti_tax_invoice_upload",
    "Sales Invoice": "out_fp_tax_invoice_upload",
}


def get_settings() -> dict[str, Any]:
    if not frappe.db:
        return DEFAULT_SETTINGS.copy()

    settings_map = DEFAULT_SETTINGS.copy()
    getter = getattr(getattr(frappe, "db", None), "get_singles_dict", None)
    record = getter(SETTINGS_DOCTYPE) if callable(getter) else {}
    record = record or {}
    settings_map.update(record)
    settings_obj = frappe._dict(settings_map)
    if not hasattr(settings_obj, "get"):
        settings_obj.get = lambda key, default=None: getattr(settings_obj, key, default)
    return settings_obj


def normalize_npwp(npwp: str | None) -> str | None:
    if not npwp:
        return npwp
    settings = get_settings()
    if cint(settings.get("npwp_normalize")):
        return re.sub(r"[.\-\s]", "", npwp or "")
    return npwp


NPWP_REGEX = re.compile(r"(?P<npwp>\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}|\d{15,20})")
NPWP_LABEL_REGEX = re.compile(r"NPWP\s*[:\-]?\s*(?P<npwp>[\d.\-\s]{10,})", re.IGNORECASE)
PPN_RATE_REGEX = re.compile(r"(?:Tarif\s*)?PPN[^\d%]{0,10}(?P<rate>\d{1,2}(?:[.,]\d+)?)\s*%", re.IGNORECASE)
TAX_INVOICE_REGEX = re.compile(r"(?P<fp>\d{2,3}[.\-\s]?\d{2,3}[.\-\s]?\d{1,2}[.\-\s]?\d{8})")
DATE_REGEX = re.compile(r"(?P<date>\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})")
NUMBER_REGEX = re.compile(r"(?P<number>\d+[.,\d]*)")
AMOUNT_REGEX = re.compile(r"(?P<amount>\d{1,3}(?:[.,]\d{3})*[.,]\d{2})")
FAKTUR_NO_LABEL_REGEX = re.compile(
    r"Kode\s+dan\s+Nomor\s+Seri\s+Faktur\s+Pajak\s*[:\-]?\s*(?P<fp>[\d.\-\s]{10,})",
    re.IGNORECASE,
)
INDO_DATE_REGEX = re.compile(r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})")
INDO_MONTHS = {
    "januari": 1,
    "februari": 2,
    "maret": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "agustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}


def _get_fieldname(doctype: str, key: str) -> str:
    mapping = FIELD_MAP.get(doctype) or FIELD_MAP["Purchase Invoice"]
    return mapping.get(key, key)


def _get_canonical_key(fieldname: str) -> str:
    if fieldname.startswith("ti_fp_"):
        return fieldname.replace("ti_fp_", "")
    if fieldname.startswith("out_fp_"):
        return fieldname.replace("out_fp_", "")
    if fieldname == "out_buyer_tax_id":
        return "npwp"
    return fieldname


def _get_value(doc: Any, doctype: str, key: str, default: Any = None) -> Any:
    fieldname = _get_fieldname(doctype, key)
    return getattr(doc, fieldname, default)


def _get_upload_link_field(doctype: str) -> str | None:
    return UPLOAD_LINK_FIELDS.get(doctype)


def get_linked_tax_invoice_uploads(
    *, exclude_doctype: str | None = None, exclude_name: str | None = None
) -> set[str]:
    targets = ("Purchase Invoice", "Expense Request", "Branch Expense Request")
    uploads: set[str] = set()

    for target in targets:
        fieldname = _get_upload_link_field(target)
        if not fieldname:
            continue

        filters: dict[str, Any] = {fieldname: ("!=", None)}
        if target != "Expense Request":
            filters["docstatus"] = ("<", 2)
        if exclude_name and target == exclude_doctype:
            filters["name"] = ("!=", exclude_name)

        try:
            linked = frappe.get_all(target, filters=filters, pluck=fieldname) or []
        except Exception:
            continue

        uploads.update(linked)

    return {name for name in uploads if name}


def _find_existing_upload_link(
    upload_name: str, current_doctype: str, current_name: str | None = None
) -> tuple[str | None, str | None]:
    targets = ("Purchase Invoice", "Expense Request", "Branch Expense Request")

    for target in targets:
        fieldname = _get_upload_link_field(target)
        if not fieldname:
            continue

        filters: dict[str, Any] = {fieldname: upload_name}
        if target != "Expense Request":
            filters["docstatus"] = ("<", 2)
        if current_name and target == current_doctype:
            filters["name"] = ("!=", current_name)

        try:
            matches = frappe.get_all(target, filters=filters, pluck="name", limit=1) or []
        except Exception:
            continue

        if matches:
            return target, matches[0]
    return None, None


def validate_tax_invoice_upload_link(doc: Any, doctype: str):
    link_field = _get_upload_link_field(doctype)
    if not link_field:
        return

    fp_no = _get_value(doc, doctype, "fp_no")
    upload = getattr(doc, link_field, None)
    has_manual_fields = any(
        _get_value(doc, doctype, key)
        for key in ("fp_no", "fp_date", "npwp", "dpp", "ppn", "ppnbm")
    )

    if not upload:
        if has_manual_fields:
            raise ValidationError(_("Please select a verified Tax Invoice OCR Upload for the Faktur Pajak."))
        return

    status = frappe.db.get_value("Tax Invoice OCR Upload", upload, "verification_status")
    if status != "Verified":
        raise ValidationError(_("Tax Invoice OCR Upload {0} must be Verified.").format(upload))

    existing_doctype, existing_name = _find_existing_upload_link(upload, doctype, getattr(doc, "name", None))
    if existing_doctype and existing_name:
        raise ValidationError(
            _("Tax Invoice OCR Upload {0} is already used in {1} {2}. Please select another Faktur Pajak.")
            .format(upload, existing_doctype, existing_name)
        )


def get_tax_invoice_upload_context(target_doctype: str | None = None, target_name: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    used_uploads = sorted(
        get_linked_tax_invoice_uploads(exclude_doctype=target_doctype, exclude_name=target_name)
    )
    verified_uploads = []
    try:
        verified_uploads = frappe.get_all(
            "Tax Invoice OCR Upload",
            filters={
                "verification_status": "Verified",
                **({"name": ("not in", used_uploads)} if used_uploads else {}),
            },
            fields=["name", "fp_no", "fp_date", "npwp", "dpp", "ppn", "ppnbm", "ppn_type"],
        )
    except Exception:
        verified_uploads = []
    return {
        "enable_tax_invoice_ocr": cint(settings.get("enable_tax_invoice_ocr", 0)),
        "ocr_provider": settings.get("ocr_provider") or "Manual Only",
        "used_uploads": used_uploads,
        "verified_uploads": verified_uploads,
    }


def _set_value(doc: Any, doctype: str, key: str, value: Any) -> None:
    fieldname = _get_fieldname(doctype, key)
    setattr(doc, fieldname, value)


def _copy_tax_invoice_fields(source_doc: Any, source_doctype: str, target_doc: Any, target_doctype: str):
    keys = (
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
    for key in keys:
        _set_value(target_doc, target_doctype, key, _get_value(source_doc, source_doctype, key))


def _extract_section(text: str, start_label: str, end_label: str | None = None) -> str:
    if not text:
        return ""
    lower_text = text.lower()
    start_index = lower_text.find(start_label.lower())
    if start_index < 0:
        return text
    if end_label:
        end_index = lower_text.find(end_label.lower(), start_index)
        if end_index > start_index:
            return text[start_index:end_index]
    return text[start_index:]


def _parse_idr_amount(value: str) -> float:
    cleaned = (value or "").strip()
    last_dot = cleaned.rfind(".")
    last_comma = cleaned.rfind(",")
    if last_dot == -1 and last_comma == -1:
        return flt(cleaned)

    decimal_index = max(last_dot, last_comma)
    integer_part = re.sub(r"[.,]", "", cleaned[:decimal_index])
    decimal_part = cleaned[decimal_index + 1 :]
    normalized = f"{integer_part}.{decimal_part}"
    return flt(normalized)


def _sanitize_amount(value: Any, *, max_abs: float = 9_999_999_999_999.99) -> float | None:
    try:
        number = flt(value)
    except Exception:
        return None

    if not math.isfinite(number):
        return None
    if abs(number) > max_abs:
        return None
    return number


def _extract_section_lines(text: str, start_label: str, stop_labels: tuple[str, ...]) -> list[str]:
    lines = text.splitlines()
    start_idx = next((idx for idx, line in enumerate(lines) if start_label.lower() in line.lower()), None)
    if start_idx is None:
        return []

    collected: list[str] = []
    for line in lines[start_idx:]:
        normalized = line.lower().strip()
        if any(normalized.startswith(stop.lower()) for stop in stop_labels):
            break
        collected.append(line.strip())
    return collected


def _extract_first_after_label(section_lines: list[str], label: str) -> str | None:
    pattern = re.compile(rf"{re.escape(label)}\s*[:\-]?\s*(?P<value>.+)", re.IGNORECASE)
    for line in section_lines:
        match = pattern.search(line)
        if match:
            return match.group("value").strip()
    return None


def _find_amount_after_label(text: str, label: str) -> float | None:
    def _extract_amount(line: str) -> float | None:
        amount_match = AMOUNT_REGEX.search(line or "")
        if amount_match:
            return _sanitize_amount(_parse_idr_amount(amount_match.group("amount")))
        number_match = NUMBER_REGEX.search(line or "")
        if number_match:
            return _sanitize_amount(_parse_idr_amount(number_match.group("number")))
        return None

    pattern = re.compile(rf"{re.escape(label)}\s*[:\-]?\s*(?P<value>.*)", re.IGNORECASE)
    lines = (text or "").splitlines()
    for idx, line in enumerate(lines):
        match = pattern.search(line)
        if not match:
            continue

        inline_amount = _extract_amount(match.group("value") or "")
        if inline_amount is not None:
            return inline_amount

        for next_line in lines[idx + 1 :]:
            if not next_line.strip():
                continue
            next_amount = _extract_amount(next_line)
            if next_amount is not None:
                return next_amount
            break
    return None


def _pick_best_npwp(candidates: list[str]) -> str | None:
    valid = [normalize_npwp((val or "").strip()) for val in candidates if val]
    valid = [val for val in valid if val]
    if not valid:
        return None

    def _score(value: str) -> tuple[int, int, str]:
        preferred_len = 0 if len(value) in {15, 16} else 1
        return (preferred_len, len(value), value)

    return sorted(valid, key=_score)[0]


def _extract_npwp_from_text(text: str) -> str | None:
    candidates = [match.group("npwp") for match in NPWP_REGEX.finditer(text or "")]
    return _pick_best_npwp(candidates)


def _extract_npwp_with_label(text: str) -> str | None:
    candidates = [match.group("npwp") for match in NPWP_LABEL_REGEX.finditer(text or "")]
    return _pick_best_npwp(candidates)


def _extract_address(section_lines: list[str], label: str) -> str | None:
    address: list[str] = []
    capture = False
    for line in section_lines:
        if label.lower() in line.lower() and ":" in line:
            capture = True
            address.append(line.split(":", 1)[1].strip())
            continue
        if capture:
            if not line or any(stop in line.lower() for stop in ("npwp", "nik", "email", "pembeli", "kode")):
                break
            address.append(line.strip())
    if not address:
        return None
    return " ".join(part for part in address if part)


def _parse_date_from_text(text: str) -> str | None:
    date_match = DATE_REGEX.search(text or "")
    if date_match:
        raw_date = date_match.group("date")
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
            try:
                return datetime.strptime(raw_date, fmt).date().isoformat()
            except Exception:
                continue

    indo_match = INDO_DATE_REGEX.search(text or "")
    if indo_match:
        try:
            day = int(indo_match.group("day"))
            month_name = indo_match.group("month").strip().lower()
            year = int(indo_match.group("year"))
            month = INDO_MONTHS.get(month_name)
            if month:
                return datetime(year, month, day).date().isoformat()
        except Exception:
            return None
    return None


def _normalize_faktur_number(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) < 10:
        return None
    return digits


def _extract_faktur_number_from_json(raw_json: dict[str, Any] | str | None) -> str | None:
    if not raw_json:
        return None

    payload: dict[str, Any] | None = None
    if isinstance(raw_json, dict):
        payload = raw_json
    elif isinstance(raw_json, str):
        try:
            payload = json.loads(raw_json)
        except Exception:
            payload = None

    if not isinstance(payload, dict):
        return None

    faktur_pajak = payload.get("faktur_pajak")
    if isinstance(faktur_pajak, dict):
        nomor_seri = faktur_pajak.get("nomor_seri")
        if nomor_seri:
            return _normalize_faktur_number(str(nomor_seri))

    return None


def parse_faktur_pajak_text(text: str) -> tuple[dict[str, Any], float]:
    matches: dict[str, Any] = {}
    confidence = 0.0

    seller_section = _extract_section_lines(
        text or "", "Pengusaha Kena Pajak", ("Pembeli Barang Kena Pajak", "Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak")
    )
    buyer_section = _extract_section_lines(
        text or "", "Pembeli Barang Kena Pajak", ("No.", "Kode Barang", "Nama Barang", "Harga Jual")
    )

    faktur_match = FAKTUR_NO_LABEL_REGEX.search(text or "")
    if faktur_match:
        normalized_fp = _normalize_faktur_number(faktur_match.group("fp"))
        if normalized_fp:
            matches["fp_no"] = normalized_fp
            confidence += 0.3
    else:
        fp_match = TAX_INVOICE_REGEX.search(text or "")
        if fp_match:
            normalized_fp = _normalize_faktur_number(fp_match.group("fp"))
            if normalized_fp:
                matches["fp_no"] = normalized_fp
                confidence += 0.25

    pkp_section = _extract_section(text or "", "Pengusaha Kena Pajak", "Pembeli")
    seller_npwp = _extract_npwp_with_label(pkp_section) or _extract_npwp_from_text(pkp_section)
    if seller_npwp:
        matches["npwp"] = seller_npwp
        confidence += 0.25
    else:
        seller_npwp = _extract_npwp_with_label(text) or _extract_npwp_from_text(text)
        if seller_npwp:
            matches["npwp"] = seller_npwp
            confidence += 0.2

    parsed_date = _parse_date_from_text(text or "")
    if parsed_date:
        matches["fp_date"] = parsed_date
        confidence += 0.15

    seller_name = _extract_first_after_label(seller_section, "Nama")
    seller_address = _extract_address(seller_section, "Alamat")
    buyer_name = _extract_first_after_label(buyer_section, "Nama")
    buyer_address = _extract_address(buyer_section, "Alamat")
    buyer_section_text = "\n".join(buyer_section)
    buyer_npwp = _extract_npwp_with_label(buyer_section_text) or _extract_npwp_from_text(buyer_section_text)

    amounts = [_sanitize_amount(_parse_idr_amount(m.group("amount"))) for m in AMOUNT_REGEX.finditer(text or "")]
    amounts = [amt for amt in amounts if amt is not None]
    labeled_dpp = _find_amount_after_label(text or "", "Dasar Pengenaan Pajak")
    labeled_ppn = _find_amount_after_label(text or "", "Jumlah PPN")

    if len(amounts) >= 6:
        tail_amounts = amounts[-6:]
        matches["dpp"] = tail_amounts[3]
        matches["ppn"] = tail_amounts[4]
        confidence += 0.2
    elif labeled_dpp is not None or labeled_ppn is not None:
        if labeled_dpp is not None:
            matches["dpp"] = labeled_dpp
        if labeled_ppn is not None:
            matches["ppn"] = labeled_ppn
        confidence += 0.2
    elif len(amounts) >= 2:
        sorted_amounts = sorted(amounts)
        matches["dpp"] = sorted_amounts[-1]
        matches["ppn"] = sorted_amounts[-2]
        confidence += 0.2
    elif amounts:
        matches["dpp"] = amounts[-1]
        confidence += 0.1
    else:
        numbers = [m.group("number") for m in NUMBER_REGEX.finditer(text or "")]
        parsed_numbers: list[float] = []
        for raw in numbers[:10]:
            digits_only = raw.replace(".", "").replace(",", "")
            if len(digits_only) > 15:
                continue
            value = raw.replace(".", "").replace(",", ".")
            try:
                parsed = _sanitize_amount(flt(value))
            except Exception:
                continue
            if parsed is None:
                continue
            parsed_numbers.append(parsed)

        if parsed_numbers:
            matches["dpp"] = max(parsed_numbers)
            if len(parsed_numbers) > 1:
                matches["ppn"] = sorted(parsed_numbers)[-2]
            confidence += 0.2

    ppn_rate = None
    ppn_rate_match = PPN_RATE_REGEX.search(text or "")
    if ppn_rate_match:
        raw_rate = ppn_rate_match.group("rate").replace(",", ".")
        try:
            ppn_rate = flt(raw_rate)
        except Exception:
            ppn_rate = None

    if ppn_rate is None:
        ppn_type = DEFAULT_SETTINGS.get("default_ppn_type", "Standard")
    else:
        ppn_type = "Standard" if ppn_rate > 0 else "Zero Rated"

    matches["ppn_type"] = ppn_type

    summary = {
        "faktur_pajak": {
            "nomor_seri": matches.get("fp_no"),
            "pengusaha_kena_pajak": {
                "nama": seller_name,
                "npwp": matches.get("npwp"),
                "alamat": seller_address,
            },
            "pembeli": {
                "nama": buyer_name,
                "npwp": buyer_npwp,
                "alamat": buyer_address,
            },
        },
        "ringkasan_pajak": {
            "dasar_pengenaan_pajak": matches.get("dpp"),
            "jumlah_ppn": matches.get("ppn"),
        },
    }

    matches["notes"] = json.dumps(summary, ensure_ascii=False, indent=2)

    filtered_matches = {key: value for key, value in matches.items() if key in ALLOWED_OCR_FIELDS}
    return filtered_matches, round(min(confidence, 0.95), 2)


def _validate_pdf_size(file_url: str, max_mb: int) -> None:
    if not file_url:
        frappe.throw(_("Please attach a Tax Invoice PDF before running OCR."))

    local_path = get_site_path(file_url.strip("/"))
    try:
        size_mb = os.path.getsize(local_path) / (1024 * 1024)
    except OSError:
        return
    if size_mb and size_mb > max_mb:
        frappe.throw(_("File exceeds maximum size of {0} MB.").format(max_mb))


def _validate_provider_settings(provider: str, settings: dict[str, Any]) -> None:
    if provider == "Manual Only":
        raise ValidationError(_("OCR provider not configured. Please select an OCR provider."))

    if provider == "Google Vision":
        service_account_file = settings.get("google_vision_service_account_file")
        if not service_account_file:
            try:
                import google.auth  # type: ignore
            except Exception:
                raise ValidationError(
                    _(
                        "Google Vision credentials are not configured. "
                        "Upload a Service Account JSON file or configure Application Default Credentials (service account). "
                        "API Key is not supported for the selected OCR flow. "
                        "See Google Cloud authentication guidance (e.g. gcloud auth application-default login or GOOGLE_APPLICATION_CREDENTIALS)."
                    )
                )
        endpoint = settings.get("google_vision_endpoint") or DEFAULT_SETTINGS["google_vision_endpoint"]
        parsed = urlparse(endpoint or DEFAULT_SETTINGS["google_vision_endpoint"])
        if not parsed.scheme or not parsed.netloc:
            raise ValidationError(_("Google Vision endpoint is invalid. Please update Tax Invoice OCR Settings."))

        allowed_hosts = {"vision.googleapis.com", "eu-vision.googleapis.com", "us-vision.googleapis.com"}
        if parsed.netloc not in allowed_hosts:
            raise ValidationError(_("Google Vision endpoint host is not supported. Please use vision.googleapis.com or a supported regional host."))

        if "asyncBatchAnnotate" in (parsed.path or ""):
            raise ValidationError(
                _(
                    "Google Vision asyncBatchAnnotate is not supported with the current OCR flow. "
                    "Use files:annotate (synchronous) or implement a GCS-based async flow with service-account auth."
                )
            )

        # If caller provides explicit parent in the path, ensure location is supported.
        if "/locations/" in (parsed.path or ""):
            parts = parsed.path.split("/locations/", 1)
            if len(parts) > 1:
                loc_part = (parts[1] or "").split("/")[0]
                if loc_part and loc_part not in {"us", "eu"}:
                    raise ValidationError(_("Google Vision location must be 'us' or 'eu' when specifying locations in endpoint path."))

        is_regional = parsed.netloc.startswith(("eu-vision.googleapis.com", "us-vision.googleapis.com"))
        if is_regional:
            if not settings.get("google_vision_project_id"):
                raise ValidationError(
                    _("Google Vision project ID is required when using a regional endpoint. Please update Tax Invoice OCR Settings.")
                )
            location = settings.get("google_vision_location")
            if not location:
                raise ValidationError(
                    _("Google Vision location is required when using a regional endpoint. Please update Tax Invoice OCR Settings.")
                )
            if location not in {"us", "eu"}:
                raise ValidationError(_("Google Vision location must be 'us' or 'eu' for regional endpoints."))
        return

    if provider == "Tesseract":
        if not settings.get("tesseract_cmd"):
            raise ValidationError(_("Tesseract command/path is not configured. Please update Tax Invoice OCR Settings."))
        return

    raise ValidationError(_("OCR provider {0} is not supported.").format(provider))


def _load_pdf_content_base64(file_url: str) -> tuple[str, str]:
    if not file_url:
        raise ValidationError(_("Tax Invoice PDF is missing. Please attach the file before running OCR."))

    local_path = get_site_path(file_url.strip("/"))
    try:
        with open(local_path, "rb") as handle:
            content = base64.b64encode(handle.read()).decode("utf-8")
    except FileNotFoundError:
        raise ValidationError(_("Could not read Tax Invoice PDF from {0}.").format(file_url))
    return local_path, content


def _build_google_vision_url(settings: dict[str, Any]) -> str:
    endpoint = settings.get("google_vision_endpoint") or DEFAULT_SETTINGS["google_vision_endpoint"]

    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise ValidationError(_("Google Vision endpoint is invalid. Please update Tax Invoice OCR Settings."))

    netloc = parsed.netloc
    path = parsed.path or ""

    is_regional = netloc.startswith(("eu-vision.googleapis.com", "us-vision.googleapis.com"))
    if not path or path == "/":
        path = "/v1/files:annotate"

    url = f"{parsed.scheme}://{netloc}{path}"
    return url


def _parse_service_account_json(raw_value: str) -> dict[str, Any]:
    try:
        return json.loads(raw_value)
    except Exception:
        try:
            decoded = base64.b64decode(raw_value).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            raise ValidationError(_("Google Vision Service Account JSON is invalid. Please check Tax Invoice OCR Settings."))


def _load_service_account_info(settings: dict[str, Any]) -> dict[str, Any] | None:
    file_url = settings.get("google_vision_service_account_file")

    if file_url:
        local_path = get_site_path(file_url.strip("/"))
        try:
            with open(local_path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except FileNotFoundError:
            raise ValidationError(_("Google Vision Service Account file not found: {0}").format(file_url))
        except OSError as exc:
            raise ValidationError(_("Could not read Google Vision Service Account file: {0}").format(exc))
        return _parse_service_account_json(content)

    return None


def _get_google_vision_headers(settings: dict[str, Any]) -> dict[str, str]:
    service_account_info = _load_service_account_info(settings)
    try:
        import google.auth  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
        if service_account_info:
            from google.oauth2 import service_account  # type: ignore
    except Exception:
        raise ValidationError(
            _(
                "Google Vision credentials are not configured. "
                "Install google-auth and provide Service Account JSON, or configure Application Default Credentials (service account). "
                "API Key is not supported for the selected OCR flow."
            )
        )

    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    credentials = None
    if service_account_info:
        credentials = service_account.Credentials.from_service_account_info(service_account_info, scopes=scopes)
    else:
        credentials, _ = google.auth.default(scopes=scopes)

    if credentials.expired or not credentials.valid:
        credentials.refresh(Request())

    if not credentials.token:
        raise ValidationError(_("Failed to obtain Google Vision access token from credentials."))

    return {"Authorization": f"Bearer {credentials.token}"}


def _google_vision_ocr(file_url: str, settings: dict[str, Any]) -> tuple[str, dict[str, Any], float]:
    def _iter_block_text(entry: dict[str, Any]) -> list[tuple[str, float, float, float]]:
        """Yield (text, y_min, y_max, confidence) for each block with normalized coordinates."""
        pages = (entry.get("fullTextAnnotation") or {}).get("pages") or []
        blocks: list[tuple[str, float, float, float]] = []

        for page in pages:
            for block in page.get("blocks") or []:
                vertices = (block.get("boundingBox") or {}).get("normalizedVertices") or []
                ys = [v.get("y", 0) for v in vertices if isinstance(v, dict) and "y" in v]
                if not ys:
                    continue
                y_min, y_max = min(ys), max(ys)
                block_conf = flt(block.get("confidence", 0))

                texts: list[str] = []
                for para in block.get("paragraphs") or []:
                    for word in para.get("words") or []:
                        symbols = [sym.get("text", "") for sym in (word.get("symbols") or []) if isinstance(sym, dict)]
                        word_text = "".join(symbols).strip()
                        if word_text:
                            texts.append(word_text)
                if texts:
                    blocks.append((" ".join(texts), y_min, y_max, block_conf))
        return blocks

    def _strip_border_artifacts(text: str) -> str:
        # Remove lines that are mostly border characters
        border_chars = set("─│—|+═╔╗╚╝•·-_=#[]")
        cleaned_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if len([ch for ch in stripped if ch in border_chars]) >= max(3, int(0.6 * len(stripped))):
                continue
            cleaned_lines.append(re.sub(r"[│─—|+_=]+", " ", stripped))
        return "\n".join(cleaned_lines)

    def _needs_full_text_fallback(text: str) -> bool:
        if not text or not text.strip():
            return True
        lower = text.lower()
        key_markers = ("pembeli", "penerima jasa", "dasar pengenaan pajak", "jumlah ppn")
        if any(marker in lower for marker in key_markers):
            return False
        # If we did not capture at least two currency amounts, we likely missed the summary table.
        if len(AMOUNT_REGEX.findall(text)) >= 2:
            return False
        return True

    try:
        import requests
    except Exception as exc:  # pragma: no cover - guard for missing optional dependency
        raise ValidationError(_("Google Vision OCR requires the requests package: {0}").format(exc))

    local_path, content = _load_pdf_content_base64(file_url)
    endpoint = _build_google_vision_url(settings)
    language = settings.get("ocr_language") or "id"
    max_pages = max(cint(settings.get("ocr_max_pages", 2)), 1)
    headers = _get_google_vision_headers(settings)

    request_body: dict[str, Any] = {
        "requests": [
            {
                "inputConfig": {"mimeType": "application/pdf", "content": content},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            }
        ]
    }

    image_context = {}
    if language:
        image_context["languageHints"] = [language]
    if image_context:
        request_body["requests"][0]["imageContext"] = image_context

    if max_pages and "files:annotate" in endpoint:
        request_body["requests"][0]["pages"] = list(range(1, max_pages + 1))

    try:
        response = requests.post(endpoint, json=request_body, headers=headers, timeout=45)
    except Exception as exc:
        raise ValidationError(_("Failed to call Google Vision OCR: {0}").format(exc))

    if response.status_code != 200:
        raise ValidationError(
            _("Google Vision OCR request failed with status {0}: {1}").format(
                response.status_code, response.text
            )
        )

    data = response.json() if hasattr(response, "json") else {}
    responses = data.get("responses") or []
    if not responses:
        raise ValidationError(_("Google Vision OCR did not return any responses for file {0}.").format(local_path))

    def _iter_entries(resp: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for entry in resp:
            yield entry
            nested_responses = entry.get("responses")
            if isinstance(nested_responses, list):
                for nested in nested_responses:
                    if isinstance(nested, dict):
                        yield nested

    texts: list[str] = []
    confidence_values: list[float] = []
    min_block_conf = flt(settings.get("ocr_min_confidence", 0.0)) or 0.0
    full_text_candidates: list[str] = []

    for entry in _iter_entries(responses):
        block_texts = _iter_block_text(entry)
        # keep only header (upper 35%) and footer (lower 35%) to avoid table/border noise
        filtered_blocks = [
            (text, conf)
            for text, y_min, y_max, conf in block_texts
            if conf >= min_block_conf and (y_max <= 0.35 or y_min >= 0.65)
        ]
        if filtered_blocks:
            texts.extend([text for text, _ in filtered_blocks])
            confidence_values.extend([conf for _, conf in filtered_blocks])
            full_text = (entry.get("fullTextAnnotation") or {}).get("text")
            if full_text:
                processed_full = _strip_border_artifacts((full_text or "").strip())
                if processed_full:
                    full_text_candidates.append(processed_full)
            continue

        # fallback to legacy full text if filtering produced nothing
        full_text = (entry.get("fullTextAnnotation") or {}).get("text")
        if not full_text:
            text_annotations = entry.get("textAnnotations") or []
            if text_annotations:
                full_text = text_annotations[0].get("description")
        if full_text:
            processed_full = _strip_border_artifacts((full_text or "").strip())
            if processed_full:
                full_text_candidates.append(processed_full)
                texts.append(processed_full)
            pages = (entry.get("fullTextAnnotation") or {}).get("pages") or []
            for page in pages:
                if "confidence" in page:
                    try:
                        confidence_values.append(flt(page.get("confidence")))
                    except Exception:
                        continue

    text = _strip_border_artifacts("\n".join(texts).strip())

    # If the filtered text is missing key markers or amounts, merge in the full text candidates captured earlier.
    if _needs_full_text_fallback(text) and full_text_candidates:
        fallback_text = "\n".join(full_text_candidates).strip()
        if fallback_text and fallback_text not in text:
            text = "\n".join([text, fallback_text]).strip()

    if not text:
        # Fallback: use any available fullTextAnnotation/textAnnotations text if block filtering produced nothing
        for entry in _iter_entries(responses):
            full_text = (entry.get("fullTextAnnotation") or {}).get("text")
            if full_text:
                pages = (entry.get("fullTextAnnotation") or {}).get("pages") or []
                for page in pages:
                    if "confidence" in page:
                        try:
                            confidence_values.append(flt(page.get("confidence")))
                        except Exception:
                            continue
                text = _strip_border_artifacts(full_text.strip())
                if text:
                    break
            text_annotations = entry.get("textAnnotations") or []
            if text_annotations:
                description = text_annotations[0].get("description")
                if description:
                    text = _strip_border_artifacts((description or "").strip())
                    if text:
                        break
    if not text:
        return "", data, 0.0

    confidence = max(confidence_values) if confidence_values else 0.0
    return text, data, confidence


def _tesseract_ocr(file_url: str, settings: dict[str, Any]) -> tuple[str, dict[str, Any] | None, float]:
    local_path, _ = _load_pdf_content_base64(file_url)
    language = settings.get("ocr_language") or "eng"
    command = settings.get("tesseract_cmd")

    if not command:
        raise ValidationError(_("Tesseract command/path is not configured. Please update Tax Invoice OCR Settings."))

    try:
        result = subprocess.run(
            [command, local_path, "stdout", "-l", language],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise ValidationError(_("Tesseract command not found: {0}").format(command))
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValidationError(_("Tesseract OCR failed: {0}").format(stderr or exc)) from exc
    except subprocess.TimeoutExpired:
        raise ValidationError(_("Tesseract OCR timed out for file {0}.").format(local_path))

    text = (result.stdout or "").strip()
    if not text:
        return "", None, 0.0

    return text, None, 0.0


def ocr_extract_text_from_pdf(file_url: str, provider: str) -> tuple[str, dict[str, Any] | None, float]:
    settings = get_settings()
    _validate_provider_settings(provider, settings)

    if provider == "Google Vision":
        return _google_vision_ocr(file_url, settings)

    if provider == "Tesseract":
        return _tesseract_ocr(file_url, settings)

    raise ValidationError(_("OCR provider {0} is not supported.").format(provider))


def _update_doc_after_ocr(
    doc: Any,
    doctype: str,
    parsed: dict[str, Any],
    confidence: float,
    raw_json: dict[str, Any] | None = None,
):
    setattr(doc, _get_fieldname(doctype, "status"), "Needs Review")
    setattr(doc, _get_fieldname(doctype, "ocr_status"), "Done")
    setattr(doc, _get_fieldname(doctype, "ocr_confidence"), confidence)

    allowed_keys = set(FIELD_MAP.get(doctype, FIELD_MAP["Purchase Invoice"]).keys()) & ALLOWED_OCR_FIELDS
    extra_notes: list[str] = []
    for key, value in parsed.items():
        if key not in allowed_keys:
            continue

        if key in {"dpp", "ppn"}:
            sanitized = _sanitize_amount(value)
            if sanitized is None:
                extra_notes.append(_("OCR ignored invalid {0} value").format(key.upper()))
                continue
            value = sanitized

        fieldname = _get_fieldname(doctype, key)
        setattr(doc, fieldname, value)

    if extra_notes:
        notes_field = _get_fieldname(doctype, "notes")
        existing_notes = getattr(doc, notes_field, None) or ""
        combined = f"{existing_notes}\n" if existing_notes else ""
        combined += "\n".join(extra_notes)
        setattr(doc, notes_field, combined)

    if raw_json is not None:
        setattr(doc, _get_fieldname(doctype, "ocr_raw_json"), json.dumps(raw_json, indent=2))

    doc.save(ignore_permissions=True)


def _run_ocr_job(name: str, target_doctype: str, provider: str):
    target_doc = frappe.get_doc(target_doctype, name)
    settings = get_settings()
    pdf_field = _get_fieldname(target_doctype, "tax_invoice_pdf")
    try:
        target_doc.db_set(_get_fieldname(target_doctype, "ocr_status"), "Processing")
        file_url = getattr(target_doc, pdf_field)
        text, raw_json, confidence = ocr_extract_text_from_pdf(file_url, provider)
        if not (text or "").strip():
            update_payload = {
                _get_fieldname(target_doctype, "ocr_status"): "Failed",
                _get_fieldname(target_doctype, "notes"): _(
                    "OCR returned empty text for file {0}."
                ).format(file_url),
            }
            if raw_json is not None:
                update_payload[_get_fieldname(target_doctype, "ocr_raw_json")] = json.dumps(raw_json, indent=2)
            target_doc.db_set(update_payload)
            return
        parsed, estimated_confidence = parse_faktur_pajak_text(text or "")
        if not parsed.get("fp_no"):
            raw_fp_no = _extract_faktur_number_from_json(raw_json)
            if raw_fp_no:
                parsed["fp_no"] = raw_fp_no
        _update_doc_after_ocr(
            target_doc,
            target_doctype,
            parsed,
            confidence or estimated_confidence,
            raw_json if cint(settings.get("store_raw_ocr_json", 1)) else None,
        )
    except Exception as exc:
        target_doc.db_set(
            {
                _get_fieldname(target_doctype, "ocr_status"): "Failed",
                _get_fieldname(target_doctype, "notes"): getattr(exc, "message", None) or str(exc),
            }
        )
        frappe.log_error(frappe.get_traceback(), "Tax Invoice OCR failed")


def _enqueue_ocr(doc: Any, doctype: str):
    settings = get_settings()
    pdf_field = _get_fieldname(doctype, "tax_invoice_pdf")
    _validate_pdf_size(getattr(doc, pdf_field, None), cint(settings.get("ocr_file_max_mb", 10)))

    doc.db_set(
        {
            _get_fieldname(doctype, "ocr_status"): "Queued",
            _get_fieldname(doctype, "notes"): None,
        }
    )
    provider = settings.get("ocr_provider", "Manual Only")

    method_path = f"{__name__}._run_ocr_job"
    frappe.enqueue(
        method_path,
        queue="long",
        job_name=f"tax-invoice-ocr-{doctype}-{doc.name}",
        timeout=300,
        now=getattr(frappe.flags, "in_test", False),
        is_async=not getattr(frappe.flags, "in_test", False),
        **{"name": doc.name, "target_doctype": doctype, "provider": provider},
    )


def _get_party_npwp(doc: Any, doctype: str) -> str | None:
    if doctype == "Sales Invoice":
        party = getattr(doc, "customer", None) or getattr(doc, "party", None)
        party_type = "Customer"
    else:
        party = getattr(doc, "supplier", None) or getattr(doc, "party", None)
        party_type = "Supplier"

    if not party:
        return None

    for field in ("tax_id", "npwp"):
        value = frappe.db.get_value(party_type, party, field)
        if value:
            return normalize_npwp(value)
    return None


def _build_filters(target_doctype: str, fp_no: str, company: str | None) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "name": ("!=", None),
        _get_fieldname(target_doctype, "fp_no"): fp_no,
    }
    if company and target_doctype not in ("Expense Request", "Tax Invoice OCR Upload"):
        filters["company"] = company
    if target_doctype not in ("Expense Request", "Tax Invoice OCR Upload"):
        filters["docstatus"] = ("<", 2)
    return filters


def _check_duplicate_fp_no(current_name: str, fp_no: str, company: str | None, doctype: str) -> bool:
    if not fp_no:
        return False

    targets = [
        "Purchase Invoice",
        "Expense Request",
        "Branch Expense Request",
        "Sales Invoice",
        "Tax Invoice OCR Upload",
    ]
    filters_cache: dict[str, dict[str, Any]] = {}

    for target in targets:
        fieldname = _get_fieldname(target, "fp_no")
        if not fieldname:
            continue

        filters = filters_cache.setdefault(
            target,
            _build_filters(target, fp_no, company),
        )
        filters["name"] = ("!=", current_name if target == doctype else "")

        try:
            matches = frappe.get_all(target, filters=filters, pluck="name")
        except Exception:
            continue

        if matches:
            return True

    return False


def sync_tax_invoice_upload(doc: Any, doctype: str, upload_name: str | None = None, *, save: bool = True):
    link_field = _get_upload_link_field(doctype)
    if not link_field:
        return None

    target_doc = doc if not isinstance(doc, str) else frappe.get_doc(doctype, doc)
    upload_docname = upload_name or getattr(target_doc, link_field, None)
    if not upload_docname:
        return None

    upload_doc = frappe.get_doc("Tax Invoice OCR Upload", upload_docname)
    if getattr(upload_doc, "verification_status", None) != "Verified":
        raise ValidationError(_("Tax Invoice OCR Upload {0} must be Verified before syncing.").format(upload_docname))
    _copy_tax_invoice_fields(upload_doc, "Tax Invoice OCR Upload", target_doc, doctype)

    if save:
        target_doc.save(ignore_permissions=True)

    return {
        "upload": upload_doc.name,
        "status": _get_value(upload_doc, "Tax Invoice OCR Upload", "status"),
    }


def verify_tax_invoice(doc: Any, *, doctype: str, force: bool = False) -> dict[str, Any]:
    settings = get_settings()
    notes: list[str] = []

    fp_no = _get_value(doc, doctype, "fp_no")
    if fp_no:
        fp_digits = re.sub(r"\D", "", str(fp_no))
        if len(fp_digits) != 17:
            notes.append(_("Tax invoice number must be exactly 16 digits."))
    company = getattr(doc, "company", None)
    if not company:
        cost_center = getattr(doc, "cost_center", None)
        if cost_center:
            company = frappe.db.get_value("Cost Center", cost_center, "company")

    if cint(settings.get("block_duplicate_fp_no", 1)) and fp_no and company:
        duplicate = _check_duplicate_fp_no(doc.name, fp_no, company, doctype)
        _set_value(doc, doctype, "duplicate_flag", 1 if duplicate else 0)
        if duplicate:
            notes.append(_("Duplicate tax invoice number detected."))

    party_npwp = _get_party_npwp(doc, doctype)
    doc_npwp = normalize_npwp(_get_value(doc, doctype, "npwp"))
    if doc_npwp and party_npwp:
        npwp_match = 1 if doc_npwp == party_npwp else 0
        _set_value(doc, doctype, "npwp_match", npwp_match)
        if npwp_match == 0:
            label = _("supplier") if doctype != "Sales Invoice" else _("customer")
            notes.append(_("NPWP on tax invoice does not match {0}.").format(label))

    expected_ppn = None
    if _get_value(doc, doctype, "ppn_type") == "Standard":
        dpp = flt(_get_value(doc, doctype, "dpp", 0))
        template_rate = None
        taxes = getattr(doc, "taxes", []) or []
        for row in taxes:
            try:
                rate = getattr(row, "rate", None)
                if rate is not None:
                    template_rate = rate
                    break
            except Exception:
                continue
        rate = template_rate if template_rate is not None else 11
        expected_ppn = dpp * rate / 100
    else:
        expected_ppn = 0

    tolerance = flt(settings.get("tolerance_idr", 10))
    if expected_ppn is not None:
        diff = abs(flt(_get_value(doc, doctype, "ppn", 0)) - expected_ppn)
        if diff > tolerance:
            notes.append(
                _("PPN amount differs from expected by more than {0}. Difference: {1}").format(
                    format_value(tolerance, "Currency"), format_value(diff, "Currency")
                )
            )

    dpp_value = flt(_get_value(doc, doctype, "dpp", 0))
    ppn_value = flt(_get_value(doc, doctype, "ppn", 0))
    ppnbm_value = flt(_get_value(doc, doctype, "ppnbm", 0))
    if ppnbm_value > 0 and dpp_value > 0:
        ppn_rate = (ppn_value / dpp_value) * 100
        if abs(ppn_rate - 11) > 0.01:
            notes.append(_("PPN rate must be 11% when PPNBM is present."))

    if notes and not force:
        _set_value(doc, doctype, "status", "Needs Review")
    else:
        _set_value(doc, doctype, "status", "Verified")

    if notes:
        _set_value(doc, doctype, "notes", "\n".join(notes))

    doc.save(ignore_permissions=True)
    return {"status": _get_value(doc, doctype, "status"), "notes": notes}


def run_ocr(docname: str, doctype: str):
    settings = get_settings()
    if not cint(settings.get("enable_tax_invoice_ocr", 0)):
        frappe.throw(_("Tax Invoice OCR is disabled. Enable it in Tax Invoice OCR Settings."))

    provider = settings.get("ocr_provider", "Manual Only")
    _validate_provider_settings(provider, settings)

    doc = frappe.get_doc(doctype, docname)
    _enqueue_ocr(doc, doctype)
    return {"queued": True}


def _get_job_info(job_name: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    get_info = getattr(background_jobs, "get_info", None)
    if callable(get_info):
        return get_info(job_name=job_name)

    get_job_info = getattr(background_jobs, "get_job_info", None)
    if callable(get_job_info):
        return get_job_info(job_name)

    return None


def _pick_job_info(job_name: str) -> dict[str, Any] | None:
    try:
        jobs = _get_job_info(job_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Tax Invoice OCR monitor get_info failed")
        return None

    if isinstance(jobs, dict):
        return jobs
    if not isinstance(jobs, (list, tuple)):
        return None

    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("job_name") == job_name or job.get("name") == job_name:
            return job

    return jobs[0] if jobs else None


def _format_job_info(job_info: dict[str, Any] | None, job_name: str) -> dict[str, Any] | None:
    if not job_info:
        return None

    def pick(*keys):
        for key in keys:
            if key in job_info:
                return job_info.get(key)
        return None

    return {
        "name": pick("job_name", "name") or job_name,
        "queue": pick("queue"),
        "status": pick("status", "state"),
        "exc_info": pick("exc_info", "error"),
        "kwargs": pick("kwargs"),
        "enqueued_at": pick("enqueued_at"),
        "started_at": pick("started_at"),
        "ended_at": pick("ended_at", "finished_at"),
    }


def get_tax_invoice_ocr_monitoring(docname: str, doctype: str) -> dict[str, Any]:
    if doctype not in FIELD_MAP:
        raise ValidationError(_("Doctype {0} is not supported for Tax Invoice OCR.").format(doctype))

    settings = get_settings()
    doc = frappe.get_doc(doctype, docname)

    source_doc = doc
    source_doctype = doctype
    link_field = _get_upload_link_field(doctype)
    upload_name = None
    if link_field:
        upload_name = getattr(doc, link_field, None)
        if upload_name:
            source_doctype = "Tax Invoice OCR Upload"
            source_doc = frappe.get_doc(source_doctype, upload_name)

    pdf_field = _get_fieldname(source_doctype, "tax_invoice_pdf")
    job_name = f"tax-invoice-ocr-{source_doctype}-{source_doc.name}"
    job_info = _format_job_info(_pick_job_info(job_name), job_name)
    doc_info = {
        "name": docname,
        "doctype": doctype,
        "upload_name": upload_name,
        "ocr_status": _get_value(source_doc, source_doctype, "ocr_status"),
        "verification_status": _get_value(source_doc, source_doctype, "status"),
        "verification_notes": _get_value(source_doc, source_doctype, "notes"),
        "ocr_confidence": _get_value(source_doc, source_doctype, "ocr_confidence"),
        "fp_no": _get_value(source_doc, source_doctype, "fp_no"),
        "fp_date": _get_value(source_doc, source_doctype, "fp_date"),
        "npwp": _get_value(source_doc, source_doctype, "npwp"),
        "dpp": _get_value(source_doc, source_doctype, "dpp"),
        "ppn": _get_value(source_doc, source_doctype, "ppn"),
        "ppnbm": _get_value(source_doc, source_doctype, "ppnbm"),
        "ppn_type": _get_value(source_doc, source_doctype, "ppn_type"),
        "duplicate_flag": _get_value(source_doc, source_doctype, "duplicate_flag"),
        "npwp_match": _get_value(source_doc, source_doctype, "npwp_match"),
        "tax_invoice_pdf": getattr(source_doc, pdf_field, None),
        "ocr_raw_json": _get_value(source_doc, source_doctype, "ocr_raw_json"),
        "ocr_raw_json_present": bool(_get_value(source_doc, source_doctype, "ocr_raw_json")),
    }

    return {
        "doc": doc_info,
        "job": job_info,
        "job_name": job_name,
        "provider": settings.get("ocr_provider"),
        "max_retry": settings.get("ocr_max_retry"),
    }
