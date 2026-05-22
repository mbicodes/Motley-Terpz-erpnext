"""
Patch: remove all Master Touch Manufacturing database records.

Fixtures only handle insert/update — they never delete existing DB rows.
This patch cleans up what the fixture removal left behind:
  - Custom Fields belonging to the MTM module
  - Custom DocTypes registered under MTM
  - The Module Def record for Master Touch Manufacturing
  - Orphaned Server Scripts / Client Scripts belonging to MTM
"""
import frappe


MTM_MODULE   = "Master Touch Manufacturing"
MTM_DOCTYPES = [
    "Wash Batch",
    "Press Batch",
    "Wash Detail",
    "Press Detail",
    "METRC Retag Log",
    "Inventory Verification",
    "Production Batch Group",
    "METRC Package Verification",
]

# Custom Fields that reference MTM (added to standard doctypes)
MTM_CUSTOM_FIELDS = [
    "Sales Invoice-custom_production_batch_group",
    "Stock Entry-custom_production_batch_group",
    "Batch-custom_production_batch_group",
    "Batch-custom_wash_batch_ref",
    "Batch-custom_press_batch_ref",
    "Purchase Receipt-custom_production_batch_group",
    "Purchase Receipt-custom_retag_log",
    "Work Order-custom_production_batch_group",
    "Job Card-custom_production_batch_group",
    "Job Card-custom_wash_batch_ref",
    "Job Card-custom_press_batch_ref",
]


def execute():
    _remove_custom_fields()
    _remove_custom_doctypes()
    _remove_module_def()
    _remove_scripts()
    frappe.clear_cache()
    frappe.db.commit()


def _remove_custom_fields():
    # Delete by known name list
    for cf_name in MTM_CUSTOM_FIELDS:
        if frappe.db.exists("Custom Field", cf_name):
            frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
            frappe.logger().info(f"[remove_mtm] deleted Custom Field: {cf_name}")

    # Catch everything with module = MTM regardless of name
    stray = frappe.get_all(
        "Custom Field",
        filters={"module": MTM_MODULE},
        pluck="name",
    )
    for name in stray:
        frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
        frappe.logger().info(f"[remove_mtm] deleted stray Custom Field: {name}")

    # Catch fields whose module was blank/unset but label/fieldname reveals MTM origin
    # (the Purchase Receipt fields visible in the screenshot fall in this bucket)
    frappe.db.sql("""
        DELETE FROM `tabCustom Field`
        WHERE
            label LIKE '%Master%Touch%'
            OR label LIKE '%METRC%'
            OR label LIKE '%Production Batch%'
            OR label LIKE '%Weight Sent%'
            OR label LIKE '%Weight Received%'
            OR label LIKE '%Weight Verified%'
            OR label LIKE '%Retag Log%'
            OR fieldname LIKE '%retag%'
            OR fieldname LIKE '%metrc%'
            OR (fieldtype = 'Section Break' AND label = 'Masters Touch Manufacturing')
    """)


def _remove_custom_doctypes():
    for dt in MTM_DOCTYPES:
        if not frappe.db.exists("DocType", dt):
            continue
        try:
            frappe.delete_doc("DocType", dt, ignore_permissions=True, force=True)
            frappe.logger().info(f"[remove_mtm] deleted DocType: {dt}")
        except Exception:
            # If it has data rows, just clear the module reference so it no longer
            # tries to resolve the deleted Python package
            frappe.db.set_value("DocType", dt, "module", "Cannabis Management")
            frappe.logger().info(f"[remove_mtm] reassigned DocType module: {dt}")


def _remove_module_def():
    if frappe.db.exists("Module Def", MTM_MODULE):
        frappe.delete_doc("Module Def", MTM_MODULE, ignore_permissions=True, force=True)
        frappe.logger().info(f"[remove_mtm] deleted Module Def: {MTM_MODULE}")


def _remove_scripts():
    # Server Scripts
    ss = frappe.get_all(
        "Server Script",
        filters={"module": MTM_MODULE},
        pluck="name",
    )
    for name in ss:
        frappe.delete_doc("Server Script", name, ignore_permissions=True, force=True)
        frappe.logger().info(f"[remove_mtm] deleted Server Script: {name}")

    # Client Scripts
    cs = frappe.get_all(
        "Client Script",
        filters={"module": MTM_MODULE},
        pluck="name",
    )
    for name in cs:
        frappe.delete_doc("Client Script", name, ignore_permissions=True, force=True)
        frappe.logger().info(f"[remove_mtm] deleted Client Script: {name}")
