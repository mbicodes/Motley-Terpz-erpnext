"""
Patch: delete the custom_production_batch_group Custom Field from all doctypes
where it was created (Batch, Job Card, Purchase Receipt, Sales Invoice,
Stock Entry, Work Order).

Uses direct SQL to bypass Frappe's validation — the field references a
non-existent doctype "Production Batch Group" so delete_doc raises an error.
Safe to re-run.
"""
import frappe


def execute():
    frappe.db.sql("""
        DELETE FROM `tabCustom Field`
        WHERE fieldname = 'custom_production_batch_group'
    """)

    frappe.db.sql("""
        DELETE FROM `tabProperty Setter`
        WHERE field_name = 'custom_production_batch_group'
    """)

    frappe.clear_cache()
    frappe.db.commit()
