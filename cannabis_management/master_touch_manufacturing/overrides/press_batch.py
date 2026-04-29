"""
Press Batch override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Press Batch"]["on_submit"]

Responsibilities:
- Auto-create one ERPNext Batch per Press Detail row (Rosin batches).
- Write batch name back to Press Detail.erpnext_batch.
- Link each Rosin batch to source BH batch via custom_source_batch.
"""

import frappe
from frappe.utils import flt
from frappe.model.naming import make_autoname


def on_submit(doc, method=None):
    _create_rosin_batches(doc)


def _create_rosin_batches(doc):
    """Create one Rosin ERPNext Batch per Press Detail row."""
    # Find source Bubble Hash batch linked to this PBG
    bh_batch = None
    if doc.production_batch_group:
        bh_batch = frappe.db.get_value(
            "Batch",
            {
                "custom_production_batch_group": doc.production_batch_group,
                "custom_batch_type": "Bubble Hash",
            },
            "name",
        )

    for row in doc.get("press_details") or []:
        if row.get("erpnext_batch"):
            continue  # already created
        if not flt(row.get("grams_rosin")):
            continue

        batch = frappe.new_doc("Batch")
        batch.batch_id = make_autoname("BATCH-RO-.#####")
        batch.item = "rosin-template"
        batch.batch_qty = flt(row.grams_rosin)
        batch.manufacturing_date = doc.press_date
        batch.custom_batch_type = "Rosin"
        batch.custom_batch_status = "Active"
        batch.custom_net_weight_g = flt(row.grams_rosin)
        batch.custom_press_batch_ref = doc.name
        batch.custom_metrc_tag = row.get("metrc_tag_rosin") or ""
        if bh_batch:
            batch.custom_source_batch = bh_batch
        if doc.production_batch_group:
            batch.custom_production_batch_group = doc.production_batch_group

        batch.insert(ignore_permissions=True)
        frappe.db.commit()

        # Write batch back to Press Detail row
        frappe.db.set_value("Press Detail", row.name, "erpnext_batch", batch.name)
