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
    "Customer": "cannabis_management.permissions.customer_query_conditions"
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

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    # Lab mapping: auto-create BOMs on Material Request submit
    "Material Request": {
        "on_submit": "cannabis_management.doc_hooks.material_request.on_submit",
    },
    "Stock Entry": {
        "validate": "cannabis_management.cannabis_management.custom.stock_entry.validate",
        # MTM: yield threshold check + batch auto-creation on Manufacture entries
        "before_submit": "cannabis_management.master_touch_manufacturing.overrides.stock_entry.before_submit",
        "on_submit": "cannabis_management.master_touch_manufacturing.overrides.stock_entry.on_submit",
    },
    "Sales Order": {
        "validate": "cannabis_management.overrides.sales_order_restrictions.validate",
        "on_update": "cannabis_management.overrides.sales_order_restrictions.on_update",
        "before_submit": "cannabis_management.overrides.sales_order_restrictions.before_submit",
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
    # MTM: Work Order status changes → update Production Batch Group status
    "Work Order": {
        "on_update": "cannabis_management.master_touch_manufacturing.overrides.work_order.on_update",
        "on_update_after_submit": "cannabis_management.master_touch_manufacturing.overrides.work_order.on_update",
    },
    # MTM: Job Card completion → clock-out, notify Slack
    "Job Card": {
        "validate": [
            "cannabis_management.doc_hooks.job_card.validate",
        ],
        "on_submit": [
            "cannabis_management.doc_hooks.job_card.validate",
            "cannabis_management.master_touch_manufacturing.overrides.job_card.on_submit",
        ],
    },
    # MTM: Purchase Receipt — weight variance, FF batch creation, retag alerts
    "Purchase Receipt": {
        "on_submit": "cannabis_management.master_touch_manufacturing.overrides.purchase_receipt.on_submit",
    },
    # MTM: Wash Batch submit → auto-create Bubble Hash ERPNext Batches per detail row
    "Wash Batch": {
        "on_submit": "cannabis_management.master_touch_manufacturing.overrides.wash_batch.on_submit",
    },
    # MTM: Press Batch submit → auto-create Rosin ERPNext Batches per detail row
    "Press Batch": {
        "on_submit": "cannabis_management.master_touch_manufacturing.overrides.press_batch.on_submit",
    },
    # MTM: Inventory Verification approval → release batches + auto-create QI
    "Inventory Verification": {
        "on_update": "cannabis_management.master_touch_manufacturing.overrides.inventory_verification.on_update",
    },
    # MTM: Purchase Order → inter-company Sales Order in supplier's company
    "Purchase Order": {
        "on_submit": "cannabis_management.master_touch_manufacturing.overrides.purchase_order.on_submit",
    },
    # MTM: Production Batch Group — sequence lock + toll invoice on close
    "Production Batch Group": {
        "before_insert": "cannabis_management.master_touch_manufacturing.overrides.production_batch_group.on_before_insert",
        "on_update": "cannabis_management.master_touch_manufacturing.overrides.production_batch_group.on_update",
    },
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    "daily": [
        "cannabis_management.cannabis_management.utils.irs_8300.check_overdue_filings",
        "cannabis_management.cannabis_management.utils.irs_8300.send_january_notices",
        # MTM: stale batch alerts
        "cannabis_management.master_touch_manufacturing.tasks.daily",
        # Payment Terms SO: remind creator 14 and 7 days before each payment due date
        "cannabis_management.overrides.payment_schedule_reminder.send_payment_schedule_reminders",
    ],
    # Sales Order delivery-date reminder fires at 10:00 AM Eastern (EDT = UTC-4 → 14:00 UTC).
    # Note: during EST (Nov–Mar, UTC-5) this fires at 9:00 AM Eastern.
    "cron": {
        "0 14 * * *": [
            "cannabis_management.overrides.sales_order_delivery_reminder.send_delivery_date_reminders",
        ],
        # Payment overdue check: Mon–Fri at 9 AM EST (UTC-4 EDT → 13:00 UTC; UTC-5 EST → 14:00 UTC)
        "0 14 * * *": [
            "cannabis_management.overrides.sales_order_delivery_reminder.send_delivery_date_reminders",
        ],
        "0 14 * * 5": [
            "cannabis_management.overrides.payment_overdue_alert.friday_overdue_report",
        ],
        # Weekly Sales Report: generate Monday 8 AM UTC, remind Tuesday 8 AM UTC if unacknowledged
        "0 8 * * 1": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.generate_weekly_signoff",
        ],
        "0 8 * * 2": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.send_acknowledgment_reminder",
        ],
    },
    "weekly": [
        # MTM: weekly production summary to Slack
        "cannabis_management.master_touch_manufacturing.tasks.weekly",
    ],
    "monthly": [
        # MTM: monthly yield + cost report
        "cannabis_management.master_touch_manufacturing.tasks.monthly",
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
# override_doctype_dashboards = {
# 	"Task": "cannabis_management.task.get_dashboard_data"
# }

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
    # MTM module — export all module-specific records so they survive reinstall
    {"dt": "DocType", "filters": [["module", "=", "Master Touch Manufacturing"]]},
    {"dt": "DocType", "filters": [["name", "=", "Weekly Sales Report"]]},
    {"dt": "Role", "filters": [["name", "in", [
        "Lab Tech", "Lab Supervisor", "Production Manager",
        "Distro Manager", "Compliance Officer"
    ]]]},
    {"dt": "Workstation", "filters": [["name", "like", "WS%"]]},
    {"dt": "Operation", "filters": [["workstation", "like", "WS%"]]},
    {"dt": "Workspace", "filters": [["module", "=", "Master Touch Manufacturing"]]},
    {"dt": "Quality Inspection Template", "filters": [["quality_inspection_template_name", "in", [
        "Bubble Hash QI", "Rosin QI"
    ]]]},
]

