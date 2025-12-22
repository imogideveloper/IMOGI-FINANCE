# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from typing import Iterable

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime
from frappe.utils.data import getdate
from frappe.utils.file_manager import get_file_path


class DuplicateUploadError(frappe.ValidationError):
    """Raised when a statement file has already been uploaded and parsed."""


class DuplicateTransactionError(frappe.ValidationError):
    """Raised when a matching Bank Transaction already exists."""


class SkipRow(Exception):
    """Internal control exception to skip non-transaction rows."""


@dataclass
class ParsedStatementRow:
    posting_date: str
    description: str
    reference_number: str | None
    debit: float
    credit: float
    balance: float | None
    currency: str


class BCABankStatementImport(Document):
    """Staging DocType to parse BCA CSV files and create native Bank Transactions."""

    @frappe.whitelist()
    def parse_csv(self) -> dict:
        self._assert_source_file_present()

        conversion_result: dict | None = None

        try:
            file_bytes, parsed_rows = parse_bca_csv(self.source_file)
            self._guard_against_duplicate_upload(file_bytes)
            self._replace_rows(parsed_rows)
            self._update_summary_fields()
            self._mark_parsed()
            self.save(ignore_permissions=True)
            conversion_result = self.convert_to_bank_transaction()
        except Exception:
            self.import_status = "Failed"
            self.save(ignore_permissions=True)
            raise

        response = {"parsed_rows": len(parsed_rows), "hash_id": self.hash_id}

        if conversion_result:
            response["conversion"] = conversion_result

        return response

    @frappe.whitelist()
    def convert_to_bank_transaction(self) -> dict:
        self._assert_parse_completed()
        self._assert_bank_account_present()

        created = 0
        duplicates = 0
        failures = 0

        for row in self.get("statement_rows", []):
            if row.convert_status == "Converted":
                continue

            try:
                bank_transaction = create_bank_transaction_from_row(
                    row,
                    company=self.company,
                    bank_account=self.bank_account,
                    bank=self.bank,
                )
            except DuplicateTransactionError as exc:
                row.convert_status = "Converted"
                row.bank_transaction = str(exc)
                duplicates += 1
                row.error_message = None
                continue
            except Exception as exc:
                row.convert_status = "Failed"
                row.error_message = frappe.get_traceback() if frappe.conf.developer_mode else str(exc)
                failures += 1
                continue

            row.convert_status = "Converted"
            row.bank_transaction = bank_transaction.name
            row.error_message = None
            created += 1

        self.import_status = "Converted" if failures == 0 else "Failed"
        self.save(ignore_permissions=True)

        return {
            "created": created,
            "duplicates": duplicates,
            "failures": failures,
            "total_rows": len(self.get("statement_rows", [])),
        }

    def _assert_source_file_present(self) -> None:
        if not self.source_file:
            frappe.throw(_("Please attach a CSV file from BCA before parsing."))

    def _guard_against_duplicate_upload(self, file_bytes: bytes) -> None:
        self.hash_id = hashlib.sha256(file_bytes).hexdigest()
        existing_name = frappe.db.get_value(
            "BCA Bank Statement Import",
            {"hash_id": self.hash_id},
            "name",
        )
        if existing_name and existing_name != self.name:
            raise DuplicateUploadError(
                _("This statement file has already been uploaded as {0}.").format(existing_name)
            )

    def _replace_rows(self, parsed_rows: Iterable[ParsedStatementRow]) -> None:
        self.set("statement_rows", [])
        for parsed in parsed_rows:
            self.append(
                "statement_rows",
                {
                    "posting_date": parsed.posting_date,
                    "description": parsed.description,
                    "reference_number": parsed.reference_number,
                    "debit": parsed.debit,
                    "credit": parsed.credit,
                    "balance": parsed.balance,
                    "currency": parsed.currency,
                    "convert_status": "Not Converted",
                },
            )

    def _update_summary_fields(self) -> None:
        rows = self.get("statement_rows", [])
        if not rows:
            self.starting_balance = None
            self.total_debit = None
            self.total_credit = None
            self.ending_balance = None
            return

        self.total_debit = sum(flt(row.debit) for row in rows)
        self.total_credit = sum(flt(row.credit) for row in rows)

        first_with_balance = next((row for row in rows if row.balance is not None), None)
        last_with_balance = next((row for row in reversed(rows) if row.balance is not None), None)

        starting_balance = None
        if first_with_balance:
            starting_balance = flt(first_with_balance.balance)
            starting_balance -= flt(first_with_balance.credit)
            starting_balance += flt(first_with_balance.debit)

        self.starting_balance = starting_balance
        self.ending_balance = flt(last_with_balance.balance) if last_with_balance else None

    def _mark_parsed(self) -> None:
        self.import_status = "Parsed"
        self.imported_on = now_datetime()
        self.imported_by = frappe.session.user
        self.bank = self.bank or "BCA"
        if not self.name:
            self.insert(ignore_permissions=True)

    def _assert_parse_completed(self) -> None:
        if self.import_status not in {"Parsed", "Converted", "Failed"}:
            frappe.throw(_("Please parse the CSV file before converting transactions."))
        if not self.get("statement_rows"):
            frappe.throw(_("No parsed rows available to convert. Please parse again."))

    def _assert_bank_account_present(self) -> None:
        if not self.bank_account:
            frappe.throw(_("Bank Account is required before converting transactions."))


def parse_bca_csv(file_url: str) -> tuple[bytes, list[ParsedStatementRow]]:
    file_path = get_file_path(file_url)

    with open(file_path, "rb") as handle:
        file_bytes = handle.read()

    decoded = strip_csv_preamble(file_bytes.decode("utf-8-sig"))
    reader, field_map = get_csv_reader_and_headers(decoded)
    parsed_rows: list[ParsedStatementRow] = []

    for index, raw_row in enumerate(reader, start=1):
        if not raw_row or all(not (value or "").strip() for value in raw_row.values()):
            continue

        try:
            parsed_rows.append(parse_row(raw_row, field_map))
        except SkipRow:
            continue
        except Exception as exc:
            error_detail = frappe.get_traceback() if frappe.conf.developer_mode else str(exc)
            raise frappe.ValidationError(_("Row {0}: {1}").format(index, error_detail)) from exc

    if not parsed_rows:
        frappe.throw(_("No transaction rows were found in the CSV file."))

    return file_bytes, parsed_rows


def parse_row(row: dict, field_map: dict[str, str]) -> ParsedStatementRow:
    def get_value(key: str) -> str:
        header = field_map.get(key)
        return (row.get(header, "") or "").strip() if header else ""

    posting_date_raw = get_value("posting_date")
    if not posting_date_raw:
        raise frappe.ValidationError(_("Posting Date is missing."))

    normalized_posting_date = normalize_header(posting_date_raw)
    normalized_description = normalize_header(get_value("description"))
    skip_markers = (
        "pend",
        "pending",
        "saldo awal",
        "saldo akhir",
        "mutasi debet",
        "mutasi debit",
        "mutasi kredit",
    )

    if any(
        normalized_posting_date == marker or normalized_posting_date.startswith(marker)
        for marker in skip_markers
    ):
        raise SkipRow

    if any(
        marker in normalized_description or normalized_description.startswith(marker)
        for marker in skip_markers
    ):
        raise SkipRow

    try:
        posting_date = getdate(posting_date_raw)
    except Exception as exc:  # noqa: BLE001 - allow skipping pending markers
        raise
    description = get_value("description")
    reference_number = get_value("reference_number") or None
    debit, debit_type = parse_amount_with_marker(get_value("debit"), normalize_sign=True)
    credit, credit_type = parse_amount_with_marker(get_value("credit"), normalize_sign=True)
    amount, amount_type = parse_amount_with_marker(get_value("amount"), normalize_sign=True)
    balance = parse_amount(get_value("balance"))
    currency = get_value("currency") or "IDR"

    debit = debit or 0
    credit = credit or 0

    if debit_type == "credit":
        credit += debit
        debit = 0

    if credit_type == "debit":
        debit += credit
        credit = 0

    if not debit and not credit and amount is not None:
        if amount_type == "credit":
            credit = amount
        elif amount_type == "debit":
            debit = amount
        elif amount > 0:
            credit = amount
        elif amount < 0:
            debit = abs(amount)

    if debit and credit:
        raise frappe.ValidationError(_("Debit and Credit cannot both be set in the same row."))

    if not debit and not credit:
        if amount in (0, None) and balance is not None:
            raise SkipRow
        raise frappe.ValidationError(_("Either Debit or Credit must be provided."))

    return ParsedStatementRow(
        posting_date=str(posting_date),
        description=description,
        reference_number=reference_number,
        debit=debit or 0,
        credit=credit or 0,
        balance=balance,
        currency=currency,
    )

def parse_amount_with_marker(value: str, *, normalize_sign: bool) -> tuple[float | None, str | None]:
    cleaned = (value or "").strip()

    if not cleaned:
        return None, None

    marker = None
    for candidate in ("cr", "db", "dr"):
        if cleaned.lower().endswith(candidate):
            marker = candidate
            cleaned = cleaned[: -len(candidate)].strip()
            break

    cleaned = cleaned.replace(",", "")

    if not cleaned:
        return None, _map_marker_to_type(marker)

    try:
        amount = flt(cleaned)
    except ValueError as exc:
        raise frappe.ValidationError(_("Invalid amount: {0}").format(value)) from exc

    marker_type = _map_marker_to_type(marker)

    if normalize_sign and marker_type:
        amount = abs(amount)

    return amount, marker_type


def parse_amount(value: str) -> float | None:
    amount, _ = parse_amount_with_marker(value, normalize_sign=False)
    return amount


def _map_marker_to_type(marker: str | None) -> str | None:
    if marker == "cr":
        return "credit"
    if marker in {"db", "dr"}:
        return "debit"
    return None


def map_headers(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {normalize_header(header): header for header in fieldnames}

    alias_map = {
        "posting_date": (
            "tanggal transaksi",
            "transaction date",
            "posting date",
            "tanggal",
            "tgl",
            "tgl transaksi",
            "tanggal mutasi",
            "date",
        ),
        "description": (
            "keterangan",
            "keterangan transaksi",
            "uraian",
            "deskripsi",
            "description",
            "transaction description",
            "details",
            "remarks",
        ),
        "reference_number": ("no. referensi", "nomor referensi", "reference number", "no referensi"),
        "debit": ("mutasi debet", "mutasi debit", "debet", "debit", "withdrawal", "db"),
        "credit": ("mutasi kredit", "kredit", "credit", "deposit", "cr", "credit amount"),
        "balance": (
            "saldo akhir",
            "saldo",
            "balance",
            "saldo mutasi",
            "ending balance",
            "closing balance",
        ),
        "currency": ("currency", "mata uang"),
        "amount": ("jumlah", "nominal", "amount"),
    }

    def resolve(key: str) -> str | None:
        return find_header(normalized, alias_map[key])

    header_map = {
        "posting_date": resolve("posting_date"),
        "description": resolve("description"),
        "reference_number": resolve("reference_number"),
        "debit": resolve("debit"),
        "credit": resolve("credit"),
        "balance": resolve("balance"),
        "currency": resolve("currency"),
        "amount": resolve("amount"),
    }

    missing_labels = []

    if not header_map.get("posting_date"):
        missing_labels.append(_("Posting Date"))
    if not header_map.get("description"):
        missing_labels.append(_("Description"))
    if not header_map.get("balance"):
        missing_labels.append(_("Balance"))
    if not (header_map.get("debit") or header_map.get("credit") or header_map.get("amount")):
        missing_labels.append(_("Debit/Credit or Amount"))

    if missing_labels:
        frappe.throw(_("Missing required columns in CSV: {0}.").format(", ".join(missing_labels)))

    return header_map


def normalize_header(header: str) -> str:
    cleaned = (header or "").strip().lower()
    for char in ("_", "-", "/", "(", ")", "."):
        cleaned = cleaned.replace(char, " ")
    cleaned = " ".join(cleaned.split())
    return cleaned


def find_header(normalized_map: dict[str, str], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        candidate_normalized = normalize_header(candidate)
        for normalized, original in normalized_map.items():
            if normalized == candidate_normalized or candidate_normalized in normalized:
                return original
    return None


def detect_csv_dialect(decoded: str) -> csv.Dialect:
    try:
        sample = decoded[:2048]
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        return csv.get_dialect("excel")


def get_csv_reader_and_headers(decoded: str) -> tuple[csv.DictReader, dict[str, str]]:
    def build_reader_params(delimiter: str | None = None) -> dict:
        if delimiter:
            return {"delimiter": delimiter}
        return {"dialect": detect_csv_dialect(decoded)}

    def detect_header_row(params: dict) -> int | None:
        probe = io.StringIO(decoded)
        reader = csv.reader(probe, **params)
        for index, row in enumerate(reader):
            if index >= 15:
                break
            if _is_header_row(row):
                return index
        return None

    last_error: Exception | None = None

    for delimiter in (None, ",", ";", "\t"):
        params = build_reader_params(delimiter)
        header_index = detect_header_row(params)
        if header_index is None:
            last_error = frappe.ValidationError(
                _("Could not locate a header row. Please ensure the file contains a 'Tanggal Transaksi' column.")
            )
            continue

        stream = io.StringIO(decoded)
        pre_reader = csv.reader(stream, **params)
        for _ in range(header_index):
            next(pre_reader, None)

        fieldnames = next(pre_reader, None)
        if not fieldnames:
            last_error = frappe.ValidationError(_("The CSV file does not contain a header row."))
            continue

        try:
            field_map = map_headers(fieldnames)
        except Exception as exc:  # noqa: BLE001 - need to retry with alternate delimiters
            last_error = exc
            continue

        reader = csv.DictReader(stream, fieldnames=fieldnames, **params)

        if _has_collapsed_headers(fieldnames, field_map):
            last_error = frappe.ValidationError(
                _("The CSV headers could not be detected. Please ensure each column is separated correctly.")
            )
            continue

        return reader, field_map

    if last_error:
        raise last_error

    frappe.throw(_("Unable to read the CSV file."))


def _has_collapsed_headers(fieldnames: Iterable[str], field_map: dict[str, str]) -> bool:
    if not fieldnames:
        return True

    if len(list(fieldnames)) == 1:
        return True

    core_headers = [field_map.get(key) for key in ("posting_date", "description", "balance")]
    value_headers = [field_map.get(key) for key in ("debit", "credit") if field_map.get(key)]

    if not value_headers and field_map.get("amount"):
        value_headers.append(field_map.get("amount"))

    required_headers = [header for header in core_headers + value_headers if header]

    return len(set(required_headers)) != len(required_headers)


def _is_header_row(row: list[str]) -> bool:
    normalized = [normalize_header(cell) for cell in row]
    return any(header in {"tanggal transaksi", "transaction date"} for header in normalized)


def strip_csv_preamble(decoded: str) -> str:
    """Remove leading delimiter hints (e.g. ``sep=;``) and blank lines.

    Some CSV exports from spreadsheet tools start with a ``sep=`` instruction so
    the parser treats the file as a single-column CSV, which prevents header
    detection. We drop that preamble and any leading empty lines before building
    a DictReader.
    """

    cleaned: list[str] = []
    for line in decoded.splitlines():
        stripped = line.strip()
        if not cleaned and (not stripped or stripped.lower().startswith("sep=")):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)


def create_bank_transaction_from_row(
    row: Document,
    *,
    company: str,
    bank_account: str,
    bank: str | None = None,
) -> Document:
    amount = row.credit or row.debit
    filters = {
        "company": company,
        "bank_account": bank_account,
        "date": row.posting_date,
        "reference_number": row.reference_number,
    }

    if row.credit:
        filters["deposit"] = amount
    else:
        filters["withdrawal"] = amount

    existing = frappe.db.get_value("Bank Transaction", filters, "name")
    if existing:
        raise DuplicateTransactionError(existing)

    bank_transaction = frappe.new_doc("Bank Transaction")
    bank_transaction.company = company
    bank_transaction.bank_account = bank_account
    bank_transaction.bank = bank
    bank_transaction.date = row.posting_date
    bank_transaction.description = row.description
    bank_transaction.reference_number = row.reference_number
    bank_transaction.deposit = row.credit
    bank_transaction.withdrawal = row.debit
    bank_transaction.balance = row.balance
    bank_transaction.currency = row.currency
    bank_transaction.insert(ignore_permissions=True)

    return bank_transaction
