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
    "/assets/cannabis_management/js/payment_calendar.js",
    "/assets/cannabis_management/js/sidebar_nav.js",
    "/assets/cannabis_management/js/financial_statements_child_accounts_link.js",
    "/assets/cannabis_management/js/pnl_gl_export.js",
]


app_include_css = [
    "/assets/cannabis_management/css/payment_calendar.css"
]
# include js in doctype views
doctype_js = {
    # Cash Management forms
    "Cash Ledger Entry": "cash_management/doctype/cash_ledger_entry/cash_ledger_entry.js",
    "Expense Tracker Entry": "cash_management/doctype/expense_tracker_entry/expense_tracker_entry.js",
    # Existing
    "Stock Entry": "public/js/stock_entry.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Receipt": "public/js/purchase_receipt.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Delivery Note": "public/js/delivery_note.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Sales Order": "public/js/sales_order.js",
    "Material Request": "public/js/material_request.js",
    "Item Group": "public/js/item_group_custom.js",
    "Job Card": "public/js/job_card.js",
    "Quotation": "public/js/quotation.js",
}
doctype_list_js = {
    "Sales Invoice": "public/js/sales_invoice_list.js",
    "Sales Order": "public/js/sales_order_list.js",
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

# Migration hooks
# ---------------
# Installs backward-compat shims for Frappe API removed in ~v15.97 that
# Frappe CRM still imports.  Runs before after_migrate hooks fire.
before_migrate = ["cannabis_management.compat.install_frappe_shims"]

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
    "Customer":      "cannabis_management.permissions.customer_query_conditions",
    "Sales Invoice": "cannabis_management.permissions.sales_invoice_query_conditions",
    # CRM Lead permission (Tolling access) moved to crm.motley_terpz.permissions
    "Cash Ledger Entry":      "cannabis_management.cash_management.permissions.cash_ledger_entry_query",
    "Expense Tracker Entry":  "cannabis_management.cash_management.permissions.expense_tracker_entry_query",
    "Personal Cash Tracking": "cannabis_management.cash_management.permissions.personal_cash_tracking_query",
    "Motley Cash Tracking":   "cannabis_management.cash_management.permissions.motley_cash_tracking_query",
}

has_permission = {
    "Customer":      "cannabis_management.permissions.customer_has_permission",
    "Sales Invoice": "cannabis_management.permissions.sales_invoice_has_permission",
    "Personal Cash Tracking": "cannabis_management.cash_management.permissions.personal_cash_tracking_has_permission",
    "Motley Cash Tracking":   "cannabis_management.cash_management.permissions.motley_cash_tracking_has_permission",
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
    # ── Workstation Operating Cost validation ────────────────────────────────
    "Workstation": {
        "validate": "cannabis_management.cannabis_management.doctype.operating_component.operating_component.validate_workstation",
    },
    # -----------------------------------------------------------------------
    # Cash Management Module
    # -----------------------------------------------------------------------
    "Cash Ledger Entry": {
        "before_save": [
            "cannabis_management.cash_management.utils.cash_utils.auto_fill_month",
            "cannabis_management.cash_management.utils.cash_utils.auto_fill_employee",
        ],
        "on_submit": [
            "cannabis_management.cash_management.utils.cash_utils.update_running_balance",
            "cannabis_management.cash_management.utils.cash_utils.check_form_8300_trigger",
            "cannabis_management.cash_management.utils.cash_utils.update_cash_balance_ledger",
            "cannabis_management.cash_management.utils.cash_utils.publish_realtime_balance",
        ],
        "on_cancel": [
            "cannabis_management.cash_management.utils.cash_utils.update_cash_balance_ledger",
            "cannabis_management.cash_management.utils.cash_utils.publish_realtime_balance",
        ],
    },
    "Expense Tracker Entry": {
        "before_save": [
            "cannabis_management.cash_management.utils.cash_utils.auto_fill_month",
            "cannabis_management.cash_management.utils.cash_utils.auto_fill_employee",
        ],
        "on_submit": [
            "cannabis_management.cash_management.utils.cash_utils.update_expense_balance",
            "cannabis_management.cash_management.utils.cash_utils.publish_realtime_balance",
        ],
        "on_cancel": [
            "cannabis_management.cash_management.utils.cash_utils.update_expense_balance",
            "cannabis_management.cash_management.utils.cash_utils.publish_realtime_balance",
        ],
    },
    # Cash tracking capture forms — submittable; cancellation is restricted to
    # the Administrator / MBI (see cash_utils.restrict_cancel).
    "Motley Cash Tracking": {
        "before_cancel": "cannabis_management.cash_management.utils.cash_utils.restrict_cancel",
    },
    "Personal Cash Tracking": {
        "before_cancel": "cannabis_management.cash_management.utils.cash_utils.restrict_cancel",
    },
    # -----------------------------------------------------------------------
    # CRM account enhancements (sales-team feedback, July 2026)
    "CRM Lead": {
        "before_insert": "cannabis_management.api.crm_account_enhancements.check_lead_duplicate",
    },
    "CRM Organization": {
        "before_insert": "cannabis_management.api.crm_account_enhancements.check_organization_duplicate",
    },
    "CRM Deal": {
        "on_update": "cannabis_management.api.crm_account_enhancements.create_won_deal_followups",
    },
    # -----------------------------------------------------------------------
    # AR Policy disabled — before_submit cap check removed
    "Sales Invoice": {
        "before_validate": "cannabis_management.doc_hooks.sales_invoice.before_validate",
        "before_submit": "cannabis_management.doc_hooks.sales_invoice.before_submit",
        "on_submit": [
            "cannabis_management.doc_hooks.sales_invoice.on_submit",
        ],
    },
    # Quotation approval — discount-threshold routing (Sales Manager / Finance)
    "Quotation": {
        "validate": [
            "cannabis_management.overrides.quotation_approval.validate",
            "cannabis_management.overrides.license_compliance.check_license",
        ],
        "on_update":     "cannabis_management.overrides.quotation_approval.on_update",
        "before_submit": "cannabis_management.overrides.quotation_approval.before_submit",
    },
    # Lab mapping: auto-create BOMs on Material Request submit
    "Material Request": {
        "validate": "cannabis_management.doc_hooks.material_request.validate",
        "on_submit": "cannabis_management.doc_hooks.material_request.on_submit",
    },
    "Stock Entry": {
        "before_validate": "cannabis_management.cannabis_management.custom.stock_entry.before_validate",
        "validate": [
            "cannabis_management.cannabis_management.custom.stock_entry.validate",
            "cannabis_management.doc_hooks.stock_entry.sync_row_uom_with_item",
            "cannabis_management.doc_hooks.stock_entry.populate_micron_finished_goods",
            "cannabis_management.doc_hooks.stock_entry.set_operating_cost_accounts",
            # Metric Tag: mirror muid/to_muid on single-leg rows so either field works
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.normalize_stock_entry_tag_fields",
        ],
        # Metric Tag status/qty lifecycle sync — also covers the Stock Entries a Job Card generates
        "before_submit": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.validate_metric_tag_status",
        "on_submit": [
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
        ],
        "on_cancel": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
    },
    "Sales Order": {
        "before_validate": "cannabis_management.doc_hooks.sales_invoice.before_validate",
        "validate": [
            "cannabis_management.overrides.sales_order_restrictions.validate",
            "cannabis_management.overrides.license_compliance.check_license",
        ],
        "on_update": "cannabis_management.overrides.sales_order_restrictions.on_update",
        "before_submit": [
            "cannabis_management.overrides.sales_order_restrictions.before_submit",
        ],
        "on_submit": [
            "cannabis_management.overrides.sales_order_restrictions.on_submit",
            "cannabis_management.overrides.sales_invoice_hooks.check_inventory_and_notify_slack",
            # "cannabis_management.overrides.payment_overdue_alert.on_sales_invoice_submit"  # AR Policy disabled
        ],
    },
    "Delivery Note": {
        "before_submit": [
            # Metric Tag status lifecycle sync
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.validate_metric_tag_status",
        ],
        "on_update": [
            "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
            "cannabis_management.overrides.delivery_note_hooks.update_sales_order_delivery_status",
        ],
        "on_submit": [
            "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
            "cannabis_management.overrides.delivery_note_hooks.update_sales_order_delivery_status",
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
        ],
        "on_cancel": [
            "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
            "cannabis_management.overrides.delivery_note_hooks.update_sales_order_delivery_status",
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
        ],
        "validate": "cannabis_management.overrides.delivery_note_hooks.set_expense_head",
    },
    # Metric Tag status/qty lifecycle sync
    "Purchase Receipt": {
        "before_submit": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.validate_metric_tag_status",
        "on_submit": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
        "on_cancel": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
    },
    "Stock Reconciliation": {
        "before_submit": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.validate_metric_tag_status",
        "on_submit": [
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
        ],
        "on_cancel": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
    },
    "Timesheet": {
        "after_insert": "cannabis_management.overrides.timesheet_hooks.auto_submit_timesheet",
    },
    "Payment Entry": {
        "on_submit": "cannabis_management.cannabis_management.utils.irs_8300.check_cash_threshold"
    },
    "Job Card": {
        "validate": [
            "cannabis_management.doc_hooks.job_card.calculate_sub_op_costs",
            "cannabis_management.doc_hooks.job_card.validate",
        ],
        "on_submit": [
            "cannabis_management.doc_hooks.job_card.calculate_sub_op_costs",
            "cannabis_management.doc_hooks.job_card.validate",
        ],
    },
    "Conversion Entry": {
        "on_submit": [
            "cannabis_management.overrides.conversion_entry_hooks.notify_conversion_entry_slack",
        ],
    },
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    "cron": {
        # AR due-date reminders: every day at 7 AM UTC (daily, including weekends)
        "0 7 * * *": [
            "cannabis_management.api.ar_reminders.send_ar_reminders",
            # Daily overdue-invoice reminder to the owning rep (no blocking)
            "cannabis_management.api.overdue_owner_reminder.send_overdue_owner_reminders",
            # Daily unreconciled-customer count snapshot (day-over-day AR tracking)
            "cannabis_management.api.sales_daily_sync.snapshot_unreconciled",
        ],
        # Daily jobs: Mon–Fri only (midnight Berlin time)
        "0 0 * * 1-5": [
            "cannabis_management.api.crm_sync.sync_crm_ar_data",
            "cannabis_management.cannabis_management.utils.irs_8300.check_overdue_filings",
            "cannabis_management.cannabis_management.utils.irs_8300.send_january_notices",
            "cannabis_management.cash_management.utils.cash_utils.check_overdue_form_8300",
            # Payment Terms SO: remind creator 14 and 7 days before each payment due date
            "cannabis_management.overrides.payment_schedule_reminder.send_payment_schedule_reminders",
            # AR Policy disabled
            # "cannabis_management.api.ar_monitor.check_ar_cap",
            # "cannabis_management.api.ar_monitor.compute_dso",
        ],
        # SO delivery-date reminder: 10 AM Eastern (UTC-4 EDT → 14:00 UTC) — weekdays only
        "0 14 * * 1-5": [
            "cannabis_management.overrides.sales_order_delivery_reminder.send_delivery_date_reminders",
            # "cannabis_management.overrides.payment_overdue_alert.on_sales_invoice_submit",  # AR Policy disabled
        ],
        # Friday: payment overdue report at 9 AM PDT (14:00 UTC / 15:00 PST)
        "0 14 * * 5": [
            # "cannabis_management.overrides.payment_overdue_alert.friday_overdue_report",  # AR Policy disabled
            # "cannabis_management.api.ar_monitor.send_weekly_ar_report",  # AR Policy disabled
        ],
        # Weekly Sale Report: Friday 4 PM PDT (23:00 UTC)
        # "0 23 * * 5": [
        #     "cannabis_management.api.weekly_report.send_weekly_report",
        # ],
        # Weekly Sales Report: generate Monday 8 AM UTC
        "0 8 * * 1": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.generate_weekly_signoff",
            # "cannabis_management.api.nikki_ar_report.send_nikki_ar_report",  # AR Policy disabled
        ],
        # Weekly Sales Report: remind Tuesday 8 AM UTC if unacknowledged
        "0 8 * * 2": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.send_acknowledgment_reminder",
        ],
        # Daily Sale Report: Mon–Fri 01:00 Berlin (CEST=UTC+2) = Sun–Thu 23:00 UTC = Mon–Fri 04:00 PKT
        # Server is Europe/Berlin; cron uses server local time, not UTC
        "0 1 * * 1-5": [
            "cannabis_management.api.daily_report.send_daily_report",
        ],
        # DN Gap Report: 5 AM PDT every day (12:00 UTC / 3 AM Adak HDT)
        # Weekly AR Report: 5 AM PDT Friday only (12:00 UTC / 3 AM Adak HDT)
        "0 3 * * *": [
            "cannabis_management.api.dn_gap_report.send_dn_gap_report",
        ],
        "0 3 * * 5": [
            "cannabis_management.api.ar_report.send_ar_report",
        ],
    },
    "monthly": [
        # AR Policy disabled
        # "cannabis_management.api.ar_monitor.compute_cei",
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
override_whitelisted_methods = {
    # Always set party_type=Employee on Payment Entries created from Cash/Expense doctypes.
    "cannabis_management.cash_management.utils.cash_utils.create_payment_entry":
        "cannabis_management.api.cash_payment_override.create_payment_entry",
}
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
    # Cash Management DocTypes
    {"dt": "DocType", "filters": [["name", "=", "Cash Tracker Person"]]},
    {"dt": "DocType", "filters": [["name", "=", "Cash Balance Ledger"]]},
    {"dt": "DocType", "filters": [["name", "=", "Cash Account Mapping"]]},
    {"dt": "DocType", "filters": [["name", "=", "Cash Ledger Entry"]]},
    {"dt": "DocType", "filters": [["name", "=", "Expense Tracker Entry"]]},
    # ── Sales Daily Sync dashboard objects (travel via git) ──ench
    # Role that grants visibility into Nikki's cash/expense widgets
    # + Company Records module roles
    {"dt": "Role", "filters": [["name", "in", [
        "Nikki Ledger",
        "Accounting Team",
        "Operations",
        "ERP Dev Team",
        "Director",
        "Farm Manager",
    ]]]},
    # Company Records workflow actions (Workflow / Workflow State are already
    # exported unfiltered above)
    {"dt": "Workflow Action Master", "filters": [["name", "in", [
        "Submit for Review", "Approve", "Reject", "Lock",
        "Activate", "Mark Expired", "Terminate",
    ]]]},
    # Day-over-day unreconciled-AR snapshot storage
    {"dt": "DocType", "filters": [["name", "=", "AR Recon Snapshot"]]},
    # The combined Sales Target + Inventory + COD/AR/Unreconciled dashboard block
    {"dt": "Custom HTML Block", "filters": [["name", "in", [
        "Sales Daily Sync Dashboard Block",
        "Lab Daily Sync Dashboard Block",
        "Sales Target and Inventory Dashboard",  # ye bhi hai aapke paas
        "Distribution Hub",
        "Company Records Hub",
    ]]]},
    # Client-facing Extracts Live Menu page (JS: display-name aliases +
    # Tier group ordering). Git-managed so it deploys via bench update.
    {"dt": "Web Page", "filters": [["name", "=", "live-menu-2"]]},
]

