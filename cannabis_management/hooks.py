app_name = "cannabis_management"
app_title = "Cannabis Management"
app_publisher = "alltechvirtual.com"
app_description = "Comprehensive ERPNext module for cannabis cultivation, inventory, compliance, and seed-to-sale management."
app_email = "mbi@alltechvirtual.com"
app_license = "mit"

csrf_exempt = [
    "/api/method/cannabis_management.api.slack_inventory.handle_inventory_command"
]

web_include_js = ["/assets/cannabis_management/js/login_location.js?v=5"]

app_include_js = [
    "/assets/cannabis_management/js/stock_balance_custom.js",
    "/assets/cannabis_management/js/payment_calendar.js",
    "/assets/cannabis_management/js/sidebar_nav.js",
    "/assets/cannabis_management/js/financial_statements_child_accounts_link.js",
    "/assets/cannabis_management/js/pnl_gl_export.js",
    "/assets/cannabis_management/js/company_filter.js",
    "/assets/cannabis_management/js/cash_tracking_actions.js",
    "/assets/cannabis_management/js/data_export_presets.js?v=1",
    "/assets/cannabis_management/js/connection_tool_menu.js?v=1",
    "/assets/cannabis_management/js/login_location.js?v=5",
    "/assets/cannabis_management/js/idle_logout.js?v=1",
    "/assets/cannabis_management/js/about_branding.js?v=2",
]

app_include_css = [
    "/assets/cannabis_management/css/payment_calendar.css"
]
doctype_js = {
    "Cash Ledger Entry": "cash_management/doctype/cash_ledger_entry/cash_ledger_entry.js",
    "Expense Tracker Entry": "cash_management/doctype/expense_tracker_entry/expense_tracker_entry.js",
    "Stock Entry": "public/js/stock_entry.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Receipt": "public/js/purchase_receipt.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Delivery Note": "public/js/delivery_note.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Sales Order": ["public/js/sales_order.js", "public/js/credit_and_ar/sales_order_credit.js"],
    "Payment Entry": [
        "public/js/credit_and_ar/payment_entry_credit.js",
        "public/js/cash_tracking_post.js",
    ],
    "Journal Entry": "public/js/cash_tracking_post.js",
    "Customer": "public/js/credit_and_ar/customer_credit.js",
    "Material Request": "public/js/material_request.js",
    "Item Group": "public/js/item_group_custom.js",
    "Job Card": "public/js/job_card.js",
    "Quotation": "public/js/quotation.js",
    "Warehouse": "public/js/warehouse.js",
}
doctype_list_js = {
    "Sales Invoice": "public/js/sales_invoice_list.js",
    "Sales Order": "public/js/sales_order_list.js",
    "Material Request": "public/js/material_request_list.js",
}

jinja = {
	"methods": [
		"cannabis_management.api.manufacturing_process.run_production_log",
		"cannabis_management.mt_dispatch.fulfillment_board.lab_pull_sheet",
	],
}

before_migrate = ["cannabis_management.compat.install_frappe_shims"]

after_migrate = [
    "cannabis_management.workspace_cleanup.remove_unwanted_workspaces",
    "cannabis_management.workspace_cleanup.ensure_ar_weekly_review_stub",
    "cannabis_management.workspace_cleanup.ensure_renamed_workspace_stubs",
    "cannabis_management.manufacturing_portal.custom_fields.install",
    "cannabis_management.manufacturing_timesheet_kiosk.custom_fields.install",
    "cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard.seed_recon_statuses",
    "cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.seed_segments",
    "cannabis_management.cannabis_management.page.ar_legacy.ar_legacy.install_reach_out_field",
    "cannabis_management.credit_and_ar.customer_layout.enforce",
    "cannabis_management.credit_and_ar.notifications.install_notifications",
    "cannabis_management.credit_and_ar.dashboard_button.install",
    "cannabis_management.overrides.material_request_dashboard.install",
    "cannabis_management.wash_plan_install.install",
    "cannabis_management.doc_hooks.job_card.install_custom_fields",
    "cannabis_management.api.manufacturing_process.install_custom_fields",
    "cannabis_management.doc_hooks.stock_reconciliation.install_custom_fields",
    "cannabis_management.mt_dispatch.install.install",
    "cannabis_management.overrides.reports.install",
    "cannabis_management.overrides.si_cogs_alignment.install_custom_fields",
    "cannabis_management.api.undelivered_cogs.install_custom_fields",
    "cannabis_management.overrides.mr_run_status.install",
    "cannabis_management.farm_reports.install.install",
    "cannabis_management.branding.ensure_branding",
    "cannabis_management.branding.queue_translation_sync",
]

permission_query_conditions = {
    "Customer":      "cannabis_management.permissions.customer_query_conditions",
    "Sales Invoice": "cannabis_management.permissions.sales_invoice_query_conditions",
    "Cash Ledger Entry":      "cannabis_management.cash_management.permissions.cash_ledger_entry_query",
    "Expense Tracker Entry":  "cannabis_management.cash_management.permissions.expense_tracker_entry_query",
    "Personal Cash Tracking": "cannabis_management.cash_management.permissions.personal_cash_tracking_query",
    "Motley Cash Tracking":   "cannabis_management.cash_management.permissions.motley_cash_tracking_query",
    "TSBC Cash Tracking":     "cannabis_management.cash_management.permissions.tsbc_cash_tracking_query",
    "Safe Cash Tracking":     "cannabis_management.cash_management.permissions.safe_cash_tracking_query",
}

has_permission = {
    "Cash Tracker Person": "cannabis_management.cash_management.permissions.cash_tracker_person_has_permission",
    "Customer":      "cannabis_management.permissions.customer_has_permission",
    "Sales Invoice": "cannabis_management.permissions.sales_invoice_has_permission",
    "Personal Cash Tracking": "cannabis_management.cash_management.permissions.personal_cash_tracking_has_permission",
    "Motley Cash Tracking":   "cannabis_management.cash_management.permissions.motley_cash_tracking_has_permission",
    "TSBC Cash Tracking":     "cannabis_management.cash_management.permissions.tsbc_cash_tracking_has_permission",
    "Safe Cash Tracking":     "cannabis_management.cash_management.permissions.safe_cash_tracking_has_permission",
}

override_doctype_class = {
    "Stock Entry":          "cannabis_management.overrides.stock_entry_gl.CMStockEntry",
    "Purchase Receipt":     "cannabis_management.overrides.purchase_receipt_gl.CMPurchaseReceipt",
    "Delivery Note":        "cannabis_management.overrides.delivery_note_gl.CMDeliveryNote",
    "Stock Reconciliation": "cannabis_management.overrides.stock_reconciliation_gl.CMStockReconciliation",
    "Sales Invoice":        "cannabis_management.overrides.sales_invoice_gl.CMSalesInvoice",
    "Material Request":     "cannabis_management.overrides.mr_run_status.CMMaterialRequest",
    "Job Card":             "cannabis_management.overrides.job_card_qty.CMJobCard",
    "CRM Lead":             "cannabis_management.overrides.crm_lead_no_gravatar.CMCRMLead",
}

on_session_creation = [
    "cannabis_management.time_clock.login_location.on_session_creation",
    "cannabis_management.idle_logout.on_session_creation",
]

doc_events = {
    "Journal Entry": {
        "on_submit": "cannabis_management.api.undelivered_cogs.journal_entry_on_submit",
        "before_cancel": "cannabis_management.api.undelivered_cogs.journal_entry_before_cancel",
    },
    "Repost Accounting Ledger": {
        "validate": "cannabis_management.api.undelivered_cogs.repost_ledger_validate",
    },
    "User": {
        "validate": "cannabis_management.manufacturing_portal.user_hooks.validate",
    },

    "Employee": {
        "validate": "cannabis_management.manufacturing_timesheet_kiosk.employee_hooks.validate",
    },

    "Workstation": {
        "validate": "cannabis_management.cannabis_management.doctype.operating_component.operating_component.validate_workstation",
    },

    "Credit Application": {
        "before_insert": "cannabis_management.credit_and_ar.web_form_intake.before_insert",
    },
    "DocShare": {
        "validate": "cannabis_management.cash_management.permissions.docshare_validate",
    },
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
    "Motley Cash Tracking": {
        "before_cancel": "cannabis_management.cash_management.utils.cash_utils.restrict_cancel",
    },
    "TSBC Cash Tracking": {
        "before_cancel": "cannabis_management.cash_management.utils.cash_utils.restrict_cancel",
    },
    "Safe Cash Tracking": {
        "before_cancel": "cannabis_management.cash_management.utils.cash_utils.restrict_cancel",
    },
    "Personal Cash Tracking": {
        "before_cancel": "cannabis_management.cash_management.utils.cash_utils.restrict_cancel",
    },
    "CRM Lead": {
        "before_insert": "cannabis_management.api.crm_account_enhancements.check_lead_duplicate",
    },
    "CRM Organization": {
        "before_insert": "cannabis_management.api.crm_account_enhancements.check_organization_duplicate",
    },
    "CRM Deal": {
        "on_update": "cannabis_management.api.crm_account_enhancements.create_won_deal_followups",
    },
    "Sales Invoice": {
        "before_validate": "cannabis_management.doc_hooks.sales_invoice.before_validate",
        "validate": [
            "cannabis_management.credit_and_ar.payment_entry_hooks.stamp_invoice_ledger",
            "cannabis_management.overrides.delivery_note_hooks.set_expense_head",
        ],
        "before_submit": [
            "cannabis_management.doc_hooks.sales_invoice.before_submit",
            "cannabis_management.credit_and_ar.sales_invoice_hooks.before_submit",
        ],
        "on_submit": [
            "cannabis_management.doc_hooks.sales_invoice.on_submit",
            "cannabis_management.credit_and_ar.hold_engine.on_sales_invoice_submit",
            "cannabis_management.credit_and_ar.sales_invoice_hooks.on_submit",
        ],
        "on_cancel": "cannabis_management.credit_and_ar.sales_invoice_hooks.on_cancel",
    },
    "Quotation": {
        "validate": [
            "cannabis_management.overrides.quotation_approval.validate",
            "cannabis_management.overrides.license_compliance.check_license",
        ],
        "on_update":     "cannabis_management.overrides.quotation_approval.on_update",
        "before_submit": "cannabis_management.overrides.quotation_approval.before_submit",
    },
    "Material Request": {
        "on_cancel": "cannabis_management.doc_hooks.wash_plan_sync.material_request_unlink",
        "on_trash": "cannabis_management.doc_hooks.wash_plan_sync.material_request_unlink",
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
        ],
        "before_submit": [
            "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
            "cannabis_management.overrides.warehouse_account_utils.validate_item_group_mapping",
        ],
        "on_submit": [
            "cannabis_management.doc_hooks.stock_entry.carry_produced_qty_to_sibling_work_order",
            "cannabis_management.doc_hooks.wash_plan_sync.stock_entry_sync",
            "cannabis_management.overrides.mr_run_status.on_stock_entry_change",
        ],
        "on_cancel": [
            "cannabis_management.overrides.mr_run_status.on_stock_entry_change",
            "cannabis_management.doc_hooks.wash_plan_sync.stock_entry_sync",
        ],
    },
    "Sales Order": {
        "before_validate": "cannabis_management.doc_hooks.sales_invoice.before_validate",
        "validate": [
            "cannabis_management.credit_and_ar.sales_order_hooks.validate",
        ],
        "on_update": "cannabis_management.credit_and_ar.sales_order_hooks.on_update",
        "before_submit": [
            "cannabis_management.credit_and_ar.sales_order_hooks.before_submit",
            "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
        ],
        "on_submit": [
            "cannabis_management.overrides.sales_order_restrictions.on_submit",
            "cannabis_management.credit_and_ar.sales_order_hooks.on_submit",
        ],
        "on_cancel": "cannabis_management.credit_and_ar.sales_order_hooks.on_cancel",
    },
    "Delivery Note": {
        "before_submit": [
            "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
            "cannabis_management.overrides.warehouse_account_utils.validate_item_group_mapping",
        ],
        "on_update": [
            "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
            "cannabis_management.overrides.delivery_note_hooks.update_sales_order_delivery_status",
        ],
        "on_submit": [
            "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
            "cannabis_management.overrides.delivery_note_hooks.update_sales_order_delivery_status",
        ],
        "on_cancel": [
            "cannabis_management.overrides.delivery_note_hooks.update_sales_invoice_delivery_status",
            "cannabis_management.overrides.delivery_note_hooks.update_sales_order_delivery_status",
        ],
        "validate": "cannabis_management.overrides.delivery_note_hooks.set_expense_head",
    },
    "Purchase Order": {
        "before_validate": "cannabis_management.inter_company.drop_foreign_contact",
    },
    "Purchase Invoice": {
        "before_validate": "cannabis_management.inter_company.drop_foreign_contact",
    },
    "Purchase Receipt": {
        "before_validate": "cannabis_management.inter_company.drop_foreign_contact",
        "before_submit": [
            "cannabis_management.overrides.warehouse_account_utils.validate_item_group_mapping",
        ],
    },
    "Stock Reconciliation": {
        "before_submit": [
            "cannabis_management.overrides.warehouse_account_utils.validate_item_group_mapping",
        ],
        "after_insert": "cannabis_management.doc_hooks.wash_plan_sync.work_order_after_insert",
    },
    "Work Order": {
        "before_submit": "cannabis_management.credit_and_ar.hold_engine.enforce_hold",
        "on_submit": "cannabis_management.overrides.mr_run_status.on_work_order_change",
        "on_cancel": "cannabis_management.overrides.mr_run_status.on_work_order_change",
    },
    "Timesheet": {
        "after_insert": "cannabis_management.overrides.timesheet_hooks.auto_submit_timesheet",
        "on_trash": "cannabis_management.manufacturing_timesheet_kiosk.timesheet_hooks.on_trash",
    },
    "File": {
        "on_trash": "cannabis_management.manufacturing_timesheet_kiosk.timesheet_hooks.on_trash_file",
    },
    "Customer": {
        "validate": "cannabis_management.credit_and_ar.customer_hooks.validate",
        "on_update": "cannabis_management.credit_and_ar.customer_hooks.on_update",
    },
    "Workspace": {
        "on_update": "cannabis_management.home_hub_block.on_workspace_update",
        "on_trash": "cannabis_management.home_hub_block.on_trash",
    },
    "Report": {
        "after_insert": "cannabis_management.home_hub_block.on_report_change",
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
        "validate": "cannabis_management.credit_and_ar.payment_entry_hooks.validate",
        "on_submit": [
            "cannabis_management.cannabis_management.utils.irs_8300.check_cash_threshold",
            "cannabis_management.credit_and_ar.payment_entry_hooks.on_submit",
        ],
        "on_cancel": [
            "cannabis_management.credit_and_ar.hold_engine.on_payment_entry_cancel",
            "cannabis_management.credit_and_ar.payment_entry_hooks.on_cancel",
        ],
    },
    "Job Card": {
        "before_validate": "cannabis_management.doc_hooks.job_card.sync_micron_total_to_time_log",
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
            "cannabis_management.api.manufacturing_process.submit_tiering_stock_entries",
        ],
    },
}

from cannabis_management.mt_dispatch import hooks_wiring as _mt_dispatch_hooks

_mt_dispatch_hooks.extend_doc_events(doc_events)

scheduler_events = {
    "hourly": [
        "cannabis_management.credit_and_ar.customer_layout.enforce",
        "cannabis_management.credit_and_ar.notifications.install_notifications",
        "cannabis_management.credit_and_ar.dashboard_button.install",
        "cannabis_management.branding.ensure_branding",
        "cannabis_management.farm_reports.api.send_reminders",
    ],
    "cron": {
        "* * * * *": [
            "cannabis_management.manufacturing_timesheet_kiosk.api.auto_end_overtime_sessions",
            "cannabis_management.manufacturing_timesheet_kiosk.api.send_upcoming_cutoff_warnings",
        ],
        "0 7 * * *": [
            "cannabis_management.api.ar_reminders.send_ar_reminders",
            "cannabis_management.api.overdue_owner_reminder.send_overdue_owner_reminders",
            "cannabis_management.api.sales_daily_sync.snapshot_unreconciled",
            "cannabis_management.credit_and_ar.hold_engine.evaluate_customer_credit_status",
            "cannabis_management.credit_and_ar.hold_engine.check_broken_promises",
            "cannabis_management.credit_and_ar.hold_engine.check_license_expiry",
            "cannabis_management.credit_and_ar.plan_workout.check_plan_installments",
            "cannabis_management.credit_and_ar.plan_workout.review_workouts",
            "cannabis_management.credit_and_ar.metrics.evaluate_company_metrics",
            "cannabis_management.credit_and_ar.scoring.update_customer_payment_scores",
        ],
        "0 0 * * 1-5": [
            "cannabis_management.api.crm_sync.sync_crm_ar_data",
            "cannabis_management.cannabis_management.utils.irs_8300.check_overdue_filings",
            "cannabis_management.cannabis_management.utils.irs_8300.send_january_notices",
            "cannabis_management.cash_management.utils.cash_utils.check_overdue_form_8300",
            "cannabis_management.overrides.payment_schedule_reminder.send_payment_schedule_reminders",
        ],
        "0 14 * * 1-5": [
            "cannabis_management.overrides.sales_order_delivery_reminder.send_delivery_date_reminders",
        ],
        "0 8 * * 5": [
            "cannabis_management.credit_and_ar.weekly_report.send_weekly_report",
        ],
        "0 14 * * 5": [
        ],
        "0 6 1 * *": [
            "cannabis_management.credit_and_ar.finance_charge.apply_finance_charges",
        ],
        "0 8 * * 1": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.generate_weekly_signoff",
        ],
        "0 8 * * 2": [
            "cannabis_management.cannabis_management.overrides.weekly_signoff.send_acknowledgment_reminder",
        ],
        "0 1 * * 1-5": [
            "cannabis_management.api.daily_report.send_daily_report",
        ],
        "0 4 * * *": [
            "cannabis_management.cannabis_management.page.employee_timesheet.employee_timesheet.send_daily_report",
        ],
        "0 3 * * *": [
            "cannabis_management.api.dn_gap_report.send_dn_gap_report",
        ],
        "0 11 * * *": [
            "cannabis_management.api.ar_dashboard_email.send_scheduled_ar_report",
        ],
        "0 3 * * 5": [
            "cannabis_management.api.ar_report.send_ar_report",
        ],
    },
    "monthly": [
    ],
}

override_whitelisted_methods = {
    "frappe.utils.change_log.get_versions": "cannabis_management.branding.get_versions",

    "erpnext.selling.doctype.quotation.quotation.make_sales_order":
        "cannabis_management.overrides.quote_to_order.make_sales_order",

    "cannabis_management.cash_management.utils.cash_utils.create_payment_entry":
        "cannabis_management.api.cash_payment_override.create_payment_entry",

    "frappe.www.printview.get_html_and_style":
        "cannabis_management.credit_and_ar.print_guard.get_html_and_style",
    "frappe.utils.print_format.download_pdf":
        "cannabis_management.credit_and_ar.print_guard.download_pdf",
    "frappe.utils.weasyprint.download_pdf":
        "cannabis_management.credit_and_ar.print_guard.weasyprint_download_pdf",
    "frappe.core.doctype.communication.email.make":
        "cannabis_management.credit_and_ar.print_guard.make",

    "frappe.desk.desktop.get_desktop_page":
        "cannabis_management.api.workspace_guard.get_desktop_page",
    "frappe.desk.desktop.get_workspace_sidebar_items":
        "cannabis_management.api.workspace_guard.get_workspace_sidebar_items",

    "frappe.desk.query_report.run":
        "cannabis_management.api.report_filters.run",
    "frappe.desk.query_report.export_query":
        "cannabis_management.api.report_filters.export_query",
}
override_doctype_dashboards = {
	"Sales Order": "cannabis_management.overrides.sales_order_dashboard.get_data",
	"Customer": "cannabis_management.overrides.customer_dashboard.get_data",
	"Material Request": "cannabis_management.overrides.material_request_dashboard.get_data",
}

ignore_links_on_delete = ["Connection Tool", "Connection Tool Link"]

before_request = [
	"cannabis_management.manufacturing_portal.cookie_scheme_fix.fix_scheme_for_unproxied_requests",
	"cannabis_management.manufacturing_timesheet_kiosk.routing.route_kiosk_api",
	"cannabis_management.overrides.stock_balance_dimensions.apply",
]

before_job = ["cannabis_management.overrides.stock_balance_dimensions.apply"]

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            [
                "fieldname",
                "not in",
                [
                    "tier",
                    "to_tier",
                    "from_tier",
                    "rejected_tier",
                ],
            ]
        ],
    },
    "Client Script",
    "Server Script",
    "Property Setter",
    "Workflow",
    "Workflow State",
    "Workflow Action",
    {"dt": "DocType", "filters": [["name", "=", "Warehouse Item Group Account Mapping"]]},
    {"dt": "DocType", "filters": [["name", "=", "Weekly Sales Report"]]},
    {"dt": "DocType", "filters": [["name", "=", "Cash Tracker Person"]]},
    {"dt": "DocType", "filters": [["name", "=", "Cash Balance Ledger"]]},
    {"dt": "DocType", "filters": [["name", "=", "Cash Account Mapping"]]},
    {"dt": "DocType", "filters": [["name", "=", "Cash Ledger Entry"]]},
    {"dt": "DocType", "filters": [["name", "=", "Expense Tracker Entry"]]},
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
    {"dt": "Workflow Action Master", "filters": [["name", "in", [
        "Submit for Review", "Approve", "Reject", "Lock",
        "Activate", "Mark Expired", "Terminate",
        "Recommend", "Revoke",
    ]]]},
    {"dt": "DocType", "filters": [["name", "=", "AR Recon Snapshot"]]},
    {"dt": "Custom HTML Block", "filters": [["name", "in", [
        "Home Hub",
        "Sales Daily Sync Dashboard Block",
        "Lab Daily Sync Dashboard Block",
        "Sales Target and Inventory Dashboard",
        "Distribution Hub",
        "Company Records Hub",
        "Nikki",
        "Jamie",
    ]]]},
    {"dt": "Web Page", "filters": [["name", "in", ["live-menu-2", "mtm-inventory-dashboard"]]]},
    {"dt": "Number Card", "filters": [["name", "like", "Credit \u2014 %"]]},
    {"dt": "Notification", "filters": [["module", "=", "Credit and AR"]]},
]

_mt_dispatch_hooks.extend_scheduler_events(scheduler_events)
_mt_dispatch_hooks.extend_doctype_js(doctype_js)
