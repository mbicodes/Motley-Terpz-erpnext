app_name = "cannabis_management"
app_title = "Cannabis Management"
app_publisher = "alltechvirtual.com"
app_description = "Comprehensive ERPNext module for cannabis cultivation, inventory, compliance, and seed-to-sale management."
app_email = "mbi@alltechvirtual.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "cannabis_management",
# 		"logo": "/assets/cannabis_management/logo.png",
# 		"title": "Cannabis Management",
# 		"route": "/cannabis_management",
# 		"has_permission": "cannabis_management.api.permission.has_app_permission"
# 	}
# ]

csrf_exempt = [
    "/api/method/cannabis_management.api.slack_inventory.handle_inventory_command"
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/cannabis_management/css/cannabis_management.css"

# include js, css files in header of web template
# web_include_css = "/assets/cannabis_management/css/cannabis_management.css"
# web_include_js = "/assets/cannabis_management/js/cannabis_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cannabis_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}
app_include_js = [
    "/assets/cannabis_management/js/stock_balance_custom.js",
    "/assets/cannabis_management/js/payment_calendar.js"
]


app_include_css = [
    "/assets/cannabis_management/css/payment_calendar.css"
]
# include js in doctype views
doctype_js = {
    "Stock Entry": "public/js/stock_entry.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Receipt": "public/js/purchase_receipt.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Delivery Note": "public/js/delivery_note.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Sales Order": "public/js/sales_order.js",
    "Material Request": "public/js/material_request.js",
    "Item Group": "public/js/item_group_custom.js"
}

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "cannabis_management/public/icons.svg"

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
# jinja = {
# 	"methods": "cannabis_management.cannabis_management.utils.jinja_methods",
# 	"filters": "cannabis_management.cannabis_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "cannabis_management.install.before_install"
# after_install = "cannabis_management.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "cannabis_management.uninstall.before_uninstall"
# after_uninstall = "cannabis_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cannabis_management.cannabis_management.utils.before_app_install"
# after_app_install = "cannabis_management.cannabis_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cannabis_management.cannabis_management.utils.before_app_uninstall"
# after_app_uninstall = "cannabis_management.cannabis_management.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cannabis_management.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
    "Customer": "cannabis_management.permissions.customer_query_conditions",
    "CRM Lead": "cannabis_management.overrides.crm_enforcement.crm_lead_query_conditions",
}

has_permission = {
    "Customer": "cannabis_management.permissions.customer_has_permission"
}


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
    # Item Group → Account mapping: substitute warehouse inventory accounts
    # in GL entries based on the item's group. Falls back to warehouse default.
    "Stock Entry":          "cannabis_management.overrides.stock_entry_gl.CMStockEntry",
    "Purchase Receipt":     "cannabis_management.overrides.purchase_receipt_gl.CMPurchaseReceipt",
    "Delivery Note":        "cannabis_management.overrides.delivery_note_gl.CMDeliveryNote",
    "Stock Reconciliation": "cannabis_management.overrides.stock_reconciliation_gl.CMStockReconciliation",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    # AR Policy: cap check + overdue warning + blocked customer check on submit
    "Sales Invoice": {
        "before_submit": [
            "cannabis_management.doc_hooks.sales_invoice.before_submit",
            "cannabis_management.overrides.crm_enforcement.check_customer_blocked",
            "cannabis_management.overrides.crm_enforcement.check_cod_customer",
        ],
    },
    # Lab mapping: auto-create BOMs on Material Request submit
    "Material Request": {
        "on_submit": "cannabis_management.doc_hooks.material_request.on_submit",
    },
    "Stock Entry": {
        "validate": "cannabis_management.cannabis_management.custom.stock_entry.validate",
    },
    "Sales Order": {
        "validate": "cannabis_management.overrides.sales_order_restrictions.validate",
        "on_update": "cannabis_management.overrides.sales_order_restrictions.on_update",
        "before_submit": [
            "cannabis_management.overrides.sales_order_restrictions.before_submit",
            "cannabis_management.overrides.crm_enforcement.check_customer_blocked",
        ],
        "on_submit": [
            "cannabis_management.overrides.sales_order_restrictions.on_submit",
            "cannabis_management.overrides.sales_invoice_hooks.check_inventory_and_notify_slack",
            "cannabis_management.overrides.payment_overdue_alert.on_sales_invoice_submit"
        ],
    },
    "Delivery Note": {
        "on_update": "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
        "on_submit": "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
        "on_cancel": "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status"
    },
    "Timesheet": {
        "after_insert": "cannabis_management.overrides.timesheet_hooks.auto_submit_timesheet",
    },
    "Payment Entry": {
        "on_submit": "cannabis_management.cannabis_management.utils.irs_8300.check_cash_threshold"
    },
    "Job Card": {
        "validate": [
            "cannabis_management.doc_hooks.job_card.validate",
        ],
        "on_submit": [
            "cannabis_management.doc_hooks.job_card.validate",
        ],
    },
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    "daily": [
        "cannabis_management.api.crm_sync.sync_crm_ar_data",
        "cannabis_management.cannabis_management.utils.irs_8300.check_overdue_filings",
        "cannabis_management.cannabis_management.utils.irs_8300.send_january_notices",
        # Payment Terms SO: remind creator 14 and 7 days before each payment due date
        "cannabis_management.overrides.payment_schedule_reminder.send_payment_schedule_reminders",
        # AR Policy: total AR cap check + DSO from GL ledger
        "cannabis_management.api.ar_monitor.check_ar_cap",
        "cannabis_management.api.ar_monitor.compute_dso",
    ],
    "cron": {
        # SO delivery-date reminder: 10 AM Eastern (UTC-4 EDT → 14:00 UTC; UTC-5 EST → 15:00 UTC)
        "0 14 * * *": [
            "cannabis_management.overrides.sales_order_delivery_reminder.send_delivery_date_reminders",
            "cannabis_management.overrides.payment_overdue_alert.on_sales_invoice_submit",
        ],
        # Friday: payment overdue report at 9 AM PDT (14:00 UTC / 15:00 PST)
        "0 14 * * 5": [
            "cannabis_management.overrides.payment_overdue_alert.friday_overdue_report",
            # AR Policy: weekly AR report every Friday 8 AM UTC
            "cannabis_management.api.ar_monitor.send_weekly_ar_report",
            "cannabis_management.api.weekly_report.send_weekly_report",
        ],
        # Weekly Sales Report: generate Monday 8 AM UTC
        "0 8 * * 1": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.generate_weekly_signoff",
            "cannabis_management.api.nikki_ar_report.send_nikki_ar_report",
        ],
        # Weekly Sales Report: remind Tuesday 8 AM UTC if unacknowledged
        "0 8 * * 2": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.send_acknowledgment_reminder",
        ],
        # Daily Sale Report: Sun–Thu at 23:00 UTC → delivered Mon–Fri at 04:00 PKT
        # PKT is UTC+5 year-round (no DST in Pakistan)
        "0 23 * * 0-4": [
            "cannabis_management.api.daily_report.send_daily_report",
        ],
    },
    "monthly": [
        # AR Policy: CEI calculation from GL ledger
        "cannabis_management.api.ar_monitor.compute_cei",
    ],
}
# scheduler_events = {
# 	"all": [
# 		"cannabis_management.tasks.all"
# 	],
# 	"daily": [
# 		"cannabis_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"cannabis_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cannabis_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cannabis_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "cannabis_management.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "cannabis_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
	"Sales Order": "cannabis_management.overrides.sales_order_dashboard.get_data"
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cannabis_management.cannabis_management.utils.before_request"]
# after_request = ["cannabis_management.cannabis_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["cannabis_management.cannabis_management.utils.before_job"]
# after_job = ["cannabis_management.cannabis_management.utils.after_job"]

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
# 	"cannabis_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
fixtures = [
    "Custom Field",
    "Client Script",
    "Server Script",
    "Property Setter",
    "Workflow",
    "Workflow State",
    "Workflow Action",
    # Item Group Account Mapping child doctype
    {"dt": "DocType", "filters": [["name", "=", "Warehouse Item Group Account Mapping"]]},
    {"dt": "DocType", "filters": [["name", "=", "Weekly Sales Report"]]},
]

