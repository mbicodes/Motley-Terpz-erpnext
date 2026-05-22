"""
Patch: create the 6 CRM Lead Statuses for the Motley Terpz pipeline.
Safe to re-run — skips statuses that already exist.
"""
import frappe


STATUSES = [
    {"lead_status": "Lead",       "type": "Open",    "position": 1, "color": "gray"},
    {"lead_status": "Contacted",  "type": "Ongoing", "position": 2, "color": "orange"},
    {"lead_status": "Sample/QC",  "type": "Ongoing", "position": 3, "color": "blue"},
    {"lead_status": "Active",     "type": "Ongoing", "position": 4, "color": "green"},
    {"lead_status": "Inactive",   "type": "On Hold", "position": 5, "color": "amber"},
    {"lead_status": "Lost",       "type": "Lost",    "position": 6, "color": "red"},
]


def execute():
    if not frappe.db.exists("DocType", "CRM Lead Status"):
        frappe.logger().info("[crm_statuses] CRM Lead Status doctype not found — skipping")
        return

    for s in STATUSES:
        if frappe.db.exists("CRM Lead Status", s["lead_status"]):
            continue
        doc = frappe.get_doc({"doctype": "CRM Lead Status", **s})
        doc.insert(ignore_permissions=True)
        frappe.logger().info(f"[crm_statuses] created: {s['lead_status']}")

    frappe.db.commit()
