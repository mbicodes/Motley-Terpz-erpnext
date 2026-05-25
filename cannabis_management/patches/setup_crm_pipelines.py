"""
Patch: create the 4 Kanban pipeline views in CRM View Settings for CRM Lead.

Each view is a public, pinned Kanban filtered by custom_pipeline.
Columns come from CRM Lead Status (synced automatically by the CRM app).
Safe to re-run — skips views that already exist.
"""
import json
import frappe


PIPELINES = [
    {
        "label":  "Fresh Frozen",
        "icon":   "❄️",
        "filter": "Fresh Frozen",
    },
    {
        "label":  "Rosin / Solventless",
        "icon":   "🌿",
        "filter": "Rosin / Solventless",
    },
    {
        "label":  "Retail / Distro",
        "icon":   "🏪",
        "filter": "Retail / Distro",
    },
    {
        "label":  "Tolling",
        "icon":   "⚙️",
        "filter": "Tolling",
    },
]


def execute():
    if not frappe.db.exists("DocType", "CRM View Settings"):
        frappe.logger().info("[setup_crm_pipelines] CRM View Settings not found — skipping")
        return
    if not frappe.db.exists("DocType", "CRM Lead"):
        frappe.logger().info("[setup_crm_pipelines] CRM Lead not found — skipping")
        return

    # Fetch the status values to pre-populate kanban columns
    statuses = frappe.get_all(
        "CRM Lead Status",
        fields=["lead_status as status"],
        order_by="position asc",
    )
    kanban_columns = [s.status for s in statuses] if statuses else []

    for p in PIPELINES:
        if frappe.db.exists("CRM View Settings", p["label"]):
            frappe.logger().info(f"[setup_crm_pipelines] already exists: {p['label']}")
            continue

        doc = frappe.new_doc("CRM View Settings")
        doc.name          = p["label"]
        doc.label         = p["label"]
        doc.dt            = "CRM Lead"
        doc.type          = "kanban"
        doc.icon          = p["icon"]
        doc.column_field  = "status"
        doc.filters       = json.dumps({"custom_pipeline": ["=", p["filter"]]})
        doc.kanban_columns = json.dumps(kanban_columns)
        doc.kanban_fields  = json.dumps([])
        doc.public         = 1
        doc.pinned         = 1
        doc.insert(ignore_permissions=True)
        frappe.logger().info(f"[setup_crm_pipelines] created: {p['label']}")

    frappe.db.commit()
