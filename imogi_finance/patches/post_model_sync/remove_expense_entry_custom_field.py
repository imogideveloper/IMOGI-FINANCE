import frappe


def execute():
    custom_field_name = "Purchase Invoice-expense_entry"
    if frappe.db.exists("Custom Field", custom_field_name):
        frappe.delete_doc("Custom Field", custom_field_name, ignore_missing=True)
