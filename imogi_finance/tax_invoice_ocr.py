from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import frappe
from frappe import _
from frappe.exceptions import ValidationError
from frappe.utils import cint, flt, get_site_path
from frappe.utils.formatters import format_value

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
}

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

    settings = frappe._dict(DEFAULT_SETTINGS.copy())
    record = frappe.db.get_singles_dict(SETTINGS_DOCTYPE) or {}
    settings.update(record)
    return settings


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


def parse_faktur_pajak_text(text: str) -> tuple[dict[str, Any], float]:
    matches: dict[str, Any] = {}
    confidence = 0.0

    npwp_match = NPWP_REGEX.search(text or "")
    if npwp_match:
        matches["npwp"] = normalize_npwp(npwp_match.group("npwp"))
        confidence += 0.25

    fp_match = TAX_INVOICE_REGEX.search(text or "")
    if fp_match:
        matches["fp_no"] = fp_match.group("fp").replace(".", "").replace("-", "")
        confidence += 0.25

    date_match = DATE_REGEX.search(text or "")
    if date_match:
        try:
            parsed = datetime.strptime(date_match.group("date"), "%d-%m-%Y")
        except Exception:
            try:
                parsed = datetime.strptime(date_match.group("date"), "%d/%m/%Y")
            except Exception:
                parsed = None
        if parsed:
            matches["fp_date"] = parsed.date().isoformat()
            confidence += 0.15

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

    matches.setdefault("ppn_type", get_settings().get("default_ppn_type", "Standard"))

    return matches, round(min(confidence, 0.95), 2)


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


def ocr_extract_text_from_pdf(file_url: str, provider: str) -> tuple[str, dict[str, Any] | None, float]:
    if provider == "Manual Only":
        raise ValidationError(_("OCR provider not configured. Please select an OCR provider."))

    if provider == "Google Vision":
        raise ValidationError(_("Google Vision OCR is not configured. Please add credentials."))

    raise ValidationError(_("OCR provider {0} is not supported.").format(provider))


def _update_doc_after_ocr(
    doc: Any, doctype: str, parsed: dict[str, Any], confidence: float, raw_json: dict[str, Any] | None = None
):
    setattr(doc, _get_fieldname(doctype, "status"), "Needs Review")
    setattr(doc, _get_fieldname(doctype, "ocr_status"), "Done")
    setattr(doc, _get_fieldname(doctype, "ocr_confidence"), confidence)
    for key, value in parsed.items():
        fieldname = _get_fieldname(doctype, key)
        setattr(doc, fieldname, value)
    if raw_json is not None:
        setattr(doc, _get_fieldname(doctype, "ocr_raw_json"), json.dumps(raw_json, indent=2))
    doc.save(ignore_permissions=True)


def _enqueue_ocr(doc: Any, doctype: str):
    settings = get_settings()
    pdf_field = _get_fieldname(doctype, "tax_invoice_pdf")
    _validate_pdf_size(getattr(doc, pdf_field, None), cint(settings.get("ocr_file_max_mb", 10)))

    doc.db_set(_get_fieldname(doctype, "ocr_status"), "Processing")
    provider = settings.get("ocr_provider", "Manual Only")

    def _job(name: str, target_doctype: str):
        target_doc = frappe.get_doc(target_doctype, name)
        try:
            text, raw_json, confidence = ocr_extract_text_from_pdf(
                getattr(target_doc, pdf_field), provider
            )
            parsed, estimated_confidence = parse_faktur_pajak_text(text or "")
            _update_doc_after_ocr(
                target_doc, target_doctype, parsed, confidence or estimated_confidence, raw_json
            )
        except Exception as exc:
            target_doc.db_set(
                {
                    _get_fieldname(target_doctype, "ocr_status"): "Failed",
                    _get_fieldname(target_doctype, "notes"): getattr(exc, "message", None) or str(exc),
                }
            )
            frappe.log_error(frappe.get_traceback(), "Tax Invoice OCR failed")

    frappe.enqueue(
        _job,
        queue="long",
        job_name=f"tax-invoice-ocr-{doctype}-{doc.name}",
        timeout=300,
        now=getattr(frappe.flags, "in_test", False),
        is_async=not getattr(frappe.flags, "in_test", False),
        **{"name": doc.name, "target_doctype": doctype},
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
    company = getattr(doc, "company", None) or getattr(doc, "cost_center", None)

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

    doc = frappe.get_doc(doctype, docname)
    _enqueue_ocr(doc, doctype)
    return {"queued": True}
