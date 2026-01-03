import frappe


def execute():
    """Ensure CoreTax export doctypes are present after updates.

    Some sites hit a missing DocType error when loading links to
    "CoreTax Export Settings". Reloading the doctypes guarantees they
    exist in the database during migration and refreshes dependent reports.
    """

    frappe.reload_doc("imogi_finance", "doctype", "coretax_export_settings")
    frappe.reload_doc("imogi_finance", "doctype", "coretax_column_mapping")
    frappe.reload_doc("imogi_finance", "doctype", "tax_profile_pph_account")
    frappe.reload_doc("imogi_finance", "doctype", "tax_profile")
    frappe.reload_doc("imogi_finance", "doctype", "tax_period_closing")
    frappe.reload_doc("imogi_finance", "report", "vat_input_register_verified")
    frappe.reload_doc("imogi_finance", "report", "vat_output_register_verified")
    frappe.reload_doc("imogi_finance", "report", "withholding_register")
    frappe.reload_doc("imogi_finance", "report", "pb1_register")
