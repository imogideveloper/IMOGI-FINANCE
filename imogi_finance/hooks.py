app_name = "imogi_finance"
app_title = "Imogi Finance"
app_publisher = "Imogi"
app_description = "App for Manage Expense IMOGI"
app_email = "imogi.indonesia@gmail.com"
app_license = "mit"

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
    "Purchase Invoice": "public/js/purchase_invoice_tax_invoice.js",
    "Sales Invoice": "public/js/sales_invoice_tax_invoice.js",
}
doctype_list_js = {
    "BCA Bank Statement Import": "imogi_finance/doctype/bca_bank_statement_import/bca_bank_statement_import_list.js",
    "Administrative Payment Voucher": "imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher_list.js",
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
    ]
}

# Installation
# ------------

before_install = "imogi_finance.install.before_install"
# after_install = "imogi_finance.install.after_install"
after_install = "imogi_finance.utils.ensure_coretax_export_doctypes"

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

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Purchase Invoice": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
        ],
        "before_submit": "imogi_finance.events.purchase_invoice.validate_before_submit",
        "on_submit": "imogi_finance.events.purchase_invoice.on_submit",
        "on_cancel": "imogi_finance.events.purchase_invoice.on_cancel",
    },
    "Sales Invoice": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
        ]
    },
    "Expense Request": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
        ]
    },
    "Payment Entry": {
        "validate": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
            "imogi_finance.transfer_application.payment_entry_hooks.validate_transfer_application_link",
        ],
        "before_submit": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
        ],
        "on_submit": [
            "imogi_finance.events.payment_entry.on_submit",
            "imogi_finance.receipt_control.payment_entry_hooks.record_payment_entry",
            "imogi_finance.transfer_application.payment_entry_hooks.on_submit",
        ],
        "on_cancel": [
            "imogi_finance.events.payment_entry.on_cancel",
            "imogi_finance.receipt_control.payment_entry_hooks.remove_payment_entry",
            "imogi_finance.transfer_application.payment_entry_hooks.on_cancel",
        ],
    },
    "Asset": {
        "on_submit": "imogi_finance.events.asset.on_submit",
        "on_cancel": "imogi_finance.events.asset.on_cancel",
    },
    "Bank Transaction": {
        "before_cancel": "imogi_finance.events.bank_transaction.before_cancel",
        "on_submit": "imogi_finance.transfer_application.matching.handle_bank_transaction",
        "on_update_after_submit": "imogi_finance.transfer_application.matching.handle_bank_transaction",
    },
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"imogi_finance.tasks.all"
# 	],
# 	"daily": [
# 		"imogi_finance.tasks.daily"
# 	],
# 	"hourly": [
# 		"imogi_finance.tasks.hourly"
# 	],
# 	"weekly": [
# 		"imogi_finance.tasks.weekly"
# 	],
# 	"monthly": [
# 		"imogi_finance.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "imogi_finance.install.before_tests"

after_migrate = "imogi_finance.utils.ensure_coretax_export_doctypes"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "imogi_finance.event.get_events"
# }
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



fixtures = [
    "Workspace",
    {
        "dt": "Custom Field",
        "filters": [["name", "in", [
            "Purchase Invoice-imogi_expense_request",
            "Purchase Invoice-imogi_request_type",
            "Purchase Invoice-imogi_pph_type",
            "Purchase Invoice-ti_tax_invoice_section",
            "Purchase Invoice-ti_tax_invoice_pdf",
            "Purchase Invoice-ti_ocr_status",
            "Purchase Invoice-ti_ocr_confidence",
            "Purchase Invoice-ti_ocr_raw_json",
            "Purchase Invoice-ti_tax_invoice_data_section",
            "Purchase Invoice-ti_fp_no",
            "Purchase Invoice-ti_fp_date",
            "Purchase Invoice-ti_fp_npwp",
            "Purchase Invoice-ti_fp_dpp",
            "Purchase Invoice-ti_fp_ppn",
            "Purchase Invoice-ti_fp_ppn_type",
            "Purchase Invoice-ti_verification_status",
            "Purchase Invoice-ti_verification_notes",
            "Purchase Invoice-ti_duplicate_flag",
            "Purchase Invoice-ti_npwp_match",
            "Payment Entry-transfer_application",
            "Payment Entry-imogi_expense_request",
            "Payment Entry-customer_receipt",
            "Bank Transaction-transfer_application",
            "Bank Transaction-match_confidence",
            "Bank Transaction-match_notes",
            "Asset-imogi_expense_request",
            "Expense Request-ti_tax_invoice_section",
            "Expense Request-ti_tax_invoice_pdf",
            "Expense Request-ti_ocr_status",
            "Expense Request-ti_ocr_confidence",
            "Expense Request-ti_ocr_raw_json",
            "Expense Request-ti_tax_invoice_data_section",
            "Expense Request-ti_fp_no",
            "Expense Request-ti_fp_date",
            "Expense Request-ti_fp_npwp",
            "Expense Request-ti_fp_dpp",
            "Expense Request-ti_fp_ppn",
            "Expense Request-ti_fp_ppn_type",
            "Expense Request-ti_verification_status",
            "Expense Request-ti_verification_notes",
            "Expense Request-ti_duplicate_flag",
            "Expense Request-ti_npwp_match",
            "Expense Request-budget_lock_status",
            "Expense Request-internal_charge_request",
            "Expense Request-allocation_mode",
            "Expense Request-prevent_pi_if_not_ready",
            "Purchase Invoice-internal_charge_request",
            "Sales Invoice-out_fp_section",
            "Sales Invoice-out_fp_pdf",
            "Sales Invoice-out_fp_ocr_status",
            "Sales Invoice-out_fp_ocr_confidence",
            "Sales Invoice-out_fp_ocr_raw_json",
            "Sales Invoice-out_fp_data_section",
            "Sales Invoice-out_fp_no",
            "Sales Invoice-out_fp_date",
            "Sales Invoice-out_buyer_tax_id",
            "Sales Invoice-out_fp_dpp",
            "Sales Invoice-out_fp_ppn",
            "Sales Invoice-out_fp_ppn_type",
            "Sales Invoice-out_fp_status",
            "Sales Invoice-out_fp_verification_notes",
            "Sales Invoice-out_fp_duplicate_flag",
            "Sales Invoice-out_fp_npwp_match",
        ]]],
    },
    {"dt": "Workspace", "filters": [["name", "=", "IMOGI FINANCE"]]},
    {
        "dt": "Workflow",
        "filters": [
            [
                "name",
                "in",
                [
                    "Expense Request Workflow",
                    "Administrative Payment Voucher Workflow",
                    "Transfer Application Workflow",
                    "Branch Expense Request Workflow",
                ],
            ]
        ],
    },
    {
        "dt": "Workflow State",
        "filters": [
            [
                "name",
                "in",
                [
                    "Draft",
                    "Reopened",
                    "Pending Level 1",
                    "Pending Level 2",
                    "Pending Level 3",
                    "Approved",
                    "Rejected",
                    "Linked",
                    "Closed",
                    "Pending Approval",
                    "Posted",
                    "Cancelled",
                    "Finance Review",
                    "Approved for Transfer",
                    "Awaiting Bank Confirmation",
                    "Paid",
                ],
            ]
        ],
    },
    {
        "dt": "Role",
        "filters": [
            [
                "name",
                "in",
                [
                    "Receipt Maker",
                    "Receipt Approver",
                    "Receipt Auditor",
                    "Tax Reviewer",
                ],
            ]
        ],
    },
]
