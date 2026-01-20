app_name = "imogi_finance"
app_title = "Imogi Finance"
app_publisher = "Imogi"
app_description = "App for Manage Expense IMOGI"
app_email = "imogi.indonesia@gmail.com"
app_license = "mit"
# app_logo_url = "/private/files/logo polt.svg"  # Set via Workspace Settings after upload
app_color = "#2490EF"

from imogi_finance.api.payroll_sync import is_payroll_installed

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "imogi_finance",
# 		"logo": "/assets/imogi_finance/logo.png",
# 		"title": "Imogi Finance",
# 		"route": "/imogi_finance",
# 		"has_permission": "imogi_finance.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/imogi_finance/css/imogi_finance.css"
# app_include_js = "/assets/imogi_finance/js/imogi_finance.js"

# include js, css files in header of web template
# web_include_css = "/assets/imogi_finance/css/imogi_finance.css"
# web_include_js = "/assets/imogi_finance/js/imogi_finance.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "imogi_finance/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Bank Transaction": "public/js/bank_transaction.js",
    "Payment Entry": "public/js/payment_entry.js",
    "Payment Request": "public/js/payment_request.js",
    "Purchase Invoice": [
        "public/js/purchase_invoice_tax_invoice.js",
        "public/js/advance_payment_allocation.js",
    ],
    "Expense Claim": "public/js/advance_payment_allocation.js",
    "Payroll Entry": "public/js/advance_payment_allocation.js",
    "Sales Invoice": "public/js/sales_invoice_tax_invoice.js",
}
doctype_list_js = {
    "BCA Bank Statement Import": "imogi_finance/doctype/bca_bank_statement_import/bca_bank_statement_import_list.js",
    "Administrative Payment Voucher": "imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher_list.js",
    "Expense Request": "imogi_finance/doctype/expense_request/expense_request_list.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "imogi_finance/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
jinja = {
    "methods": [
        "imogi_finance.receipt_control.utils.terbilang_id",
        "imogi_finance.receipt_control.utils.build_verification_url",
        "imogi_finance.receipt_control.utils.requires_materai",
        "imogi_finance.receipt_control.utils.get_default_receipt_design",
    ]
}

# Installation
# ------------

before_install = "imogi_finance.install.before_install"
# after_install = "imogi_finance.install.after_install"
after_install = "imogi_finance.utils.ensure_coretax_export_doctypes"

# Migration safeguards
# (see consolidated before_migrate hook near the bottom of this file)

fixtures = [
    {"doctype": "Custom Field", "filters": {"module": "Imogi Finance"}},
    {"doctype": "Role", "filters": {"name": ["in", ["Expense Approver", "Branch Approver"]]}},
    {"doctype": "Workflow State", "filters": {"name": ["like", "Imogi%"]}},
    {
        "doctype": "Workflow",
        "filters": {
            "document_type": [
                "in",
                [
                    "Expense Request",
                    "Internal Charge Request",
                    "Branch Expense Request",
                ],
            ]
        },
    },
    {"doctype": "Letter Template", "filters": {"module": "Imogi Finance"}},
    {"doctype": "Letter Template Settings", "filters": {"name": ["=", "Letter Template Settings"]}},
    {"doctype": "Tax Invoice Type", "filters": {"module": "Imogi Finance"}},
    {"doctype": "Workspace", "filters": {"module": "Imogi Finance"}},
    {"doctype": "Client Script", "filters": {"dt": ["in", ["Purchase Invoice", "Payment Entry"]]}},
    # DocTypes for deferred expense and tax export functionality
    {"doctype": "Expense Deferred Settings"},
    {"doctype": "CoreTax Export Settings"},
    {"doctype": "CoreTax Column Mapping"},
    {"doctype": "Tax Profile PPh Account"},
    {"doctype": "Tax Profile PB1 Account"},
    "fixtures/item.json",
]

# Uninstallation
# ------------

# before_uninstall = "imogi_finance.uninstall.before_uninstall"
# after_uninstall = "imogi_finance.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "imogi_finance.utils.before_app_install"
# after_app_install = "imogi_finance.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "imogi_finance.utils.before_app_uninstall"
# after_app_uninstall = "imogi_finance.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "imogi_finance.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
    "Sales Invoice": "imogi_finance.overrides.sales_invoice.CustomSalesInvoice",
    "Payment Request": "imogi_finance.overrides.payment_request.CustomPaymentRequest",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Bank Statement Import": {
        "before_insert": "imogi_finance.imogi_finance.events.bank_statement_import_handler.bank_statement_import_on_before_insert",
        "before_submit": "imogi_finance.imogi_finance.events.bank_statement_import_handler.bank_statement_import_before_submit",
    },
    "Purchase Invoice": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
            "imogi_finance.validators.finance_validator.validate_document_tax_fields",
            "imogi_finance.advance_payment.api.on_reference_update",
        ],
        "before_submit": "imogi_finance.events.purchase_invoice.validate_before_submit",
        "on_submit": [
            "imogi_finance.events.purchase_invoice.on_submit",
            "imogi_finance.advance_payment.api.on_reference_update",
        ],
        "on_update_after_submit": "imogi_finance.advance_payment.api.on_reference_update",
        "before_cancel": "imogi_finance.events.purchase_invoice.before_cancel",
        "on_cancel": [
            "imogi_finance.events.purchase_invoice.on_cancel",
            "imogi_finance.advance_payment.api.on_reference_cancel",
        ],
        "before_delete": "imogi_finance.events.purchase_invoice.before_delete",
        "on_trash": "imogi_finance.events.purchase_invoice.on_trash",
    },
    "Sales Invoice": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
            "imogi_finance.validators.finance_validator.validate_document_tax_fields",
        ]
    },
    "Expense Request": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
            "imogi_finance.events.expense_request.validate_workflow_action",
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_update": [
            "imogi_finance.events.expense_request.sync_status_with_workflow",
            "imogi_finance.events.expense_request.handle_budget_workflow",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.expense_request.sync_status_with_workflow",
            "imogi_finance.events.expense_request.handle_budget_workflow",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },
    "Internal Charge Request": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_update": [
            "imogi_finance.events.internal_charge_request.sync_status_with_workflow",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.internal_charge_request.sync_status_with_workflow",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },
    "Branch Expense Request": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_update": [
            "imogi_finance.events.branch_expense_request.sync_status_with_workflow",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.branch_expense_request.sync_status_with_workflow",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },
    "Additional Budget Request": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Administrative Payment Voucher": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Advance Payment Entry": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Budget Control Entry": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Budget Reclass Request": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Cash Bank Daily Report": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Customer Receipt": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Tax Invoice OCR Upload": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Tax Invoice Upload": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Tax Payment Batch": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Tax Period Closing": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Transfer Application": {
        "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
        "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
    },
    "Payment Entry": {
        "validate": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
            "imogi_finance.transfer_application.payment_entry_hooks.validate_transfer_application_link",
            "imogi_finance.advance_payment.workflow.on_payment_entry_validate",
            "imogi_finance.events.payment_entry.sync_expense_request_reference",
        ],
        "after_insert": [
            "imogi_finance.events.payment_entry.after_insert",
        ],
        "on_update": [
            "imogi_finance.events.payment_entry.on_update",
        ],
        "before_submit": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
            "imogi_finance.events.payment_entry.sync_expense_request_reference",
        ],
        "on_submit": [
            "imogi_finance.events.payment_entry.on_submit",
            "imogi_finance.receipt_control.payment_entry_hooks.record_payment_entry",
            "imogi_finance.transfer_application.payment_entry_hooks.on_submit",
            "imogi_finance.advance_payment.workflow.on_payment_entry_submit",
        ],
        "before_cancel": [
            "imogi_finance.events.payment_entry.before_cancel",
        ],
        "on_cancel": [
            "imogi_finance.events.payment_entry.on_cancel",
            "imogi_finance.receipt_control.payment_entry_hooks.remove_payment_entry",
            "imogi_finance.transfer_application.payment_entry_hooks.on_cancel",
            "imogi_finance.advance_payment.workflow.on_payment_entry_cancel",
        ],
        "before_delete": "imogi_finance.events.payment_entry.before_delete",
        "on_trash": [
            "imogi_finance.events.payment_entry.on_trash",
        ],
        "on_update_after_submit": [
            "imogi_finance.advance_payment.workflow.on_payment_entry_update_after_submit",
        ],
    },
    "Bank Transaction": {
        "before_cancel": "imogi_finance.events.bank_transaction.before_cancel",
        "on_submit": "imogi_finance.transfer_application.matching.handle_bank_transaction",
        "on_update_after_submit": "imogi_finance.transfer_application.matching.handle_bank_transaction",
    },
    "Expense Claim": {
        "on_submit": "imogi_finance.advance_payment.api.on_reference_update",
        "on_update_after_submit": "imogi_finance.advance_payment.api.on_reference_update",
        "on_cancel": "imogi_finance.advance_payment.api.on_reference_cancel",
    },
    "Payroll Entry": {
        "on_submit": "imogi_finance.advance_payment.api.on_reference_update",
        "on_update_after_submit": "imogi_finance.advance_payment.api.on_reference_update",
        "on_cancel": "imogi_finance.advance_payment.api.on_reference_cancel",
    },
}

if is_payroll_installed():
    doc_events.setdefault("Salary Slip", {}).update(
        {
            "on_submit": "imogi_finance.api.payroll_sync.handle_salary_slip_submit",
            "on_cancel": "imogi_finance.api.payroll_sync.handle_salary_slip_cancel",
        }
    )

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "imogi_finance.reporting.tasks.run_daily_reporting",
        "imogi_finance.services.tax_invoice_service.sync_pending_tax_invoices",
    ],
    "monthly": [
        "imogi_finance.reporting.tasks.run_monthly_reconciliation",
    ],
}

# Testing
# -------

# before_tests = "imogi_finance.install.before_tests"

# Run fixture sanitization first to avoid malformed rows during migrate,
# then ensure CoreTax export doctypes are present.
before_migrate = [
    "imogi_finance.fixtures.sanitize_fixture_files",
    "imogi_finance.utils.ensure_coretax_export_doctypes",
]
after_migrate = "imogi_finance.utils.ensure_coretax_export_doctypes"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
    "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry": "imogi_finance.overrides.payment_entry.get_payment_entry"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "imogi_finance.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["imogi_finance.utils.before_request"]
# after_request = ["imogi_finance.utils.after_request"]

# Job Events
# ----------
# before_job = ["imogi_finance.utils.before_job"]
# after_job = ["imogi_finance.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"imogi_finance.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
