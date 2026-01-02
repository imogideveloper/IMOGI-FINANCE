# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe


def ensure_coretax_export_doctypes() -> None:
	"""Ensure CoreTax export doctypes exist for linked fields."""
	missing_doctypes = []
	for doctype in (
		"CoreTax Export Settings",
		"CoreTax Column Mapping",
		"Tax Profile PPh Account",
	):
		if not frappe.db.exists("DocType", doctype):
			missing_doctypes.append(doctype)

	if not missing_doctypes:
		return

	frappe.reload_doc("imogi_finance", "doctype", "coretax_export_settings")
	frappe.reload_doc("imogi_finance", "doctype", "coretax_column_mapping")
	frappe.reload_doc("imogi_finance", "doctype", "tax_profile_pph_account")
