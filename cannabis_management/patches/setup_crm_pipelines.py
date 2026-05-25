"""
Patch: create the 4 Kanban pipeline views in CRM View Settings for CRM Lead.

Each view is a public, pinned Kanban filtered by custom_pipeline.
Safe to re-run — skips views that already exist (checked by label + dt + type).
Also repairs any existing views that have user=NULL or wrong kanban_columns.
"""
import json
import frappe


KANBAN_COLUMNS = ["Lead", "Contacted", "Sample/QC", "Active", "Inactive", "Lost"]

PIPELINES = [
    {"label": "Fresh Frozen",      "icon": "❄️", "filter": "Fresh Frozen"},
    {"label": "Rosin / Solventless","icon": "🌿", "filter": "Rosin / Solventless"},
    {"label": "Retail / Distro",   "icon": "🏪", "filter": "Retail / Distro"},
    {"label": "Tolling",           "icon": "⚙️", "filter": "Tolling"},
]


def execute():
    if not frappe.db.exists("DocType", "CRM View Settings"):
        frappe.logger().info("[setup_crm_pipelines] CRM View Settings not found — skipping")
        return
    if not frappe.db.exists("DocType", "CRM Lead"):
        frappe.logger().info("[setup_crm_pipelines] CRM Lead not found — skipping")
        return

    columns_json = json.dumps(KANBAN_COLUMNS)

    for p in PIPELINES:
        existing = frappe.db.get_value(
            "CRM View Settings",
            {"label": p["label"], "dt": "CRM Lead", "type": "kanban"},
            "name",
        )
        if existing:
            # Repair user=NULL and fix kanban_columns on existing records
            frappe.db.set_value("CRM View Settings", existing, {
                "user": "",
                "kanban_columns": columns_json,
                "public": 1,
                "pinned": 1,
            })
            frappe.logger().info(f"[setup_crm_pipelines] repaired: {p['label']}")
            continue

        doc = frappe.new_doc("CRM View Settings")
        doc.label          = p["label"]
        doc.dt             = "CRM Lead"
        doc.type           = "kanban"
        doc.icon           = p["icon"]
        doc.column_field   = "status"
        doc.user           = ""
        doc.filters        = json.dumps({"custom_pipeline": ["=", p["filter"]]})
        doc.kanban_columns = columns_json
        doc.kanban_fields  = json.dumps([])
        doc.public         = 1
        doc.pinned         = 1
        doc.insert(ignore_permissions=True)
        frappe.logger().info(f"[setup_crm_pipelines] created: {p['label']}")

    frappe.db.commit()
