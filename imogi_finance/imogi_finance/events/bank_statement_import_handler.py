"""
Hooks untuk native Bank Statement Import
Extend native parsing dengan bank-specific configuration dari Bank Statement Bank List
"""

import frappe
from frappe.utils.file_manager import get_file_path
from frappe.utils.data import getdate
import csv
import io
import hashlib


def bank_statement_import_on_before_insert(doc, method):
    """Validate imogi_bank selection saat insert."""
    if not doc.imogi_bank:
        frappe.throw(frappe.utils._("Bank (imogi_bank) is required."))
    
    # Set hash_id untuk duplicate detection
    if hasattr(doc, 'import_file') and doc.import_file:
        try:
            file_path = get_file_path(doc.import_file)
            with open(file_path, "rb") as f:
                file_bytes = f.read()
            
            hash_id = hashlib.sha256(file_bytes).hexdigest()
            
            # Check duplicate
            existing = frappe.db.get_value(
                "Bank Statement Import",
                {"hash_id": hash_id},
                "name"
            )
            if existing and existing != doc.name:
                frappe.throw(
                    frappe.utils._("This file has already been imported as {0}").format(existing)
                )
            
            doc.hash_id = hash_id
        except Exception as e:
            frappe.logger().warning(f"Could not generate hash: {str(e)}")


def bank_statement_import_before_submit(doc, method):
    """Parse CSV dengan bank-specific configuration sebelum submit."""
    if not doc.imogi_bank:
        frappe.throw(frappe.utils._("Bank (imogi_bank) must be selected before submitting."))
    
    try:
        # Load bank config
        config_doc = frappe.get_doc("Bank Statement Bank List", doc.imogi_bank)
        
        if not config_doc.enabled:
            frappe.throw(
                frappe.utils._("Bank configuration for {0} is disabled.").format(doc.imogi_bank)
            )
        
        # Get header map dari config
        header_map = {}
        for alias_row in (config_doc.header_aliases or []):
            aliases = [a.strip() for a in (alias_row.aliases or "").split(",") if a.strip()]
            if aliases:
                header_map[alias_row.fieldname] = aliases
        
        # Get skip markers
        skip_markers = tuple(
            m.strip().lower() 
            for m in (config_doc.skip_markers or "").split(",") 
            if m.strip()
        ) if config_doc.skip_markers else ()
        
        # Parse CSV
        if doc.import_file:
            file_path = get_file_path(doc.import_file)
            with open(file_path, "rb") as f:
                decoded = f.read().decode("utf-8-sig")
            
            # Simple CSV parsing dengan header map
            reader = csv.DictReader(io.StringIO(decoded))
            
            # Normalize headers
            if reader.fieldnames:
                normalized_headers = {_normalize_header(h): h for h in reader.fieldnames}
                
                # Build field map
                field_map = {}
                for fieldname, aliases in header_map.items():
                    for alias in aliases:
                        normalized_alias = _normalize_header(alias)
                        if normalized_alias in normalized_headers:
                            field_map[fieldname] = normalized_headers[normalized_alias]
                            break
                
                # Parse rows
                doc.import_rows = []
                row_count = 0
                
                for row_idx, row in enumerate(reader, 1):
                    if not row or all(not (v or "").strip() for v in row.values()):
                        continue
                    
                    # Check skip markers
                    posting_date_header = field_map.get("posting_date")
                    description_header = field_map.get("description")
                    
                    should_skip = False
                    if posting_date_header and row.get(posting_date_header):
                        date_val = _normalize_header(row.get(posting_date_header, ""))
                        if any(date_val.startswith(m) for m in skip_markers):
                            should_skip = True
                    
                    if description_header and row.get(description_header):
                        desc_val = _normalize_header(row.get(description_header, ""))
                        if any(m in desc_val for m in skip_markers):
                            should_skip = True
                    
                    if should_skip:
                        continue
                    
                    try:
                        # Get values
                        posting_date_str = row.get(field_map.get("posting_date"), "")
                        description = row.get(field_map.get("description"), "")
                        reference_number = row.get(field_map.get("reference_number"), "")
                        debit_str = row.get(field_map.get("debit"), "")
                        credit_str = row.get(field_map.get("credit"), "")
                        balance_str = row.get(field_map.get("balance"), "")
                        
                        if not posting_date_str:
                            continue
                        
                        # Parse amounts
                        debit = _parse_amount(debit_str) if debit_str else 0
                        credit = _parse_amount(credit_str) if credit_str else 0
                        balance = _parse_amount(balance_str) if balance_str else 0
                        
                        # Add row to import_rows
                        doc.append("import_rows", {
                            "date": posting_date_str,
                            "description": description,
                            "reference_number": reference_number,
                            "debit": debit,
                            "credit": credit,
                            "balance": balance,
                        })
                        
                        row_count += 1
                    except Exception as e:
                        frappe.logger().warning(f"Row {row_idx} parse error: {str(e)}")
                        continue
                
                if row_count == 0:
                    frappe.throw(
                        frappe.utils._("No transaction rows found in the file.")
                    )
                
                doc.import_status = "Processed"
    
    except frappe.DoesNotExistError:
        frappe.throw(
            frappe.utils._("Bank Statement Bank List configuration not found for bank: {0}").format(doc.imogi_bank)
        )
    except Exception as e:
        frappe.throw(
            frappe.utils._("Error parsing CSV: {0}").format(str(e))
        )


def _normalize_header(header: str) -> str:
    """Normalize header untuk comparison."""
    return (header or "").lower().strip().replace("_", "").replace(" ", "")


def _parse_amount(value: str) -> float:
    """Parse amount dari string."""
    if not value:
        return 0
    
    # Clean
    cleaned = (value or "").strip()
    cleaned = cleaned.replace(",", "").replace(".", "")
    
    # Check markers
    for marker in ("cr", "db", "dr"):
        if marker in cleaned.lower():
            cleaned = cleaned.lower().replace(marker, "").strip()
            break
    
    try:
        return float(cleaned) if cleaned else 0
    except:
        return 0
