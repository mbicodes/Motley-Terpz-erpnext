"""
Work Order override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Work Order"]["on_update"]

Responsibilities:
- Sync Work Order status changes to linked Production Batch Group.
- Propagate actual_yield_qty to the next Work Order's raw material quantity.
"""

import frappe
from frappe.utils import flt


# Status mapping: WO status → PBG status
_WO_TO_PBG_STATUS = {
    "Not Started": "Open",
    "In Process": "In Wash",
    "Completed": "Closed",
    "Stopped": "Closed",
}


def on_update(doc, method=None):
    """Sync WO status change to PBG and propagate actual yield to next WO."""
    _sync_pbg_status(doc)
    _propagate_actual_yield(doc)


def _sync_pbg_status(doc):
    pbg_name = doc.get("custom_production_batch_group")
    if not pbg_name:
        return

    new_status = _WO_TO_PBG_STATUS.get(doc.status)
    if not new_status:
        return

    current_status = frappe.db.get_value("Production Batch Group", pbg_name, "status")
    _STATUS_ORDER = ["Open", "In Wash", "In Press", "Inventory Verification", "Closed"]
    if (current_status in _STATUS_ORDER and new_status in _STATUS_ORDER and
            _STATUS_ORDER.index(new_status) <= _STATUS_ORDER.index(current_status)):
        return

    frappe.db.set_value("Production Batch Group", pbg_name, "status", new_status)


def _propagate_actual_yield(doc):
    """
    When actual_yield_qty is set on this WO, find the next WO in the chain
    (the one whose BOM uses this WO's production_item as its raw material)
    and update that WO's required_items qty — without changing this WO's own RM qty.

    Chain example:
        WO1: Fresh Frozen → [Wash] → Bubble Hash   (actual_yield_qty = 12g)
        WO2: Bubble Hash  → [Press] → Rosin         (required_items[Bubble Hash].required_qty = 12g)
    """
    actual_qty = flt(doc.get("custom_actual_yield_qty"))
    if not actual_qty:
        return

    mr_name = doc.get("material_request")
    if not mr_name:
        return

    production_item = doc.production_item

    # Find the next BOM in this MR's chain: a BOM whose RM is this WO's FG
    next_bom_rows = frappe.db.sql(
        """
        SELECT b.name
        FROM `tabBOM` b
        JOIN `tabBOM Item` bi ON bi.parent = b.name
        WHERE b.custom_material_request = %s
          AND b.docstatus = 1
          AND bi.item_code = %s
        LIMIT 1
        """,
        (mr_name, production_item),
        as_dict=True,
    )

    if not next_bom_rows:
        return

    next_bom_name = next_bom_rows[0].name

    next_wo_name = frappe.db.get_value(
        "Work Order",
        {"bom_no": next_bom_name, "docstatus": ["!=", 2]},
        "name",
    )
    if not next_wo_name:
        return

    next_wo = frappe.get_doc("Work Order", next_wo_name)

    updated = False
    for row in next_wo.required_items:
        if row.item_code == production_item:
            row.required_qty = actual_qty
            updated = True
            break

    if updated:
        # Direct DB write — bypasses Work Order validate() which would recalculate
        # required_items from BOM ratios and overwrite our value.
        frappe.db.sql(
            """UPDATE `tabWork Order Item`
               SET required_qty = %s
               WHERE parent = %s AND item_code = %s""",
            (actual_qty, next_wo_name, production_item),
        )
        frappe.db.commit()
        frappe.msgprint(
            "Next Work Order <b>{0}</b> raw material qty updated to {1} (actual yield from {2}).".format(
                next_wo_name, actual_qty, doc.name
            ),
            alert=True,
        )
