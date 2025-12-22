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

        try:
            file_bytes, parsed_rows = parse_bca_csv(self.source_file)
            self._guard_against_duplicate_upload(file_bytes)
            self._replace_rows(parsed_rows)
            self._mark_parsed()
            self.save(ignore_permissions=True)
        except Exception:
            self.import_status = "Failed"
            self.save(ignore_permissions=True)
            raise

        return {"parsed_rows": len(parsed_rows), "hash_id": self.hash_id}

    @frappe.whitelist()
    def convert_to_bank_transaction(self) -> dict:
        self._assert_parse_completed()

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


def parse_bca_csv(file_url: str) -> tuple[bytes, list[ParsedStatementRow]]:
    file_path = get_file_path(file_url)

    with open(file_path, "rb") as handle:
        file_bytes = handle.read()

    decoded = file_bytes.decode("utf-8-sig")
    dialect = detect_csv_dialect(decoded)
    reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)

    if not reader.fieldnames:
        frappe.throw(_("The CSV file does not contain a header row."))

    field_map = map_headers(reader.fieldnames)
    parsed_rows: list[ParsedStatementRow] = []

    for index, raw_row in enumerate(reader, start=1):
        if not raw_row or all(not (value or "").strip() for value in raw_row.values()):
            continue

        try:
            parsed_rows.append(parse_row(raw_row, field_map))
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

    posting_date = getdate(posting_date_raw)
    description = get_value("description")
    reference_number = get_value("reference_number") or None
    debit = parse_amount(get_value("debit"))
    credit = parse_amount(get_value("credit"))
    balance = parse_amount(get_value("balance"))
    currency = get_value("currency") or "IDR"

    if debit and credit:
        raise frappe.ValidationError(_("Debit and Credit cannot both be set in the same row."))

    if not debit and not credit:
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


def parse_amount(value: str) -> float | None:
    cleaned = (value or "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return flt(cleaned)
    except ValueError as exc:
        raise frappe.ValidationError(_("Invalid amount: {0}").format(value)) from exc


def map_headers(fieldnames: Iterable[str]) -> dict[str, str]:
    normalized = {normalize_header(header): header for header in fieldnames}

    header_map = {
        "posting_date": find_header(
            normalized, ("tanggal transaksi", "tanggal", "tgl", "tgl transaksi", "tanggal mutasi")
        ),
        "description": find_header(
            normalized, ("keterangan", "keterangan transaksi", "uraian", "deskripsi", "description")
        ),
        "reference_number": find_header(
            normalized, ("no. referensi", "nomor referensi", "reference number", "no referensi")
        ),
        "debit": find_header(normalized, ("mutasi debet", "mutasi debit", "debet", "debit")),
        "credit": find_header(normalized, ("mutasi kredit", "kredit", "credit")),
        "balance": find_header(normalized, ("saldo akhir", "saldo", "balance", "saldo mutasi")),
        "currency": find_header(normalized, ("currency", "mata uang")),
    }

    required_keys = ["posting_date", "description", "debit", "credit", "balance"]
    missing = [key for key in required_keys if not header_map.get(key)]

    if missing:
        label_map = {
            "posting_date": _("Posting Date"),
            "description": _("Description"),
            "debit": _("Debit"),
            "credit": _("Credit"),
            "balance": _("Balance"),
        }
        missing_labels = [label_map.get(key, key) for key in missing]
        frappe.throw(_("Missing required columns in CSV: {0}.").format(", ".join(missing_labels)))

    return header_map


def normalize_header(header: str) -> str:
    return (header or "").strip().lower()


def find_header(normalized_map: dict[str, str], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        for normalized, original in normalized_map.items():
            if normalized == candidate or candidate in normalized:
                return original
    return None


def detect_csv_dialect(decoded: str) -> csv.Dialect:
    try:
        sample = decoded[:2048]
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except Exception:
        return csv.get_dialect("excel")


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
        "posting_date": row.posting_date,
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
    bank_transaction.posting_date = row.posting_date
    bank_transaction.description = row.description
    bank_transaction.reference_number = row.reference_number
    bank_transaction.deposit = row.credit
    bank_transaction.withdrawal = row.debit
    bank_transaction.balance = row.balance
    bank_transaction.currency = row.currency
    bank_transaction.insert(ignore_permissions=True)

    return bank_transaction
