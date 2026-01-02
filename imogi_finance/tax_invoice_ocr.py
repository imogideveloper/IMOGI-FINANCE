from __future__ import annotations

import base64
import json
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
    "tolerance_idr": 10,
    "block_duplicate_fp_no": 1,
    "ppn_input_account": None,
    "ppn_output_account": None,
    "default_ppn_type": "Standard",
    "use_tax_rule_effective_date": 1,
    "google_vision_service_account_file": None,
    "google_vision_endpoint": "https://vision.googleapis.com/v1/files:annotate",
    "tesseract_cmd": None,
}

ALLOWED_OCR_FIELDS = {"fp_no", "fp_date", "npwp", "dpp", "ppn", "notes"}

FIELD_MAP = {
    "Purchase Invoice": {
        "fp_no": "ti_fp_no",
        "fp_date": "ti_fp_date",
        "npwp": "ti_fp_npwp",
        "dpp": "ti_fp_dpp",
        "ppn": "ti_fp_ppn",
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
TAX_INVOICE_REGEX = re.compile(r"(?P<fp>\d{2,3}[.-]?\d{2,3}[.-]?\d{1,2}[.-]?\d{8})")
DATE_REGEX = re.compile(r"(?P<date>\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})")
NUMBER_REGEX = re.compile(r"(?P<number>\d+[.,\d]*)")
AMOUNT_REGEX = re.compile(r"(?P<amount>\d{1,3}(?:\.\d{3})*,\d{2})")
FAKTUR_NO_LABEL_REGEX = re.compile(
    r"Kode\s+dan\s+Nomor\s+Seri\s+Faktur\s+Pajak\s*[:\-]?\s*(?P<fp>[\d.\-]{10,})",
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


def _set_value(doc: Any, doctype: str, key: str, value: Any) -> None:
    fieldname = _get_fieldname(doctype, key)
    setattr(doc, fieldname, value)


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
    cleaned = value.replace(".", "").replace(",", ".")
    return flt(cleaned)


def _extract_section_lines(text: str, start_label: str, stop_labels: tuple[str, ...]) -> list[str]:
    lines = text.splitlines()
    start_idx = next((idx for idx, line in enumerate(lines) if start_label.lower() in line.lower()), None)
    if start_idx is None:
        return []

    collected: list[str] = []
    for line in lines[start_idx:]:
        if any(stop.lower() in line.lower() for stop in stop_labels):
            break
        collected.append(line.strip())
    return collected


def _extract_first_after_label(section_lines: list[str], label: str) -> str | None:
    for line in section_lines:
        if label.lower() in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip()
    return None


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
        matches["fp_no"] = faktur_match.group("fp").replace(".", "").replace("-", "")
        confidence += 0.3
    else:
        fp_match = TAX_INVOICE_REGEX.search(text or "")
        if fp_match:
            matches["fp_no"] = fp_match.group("fp").replace(".", "").replace("-", "")
            confidence += 0.25

    pkp_section = _extract_section(text or "", "Pengusaha Kena Pajak", "Pembeli")
    npwp_match = NPWP_REGEX.search(pkp_section or "")
    if npwp_match:
        matches["npwp"] = normalize_npwp(npwp_match.group("npwp"))
        confidence += 0.25
    else:
        npwp_match = NPWP_REGEX.search(text or "")
        if npwp_match:
            matches["npwp"] = normalize_npwp(npwp_match.group("npwp"))
            confidence += 0.2

    parsed_date = _parse_date_from_text(text or "")
    if parsed_date:
        matches["fp_date"] = parsed_date
        confidence += 0.15

    seller_name = _extract_first_after_label(seller_section, "Nama")
    seller_address = _extract_address(seller_section, "Alamat")
    buyer_name = _extract_first_after_label(buyer_section, "Nama")
    buyer_address = _extract_address(buyer_section, "Alamat")
    buyer_npwp = _extract_first_after_label(buyer_section, "NPWP")
    if buyer_npwp:
        buyer_npwp = normalize_npwp(buyer_npwp)

    amounts = [_parse_idr_amount(m.group("amount")) for m in AMOUNT_REGEX.finditer(text or "")]
    if len(amounts) >= 6:
        tail_amounts = amounts[-6:]
        matches["dpp"] = tail_amounts[3]
        matches["ppn"] = tail_amounts[4]
        confidence += 0.2
    else:
        numbers = [m.group("number") for m in NUMBER_REGEX.finditer(text or "")]
        parsed_numbers: list[float] = []
        for raw in numbers[:6]:
            value = raw.replace(".", "").replace(",", ".")
            try:
                parsed_numbers.append(flt(value))
            except Exception:
                continue

        if parsed_numbers:
            matches["dpp"] = max(parsed_numbers)
            if len(parsed_numbers) > 1:
                matches["ppn"] = sorted(parsed_numbers)[-2]
            confidence += 0.2

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

    texts: list[str] = []
    confidence_values: list[float] = []
    for entry in responses:
        full_text = (entry.get("fullTextAnnotation") or {}).get("text")
        if not full_text:
            text_annotations = entry.get("textAnnotations") or []
            if text_annotations:
                full_text = text_annotations[0].get("description")
        if full_text:
            texts.append(full_text)

        pages = (entry.get("fullTextAnnotation") or {}).get("pages") or []
        for page in pages:
            if "confidence" in page:
                try:
                    confidence_values.append(flt(page.get("confidence")))
                except Exception:
                    continue

    text = "\n".join(texts).strip()
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
    for key, value in parsed.items():
        if key not in allowed_keys:
            continue

        fieldname = _get_fieldname(doctype, key)
        setattr(doc, fieldname, value)

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
    if company and target_doctype != "Expense Request":
        filters["company"] = company
    if target_doctype != "Expense Request":
        filters["docstatus"] = ("<", 2)
    return filters


def _check_duplicate_fp_no(current_name: str, fp_no: str, company: str | None, doctype: str) -> bool:
    if not fp_no:
        return False

    targets = ["Purchase Invoice", "Expense Request", "Sales Invoice"]
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


def verify_tax_invoice(doc: Any, *, doctype: str, force: bool = False) -> dict[str, Any]:
    settings = get_settings()
    notes: list[str] = []

    fp_no = _get_value(doc, doctype, "fp_no")
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
    pdf_field = _get_fieldname(doctype, "tax_invoice_pdf")
    job_name = f"tax-invoice-ocr-{doctype}-{docname}"
    job_info = _format_job_info(_pick_job_info(job_name), job_name)

    doc_info = {
        "name": docname,
        "doctype": doctype,
        "ocr_status": _get_value(doc, doctype, "ocr_status"),
        "verification_status": _get_value(doc, doctype, "status"),
        "ocr_confidence": _get_value(doc, doctype, "ocr_confidence"),
        "notes": _get_value(doc, doctype, "notes"),
        "fp_no": _get_value(doc, doctype, "fp_no"),
        "npwp": _get_value(doc, doctype, "npwp"),
        "tax_invoice_pdf": getattr(doc, pdf_field, None),
        "ocr_raw_json_present": bool(_get_value(doc, doctype, "ocr_raw_json")),
    }

    return {
        "doc": doc_info,
        "job": job_info,
        "job_name": job_name,
        "provider": settings.get("ocr_provider"),
        "max_retry": settings.get("ocr_max_retry"),
    }
