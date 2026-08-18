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
    # Shared METRC form helpers — must load before the per-doctype scripts
    "/assets/cannabis_management/js/metrc_indicator.js",
    # Shared "Company" report filter carrying an All Company option — must load
    # before any report script that calls cannabis.reports.company_filter().
    "/assets/cannabis_management/js/company_filter.js",
    # Manufacturing Process Desk page logic (Work Order/BOM/Job Card trail).
    # Must load before the Desk page's thin shell. The portal at
    # /manufacturing-process is a separate, lighter Time Clock view now —
    # see www/manufacturing-process.html — and does not use this file.
    "/assets/cannabis_management/js/manufacturing_process_app.js",
]


app_include_css = [
    "/assets/cannabis_management/css/payment_calendar.css"
]
# include js in doctype views
doctype_js = {
    # Cash Management forms
    "Cash Ledger Entry": "cash_management/doctype/cash_ledger_entry/cash_ledger_entry.js",
    "Expense Tracker Entry": "cash_management/doctype/expense_tracker_entry/expense_tracker_entry.js",
    # Existing — METRC form UX is appended as a second file per doctype rather
    # than merged into these, so the integration stays removable in one place.
    "Stock Entry": ["public/js/stock_entry.js", "public/js/metrc/stock_entry_metrc.js"],
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Receipt": "public/js/purchase_receipt.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Delivery Note": ["public/js/delivery_note.js", "public/js/metrc/delivery_note_metrc.js"],
    "Sales Invoice": ["public/js/sales_invoice.js", "public/js/metrc/sales_invoice_metrc.js"],
    "Sales Order": ["public/js/sales_order.js", "public/js/credit_and_ar/sales_order_credit.js"],
    "Payment Entry": "public/js/credit_and_ar/payment_entry_credit.js",
    "Customer": "public/js/credit_and_ar/customer_credit.js",
    "Material Request": "public/js/material_request.js",
    "Item Group": "public/js/item_group_custom.js",
    "Job Card": "public/js/job_card.js",
    "Quotation": "public/js/quotation.js",
    # METRC only
    "Stock Reconciliation": "public/js/metrc/stock_reconciliation_metrc.js",
    "Work Order": "public/js/metrc/work_order_metrc.js",
    "Batch": ["public/js/metrc/batch_metrc.js", "public/js/farm/batch_farm.js"],
}
doctype_list_js = {
    "Sales Invoice": "public/js/sales_invoice_list.js",
    "Sales Order": "public/js/sales_order_list.js",
    # Farm bulk actions (Destroy / Record Waste) on the Metric Tag list
    "Metric Tag": "public/js/farm/metric_tag_list.js",
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

# frappe.model.sync re-imports standard workspace fixtures on every migrate, so
# the workspaces we removed from the sidebar have to be dropped again afterwards.
after_migrate = [
    "cannabis_management.workspace_cleanup.remove_unwanted_workspaces",
    # Manufacturing Portal code fields on User. Re-asserted every migrate rather than
    # run once as a patch: create_custom_fields is idempotent, and patches.txt is
    # root-owned on this bench so it cannot be appended to as the bench user.
    "cannabis_management.manufacturing_portal.custom_fields.install",
]

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
    # ── Manufacturing Portal access code: uniqueness + strength ──────────────
    "User": {
        "validate": "cannabis_management.manufacturing_portal.user_hooks.validate",
    },

    # ── Workstation Operating Cost validation ────────────────────────────────
    "Workstation": {
        "validate": "cannabis_management.cannabis_management.doctype.operating_component.operating_component.validate_workstation",
    },

    # ── Farm / Cultivation: Dynamic Link target + 48h immature-count lock ─────
    "Batch": {
        "validate": "cannabis_management.farm.batch_validate",
    },

    "Credit Application": {
        "before_insert": "cannabis_management.credit_and_ar.web_form_intake.before_insert",
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
        # Legacy / New Book / Plan classification, written as the invoice is saved
        "validate": "cannabis_management.credit_and_ar.payment_entry_hooks.stamp_invoice_ledger",
        "before_submit": "cannabis_management.doc_hooks.sales_invoice.before_submit",
        "on_submit": [
            "cannabis_management.doc_hooks.sales_invoice.on_submit",
            # §7 limit breach → immediate hold
            "cannabis_management.credit_and_ar.hold_engine.on_sales_invoice_submit",
            # METRC: queue a sales receipt (transactional outbox, never a live call)
            "cannabis_management.metrc.push.sales.on_submit",
        ],
        "on_cancel": "cannabis_management.metrc.push.sales.on_cancel",
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
        # METRC push is appended to on_submit below, after the Metric Tag sync.
        "validate": [
            "cannabis_management.cannabis_management.custom.stock_entry.validate",
            "cannabis_management.doc_hooks.stock_entry.sync_row_uom_with_item",
            "cannabis_management.doc_hooks.stock_entry.populate_micron_finished_goods",
            "cannabis_management.doc_hooks.stock_entry.set_operating_cost_accounts",
            # Metric Tag: mirror muid/to_muid on single-leg rows so either field works
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.normalize_stock_entry_tag_fields",
        ],
        # Metric Tag status/qty lifecycle sync — also covers the Stock Entries a Job Card generates
        "before_submit": [
            # Gate 1: production transfers and manufacture only, per §7.
            "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.validate_metric_tag_status",
        ],
        "on_submit": [
            "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
            # METRC: report outbound consumption/waste as a package adjustment.
            # Runs after the tag sync so Metric Tag quantities are current.
            "cannabis_management.metrc.push.packages.on_stock_entry_submit",
        ],
        "on_cancel": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
    },
    "Sales Order": {
        "before_validate": "cannabis_management.doc_hooks.sales_invoice.before_validate",
        "validate": [
            # Credit & AR gate — COD / Terms / Sample routing. Supersedes
            # overrides.sales_order_restrictions.validate, which set the approval
            # status from a hard-coded rule and is no longer wired.
            "cannabis_management.credit_and_ar.sales_order_hooks.validate",
            "cannabis_management.overrides.license_compliance.check_license",
        ],
        "on_update": "cannabis_management.credit_and_ar.sales_order_hooks.on_update",
        "before_submit": [
            "cannabis_management.credit_and_ar.sales_order_hooks.before_submit",
            # Gate 1: a hard or immediate hold stops the order dead.
            "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
        ],
        "on_submit": [
            "cannabis_management.overrides.sales_order_restrictions.on_submit",
            "cannabis_management.overrides.sales_invoice_hooks.check_inventory_and_notify_slack",
            # "cannabis_management.overrides.payment_overdue_alert.on_sales_invoice_submit"  # AR Policy disabled
        ],
    },
    "Delivery Note": {
        "before_submit": [
            # Gate 1: no product moves for a held customer.
            "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
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
            # METRC: queue an outgoing transfer template for dispatch
            "cannabis_management.metrc.push.transfers.on_submit",
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
            # METRC: a reconciliation is a package adjustment (signed delta)
            "cannabis_management.metrc.push.packages.on_stock_reconciliation_submit",
        ],
        "on_cancel": "cannabis_management.cannabis_management.doctype.metric_tag.metric_tag.sync_metric_tags",
    },
    # -----------------------------------------------------------------------
    # METRC — manufacturing / processing jobs
    "Work Order": {
        # Gate 1: no production starts for a held customer's order.
        "before_submit": "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
        "on_submit": "cannabis_management.metrc.push.processing.on_work_order_submit",
    },
    "Manufacture Stock Entry": {
        "on_submit": "cannabis_management.metrc.push.processing.on_manufacture_stock_entry_submit",
    },
    # METRC — drop cached UOM maps / enumerations when settings change
    "Metrc Settings": {
        "on_update": "cannabis_management.metrc.maintenance.clear_caches",
    },
    "Timesheet": {
        "after_insert": "cannabis_management.overrides.timesheet_hooks.auto_submit_timesheet",
    },
    "Customer": {
        # Credit & AR policy exemption: keep the displayed state honest when the
        # flag is toggled. The engines read the flag live, so nothing migrates.
        "validate": "cannabis_management.credit_and_ar.customer_hooks.validate",
        "on_update": "cannabis_management.credit_and_ar.customer_hooks.on_update",
    },
    # ── Home stays current on its own ───────────────────────────────────────
    # Nobody should have to remember to reseed Home. These keep its tiles in
    # step as work is created, renamed, disabled or deleted. All of them no-op
    # during migrate/install/import, where the installer reseeds anyway.
    "Workspace": {
        # Un-ticking "Is Hidden" surfaces the workspace on Home; re-ticking it
        # takes the tile away again.
        "on_update": "cannabis_management.home_hub_block.on_workspace_update",
        "on_trash": "cannabis_management.home_hub_block.on_trash",
    },
    "Report": {
        "after_insert": "cannabis_management.home_hub_block.on_report_change",
        # on_update also covers the Disabled flag being toggled.
        "on_update": "cannabis_management.home_hub_block.on_report_change",
        "on_trash": "cannabis_management.home_hub_block.on_trash",
        "after_rename": "cannabis_management.home_hub_block.after_rename",
    },
    "Page": {
        "after_insert": "cannabis_management.home_hub_block.on_page_change",
        "on_trash": "cannabis_management.home_hub_block.on_trash",
        "after_rename": "cannabis_management.home_hub_block.after_rename",
    },
    "Payment Entry": {
        # Two ledgers, never netted — plan money cannot pay the new book.
        "validate": "cannabis_management.credit_and_ar.payment_entry_hooks.validate",
        "on_submit": [
            "cannabis_management.cannabis_management.utils.irs_8300.check_cash_threshold",
            "cannabis_management.credit_and_ar.payment_entry_hooks.on_submit",
        ],
        # A cancellation flagged as a returned payment raises an immediate hold.
        # An ordinary correction does not.
        "on_cancel": [
            "cannabis_management.credit_and_ar.hold_engine.on_payment_entry_cancel",
            "cannabis_management.credit_and_ar.payment_entry_hooks.on_cancel",
        ],
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
            # ── Credit & AR Control ──────────────────────────────────────────
            # Every day including weekends: past due accrues at the weekend too,
            # and a hold that waits until Monday is not a stop-work order.
            # All of these no-op until Credit Policy Settings.policy_effective_date
            # is set. Order matters — metrics read the state the engines set.
            "cannabis_management.credit_and_ar.hold_engine.evaluate_customer_credit_status",
            "cannabis_management.credit_and_ar.hold_engine.check_broken_promises",
            "cannabis_management.credit_and_ar.hold_engine.check_license_expiry",
            # Plans and workouts run independently of the past-due engine:
            # one missed installment holds everything, and a workout balance
            # that stops shrinking ends the workout.
            "cannabis_management.credit_and_ar.plan_workout.check_plan_installments",
            "cannabis_management.credit_and_ar.plan_workout.review_workouts",
            # Metrics and scoring last: they read the state set above.
            "cannabis_management.credit_and_ar.metrics.evaluate_company_metrics",
            "cannabis_management.credit_and_ar.scoring.update_customer_payment_scores",
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
        # Credit & AR: Friday report to MD and CEO, 08:00 UTC
        "0 8 * * 5": [
            "cannabis_management.credit_and_ar.weekly_report.send_weekly_report",
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
        # Credit & AR: finance charges on the 1st of each month, 06:00 UTC.
        # Left in Draft unless auto_submit_finance_charges is on.
        "0 6 1 * *": [
            "cannabis_management.credit_and_ar.finance_charge.apply_finance_charges",
        ],
        # Weekly Sales Report: generate Monday 8 AM UTC
        "0 8 * * 1": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.generate_weekly_signoff",
            # "cannabis_management.api.nikki_ar_report.send_nikki_ar_report",  # AR Policy disabled
        ],
        # Weekly Sales Report: remind Tuesday 8 AM UTC if unacknowledged
        "0 8 * * 2": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.send_acknowledgment_reminder",
        ],
        # -------------------------------------------------------------------
        # METRC integration
        # Cadence balances the per-facility rate limit against compliance
        # freshness. Metrc does not require real-time reporting, but a
        # same-day discrepancy is far cheaper to resolve than a week-old one.
        # -------------------------------------------------------------------
        # Master data (items, strains, facilities, tag pool, enumerations): hourly
        "15 * * * *": [
            "cannabis_management.metrc.pull.sync_master_data",
        ],
        # Inventory (packages, transfers): every 30 minutes
        "*/30 * * * *": [
            "cannabis_management.metrc.pull.sync_inventory",
        ],
        # Outbox worker: every 5 minutes
        "*/5 * * * *": [
            "cannabis_management.metrc.push.outbox.process_outbox",
        ],
        # Operations (sales receipts, lab tests): 02:00
        "0 2 * * *": [
            "cannabis_management.metrc.pull.sync_operations",
        ],
        # Daily master creation: new METRC Items and Tags become ERPNext records.
        # Kept out of the hourly job so the review queue arrives as one batch.
        "30 3 * * *": [
            "cannabis_management.metrc.pull.sync_new_masters",
        ],
        # Variance report + stalled-cursor / parked-write alerts: 06:00
        "0 6 * * *": [
            "cannabis_management.metrc.reconcile.send_daily_variance_report",
            "cannabis_management.metrc.pull.alert_on_stalled_syncs",
        ],
        # Log pruning: Sunday 03:00
        "0 3 * * 0": [
            "cannabis_management.metrc.maintenance.prune_logs",
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

    # Credit & AR: an unapproved Terms Sales Order must not print. Client-side
    # menu hiding is cosmetic — these are the routes that actually render a
    # document, so the block is enforced here. Everything else passes through
    # to the original implementation untouched.
    "frappe.www.printview.get_html_and_style":
        "cannabis_management.credit_and_ar.print_guard.get_html_and_style",
    "frappe.utils.print_format.download_pdf":
        "cannabis_management.credit_and_ar.print_guard.download_pdf",
    "frappe.utils.weasyprint.download_pdf":
        "cannabis_management.credit_and_ar.print_guard.weasyprint_download_pdf",
    "frappe.core.doctype.communication.email.make":
        "cannabis_management.credit_and_ar.print_guard.make",

    # Frappe filters DocType/Page/Report workspace shortcuts but returns True
    # unconditionally for Dashboard and URL — and a workspace can only be linked
    # as a URL. Without this, every user sees every workspace and dashboard tile
    # on a shared landing page regardless of access.
    "frappe.desk.desktop.get_desktop_page":
        "cannabis_management.api.workspace_guard.get_desktop_page",
    # Home groups its tiles under per-type headings. Headings are not
    # permission-filtered, so an empty section is pruned per user here.
    "frappe.desk.desktop.get_workspace_sidebar_items":
        "cannabis_management.api.workspace_guard.get_workspace_sidebar_items",

    # "All Company" is a UI sentinel, not a real Company. Strip it before the
    # report runs so each report's existing `if filters.get("company")` branch
    # means "every company". Covers on-screen runs and exports alike.
    "frappe.desk.query_report.run":
        "cannabis_management.api.report_filters.run",
    "frappe.desk.query_report.export_query":
        "cannabis_management.api.report_filters.export_query",
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
# Confines a session opened with a Manufacturing Portal code to /manufacturing-process.
# No-ops for every normally authenticated session, so the cost on ordinary requests is
# one dict lookup.
before_request = ["cannabis_management.manufacturing_portal.session_guard.guard"]
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
        # Credit & AR Control
        "Credit Finance",
        "Managing Director",
        "Ops Manager",
        "Collections Officer",
    ]]]},
    # Credit & AR: the payment-terms ladder. Only the module's own templates
    # travel — the site's PAYMENT SCHEDULE BREAKDOWN template is left alone.
    {"dt": "Payment Terms Template", "filters": [["name", "in", [
        "COD",
        "NET7",
        "NET15",
        "NET21",
        "NET30",
        "50% down NET7",
        "50% down NET15",
        "50% down NET21",
        "50% down NET30",
    ]]]},
    # Company Records workflow actions (Workflow / Workflow State are already
    # exported unfiltered above)
    {"dt": "Workflow Action Master", "filters": [["name", "in", [
        "Submit for Review", "Approve", "Reject", "Lock",
        "Activate", "Mark Expired", "Terminate",
        # Credit Application Approval
        "Recommend", "Revoke",
    ]]]},
    # Day-over-day unreconciled-AR snapshot storage
    {"dt": "DocType", "filters": [["name", "=", "AR Recon Snapshot"]]},
    # The combined Sales Target + Inventory + COD/AR/Unreconciled dashboard block
    {"dt": "Custom HTML Block", "filters": [["name", "in", [
        "Home Hub",
        "Sales Daily Sync Dashboard Block",
        "Lab Daily Sync Dashboard Block",
        "Sales Target and Inventory Dashboard",  # ye bhi hai aapke paas
        "Distribution Hub",
        "Company Records Hub",
    ]]]},
    # Client-facing Extracts Live Menu page (JS: display-name aliases +
    # Tier group ordering). Git-managed so it deploys via bench update.
    {"dt": "Web Page", "filters": [["name", "=", "live-menu-2"]]},
    # Credit & AR: dashboard cards and the §17 in-desk alerts
    {"dt": "Number Card", "filters": [["name", "like", "Credit \u2014 %"]]},
    {"dt": "Notification", "filters": [["module", "=", "Credit and AR"]]},
    # The Home landing workspace
    {"dt": "Workspace", "filters": [["name", "=", "Home"]]},
]

