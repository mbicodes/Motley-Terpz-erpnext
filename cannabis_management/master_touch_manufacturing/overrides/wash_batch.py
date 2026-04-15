"""
Wash Batch override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Wash Batch"]["on_submit"]

Responsibilities:
- Auto-create one ERPNext Batch per Wash Detail row (Bubble Hash batches).
- Write batch name back to Wash Detail.erpnext_batch.
- Link each BH batch to the source FF batch via custom_source_batch.
"""

import frappe
from frappe.utils import flt

# Map quality grade → placeholder item (template until per-strain items are assigned)
_GRADE_ITEM = {
    "Full Melt":  "hash-prime-template",
    "4-Star":     "hash-prime-template",
    "3-Star":     "hash-sub-template",
    "2-Star":     "hash-sub-template",
    "Food Grade": "hash-sub-template",
}


def on_submit(doc, method=None):
    _create_bh_batches(doc)


def _create_bh_batches(doc):
    """Create one Bubble Hash ERPNext Batch per Wash Detail row."""
    # Find source FF batch linked to this PBG
    ff_batch = None
    if doc.production_batch_group:
        ff_batch = frappe.db.get_value(
            "Batch",
            {
                "custom_production_batch_group": doc.production_batch_group,
                "custom_batch_type": "Fresh Frozen",
            },
            "name",
        )

    for row in doc.get("wash_details") or []:
        if row.get("erpnext_batch"):
            continue  # already created
        if not flt(row.get("grams_collected")):
            continue

        item_code = _GRADE_ITEM.get(row.get("quality_grade") or "", "hash-prime-template")

        batch = frappe.new_doc("Batch")
        batch.item = item_code
        batch.batch_qty = flt(row.grams_collected)
        batch.manufacturing_date = doc.wash_date
        batch.custom_batch_type = "Bubble Hash"
        batch.custom_quality_grade = row.get("quality_grade") or ""
        batch.custom_batch_status = "Active"
        batch.custom_net_weight_g = flt(row.grams_collected)
        batch.custom_wash_batch_ref = doc.name
        batch.custom_metrc_tag = row.get("metrc_tag_bubble") or ""
        if ff_batch:
            batch.custom_source_batch = ff_batch
        if doc.production_batch_group:
            batch.custom_production_batch_group = doc.production_batch_group

        batch.insert(ignore_permissions=True)
        frappe.db.commit()

        # Write batch back to Wash Detail row
        frappe.db.set_value("Wash Detail", row.name, "erpnext_batch", batch.name)
