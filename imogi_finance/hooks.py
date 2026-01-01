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
doctype_js = {"Bank Transaction": "public/js/bank_transaction.js"}
doctype_list_js = {
    "BCA Bank Statement Import": "imogi_finance/doctype/bca_bank_statement_import/bca_bank_statement_import_list.js",
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

# before_install = "imogi_finance.install.before_install"
# after_install = "imogi_finance.install.after_install"

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
        "on_submit": "imogi_finance.events.purchase_invoice.on_submit",
        "on_cancel": "imogi_finance.events.purchase_invoice.on_cancel",
    },
    "Payment Entry": {
        "validate": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
        ],
        "before_submit": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
        ],
        "on_submit": [
            "imogi_finance.events.payment_entry.on_submit",
            "imogi_finance.receipt_control.payment_entry_hooks.record_payment_entry",
        ],
        "on_cancel": [
            "imogi_finance.events.payment_entry.on_cancel",
            "imogi_finance.receipt_control.payment_entry_hooks.remove_payment_entry",
        ],
    },
    "Asset": {
        "on_submit": "imogi_finance.events.asset.on_submit",
        "on_cancel": "imogi_finance.events.asset.on_cancel",
    },
    "Bank Transaction": {"before_cancel": "imogi_finance.events.bank_transaction.before_cancel"},
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
            "Payment Entry-imogi_expense_request",
            "Payment Entry-customer_receipt",
            "Asset-imogi_expense_request",
        ]]],
    },
    {"dt": "Workspace", "filters": [["name", "=", "IMOGI FINANCE"]]},
    {"dt": "Workflow", "filters": [["name", "=", "Expense Request Workflow"]]},
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
                ],
            ]
        ],
    },
]
