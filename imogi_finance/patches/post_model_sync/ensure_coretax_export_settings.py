import frappe


def execute():
    """Ensure CoreTax export doctypes are present after updates.

    Some sites hit a missing DocType error when loading links to
    "CoreTax Export Settings". Reloading the doctypes guarantees they
    exist in the database during migration.
    """

    frappe.reload_doc("imogi_finance", "doctype", "coretax_export_settings")
    frappe.reload_doc("imogi_finance", "doctype", "coretax_column_mapping")
