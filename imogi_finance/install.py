import frappe


def before_install():
    """Clean up legacy custom fields that conflict with standard DocType fields."""
    duplicates = frappe.get_all(
        "Custom Field",
        filters={"dt": "Expense Request", "fieldname": "workflow_state"},
        pluck="name",
    )
    for name in duplicates:
        frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)
