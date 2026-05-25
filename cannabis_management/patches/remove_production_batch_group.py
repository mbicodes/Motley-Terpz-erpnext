"""
Patch: delete the custom_production_batch_group Custom Field from all doctypes
where it was created (Batch, Job Card, Purchase Receipt, Sales Invoice,
Stock Entry, Work Order).  Safe to re-run — skips if field is already gone.
"""
import frappe


DOCTYPES = [
    "Batch",
    "Job Card",
    "Purchase Receipt",
    "Sales Invoice",
    "Stock Entry",
    "Work Order",
]


def execute():
    for dt in DOCTYPES:
        cf_name = f"{dt}-custom_production_batch_group"
        if frappe.db.exists("Custom Field", cf_name):
            frappe.delete_doc("Custom Field", cf_name, ignore_missing=True, force=True)
            frappe.logger().info(f"[remove_production_batch_group] deleted {cf_name}")

    frappe.clear_cache()
    frappe.db.commit()
