import frappe


def execute():
    """Align selected workspace modules with the requested sidebar groups."""
    if not frappe.db.table_exists("Workspace"):
        return

    workspace_modules = {
        "Garage": "Sales",
        "Assets": "Inventory",
        "Buying": "Purchase",
        "Selling": "Sales",
    }

    for workspace, module in workspace_modules.items():
        if frappe.db.exists("Workspace", workspace):
            frappe.db.set_value("Workspace", workspace, "module", module)
