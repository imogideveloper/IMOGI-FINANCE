from __future__ import annotations


def get_data():
    return [
        {
            "module_name": "Imogi Finance",
            "category": "Modules",
            "label": "Imogi Finance",
            "color": "grey",
            "icon": "octicon octicon-briefcase",
            "type": "module",
            "hidden": 0,
            "items": [
                {
                    "type": "doctype",
                    "name": "Expense Request",
                    "label": "Expense Request",
                    "description": "Submit and track expense requests.",
                },
                {
                    "type": "doctype",
                    "name": "Expense Approval Setting",
                    "label": "Approval Settings",
                    "description": "Configure approval routes for expense requests.",
                },
                {
                    "type": "doctype",
                    "name": "Finance Control Settings",
                    "label": "Finance Control Settings",
                    "description": "Configure finance policies and controls.",
                },
                {
                    "type": "doctype",
                    "name": "BCA Bank Statement Import",
                    "label": "BCA Bank Statement Import",
                    "description": "Import and reconcile BCA bank statements.",
                },
                {
                    "type": "doctype",
                    "name": "Tax Invoice OCR Settings",
                    "label": "Tax Invoice OCR Settings",
                    "description": "Configure OCR for incoming tax invoices.",
                },
                {
                    "type": "doctype",
                    "name": "Tax Profile",
                    "label": "Tax Profile",
                    "description": "Maintain tax profile settings.",
                },
                {
                    "type": "doctype",
                    "name": "Receipt Design",
                    "label": "Receipt Design",
                    "description": "Manage customer receipt templates.",
                },
                {
                    "type": "doctype",
                    "name": "Tax Payment Batch",
                    "label": "Tax Payment Batch",
                    "description": "Group and process tax payments.",
                },
                {
                    "type": "doctype",
                    "name": "Tax Period Closing",
                    "label": "Tax Period Closing",
                    "description": "Close monthly tax periods.",
                },
                {
                    "type": "doctype",
                    "name": "Customer Receipt",
                    "label": "Customer Receipt",
                    "description": "Record and manage customer receipts.",
                },
                {
                    "type": "doctype",
                    "name": "Customer Receipt Item",
                    "label": "Customer Receipt Item",
                    "description": "Track items within customer receipts.",
                },
                {
                    "type": "doctype",
                    "name": "Customer Receipt Payment",
                    "label": "Customer Receipt Payment",
                    "description": "Payments associated with customer receipts.",
                },
                {
                    "type": "doctype",
                    "name": "Customer Receipt Stamp Log",
                    "label": "Customer Receipt Stamp Log",
                    "description": "Log of digital stamp usage on receipts.",
                },
                {
                    "type": "doctype",
                    "name": "Digital Stamp Template",
                    "label": "Digital Stamp Template",
                    "description": "Templates for digital stamping on receipts.",
                },
                {
                    "type": "report",
                    "is_query_report": False,
                    "name": "VAT Input Register Verified",
                    "label": "VAT Input Register Verified",
                    "doctype": "VAT Input Register Verified",
                    "description": "Verified VAT input register.",
                },
                {
                    "type": "report",
                    "is_query_report": False,
                    "name": "VAT Output Register Verified",
                    "label": "VAT Output Register Verified",
                    "doctype": "VAT Output Register Verified",
                    "description": "Verified VAT output register.",
                },
                {
                    "type": "report",
                    "is_query_report": False,
                    "name": "Withholding Register",
                    "label": "Withholding Register",
                    "doctype": "Withholding Register",
                    "description": "Withholding tax register.",
                },
                {
                    "type": "report",
                    "is_query_report": False,
                    "name": "PB1 Register",
                    "label": "PB1 Register",
                    "doctype": "PB1 Register",
                    "description": "PB1 register.",
                },
                {
                    "type": "doctype",
                    "name": "Budget Control Settings",
                    "label": "Budget Control Settings",
                    "description": "Configure budget lock, allocation, and internal charge options.",
                },
                {
                    "type": "doctype",
                    "name": "Budget Control Entry",
                    "label": "Budget Control Entry",
                    "description": "Ledger of budget reservations, consumption, and supplements.",
                },
                {
                    "type": "doctype",
                    "name": "Additional Budget Request",
                    "label": "Additional Budget Request",
                    "description": "Request to top up allocated budget.",
                },
                {
                    "type": "doctype",
                    "name": "Budget Reclass Request",
                    "label": "Budget Reclass Request",
                    "description": "Request to move budget between cost centers or accounts.",
                },
                {
                    "type": "doctype",
                    "name": "Internal Charge Request",
                    "label": "Internal Charge Request",
                    "description": "Allocate expense requests across cost centers.",
                },
            ],
        }
    ]
