# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

from pathlib import Path

import frappe


def ensure_coretax_export_doctypes() -> None:
	"""Ensure CoreTax export doctypes exist for linked fields."""
	doctype_map = {
		"CoreTax Export Settings": "coretax_export_settings",
		"CoreTax Column Mapping": "coretax_column_mapping",
		"Tax Profile PPh Account": "tax_profile_pph_account",
	}

	missing_doctypes = [name for name in doctype_map if not frappe.db.exists("DocType", name)]
	if not missing_doctypes:
		return

	doctype_root = Path(frappe.get_app_path("imogi_finance", "imogi_finance", "doctype"))
	for doctype in missing_doctypes:
		module_name = doctype_map[doctype]
		doctype_definition = doctype_root / module_name / f"{module_name}.json"
		if doctype_definition.exists():
			frappe.reload_doc("imogi_finance", "doctype", module_name)
		else:
			frappe.log_error(
				message=f"Skipped reload for missing CoreTax DocType definition: {doctype_definition}",
				title="CoreTax DocType definition not found",
			)
