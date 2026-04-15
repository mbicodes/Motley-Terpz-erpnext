"""
Work Order override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Work Order"]["on_update"]

Responsibilities:
- Sync Work Order status changes to linked Production Batch Group.
"""

import frappe


# Status mapping: WO status → PBG status
_WO_TO_PBG_STATUS = {
    "Not Started": "Open",
    "In Process": "In Wash",
    "Completed": "Closed",
    "Stopped": "Closed",
}


def on_update(doc, method=None):
    """Sync WO status change to the linked Production Batch Group."""
    pbg_name = doc.get("custom_production_batch_group")
    if not pbg_name:
        return

    new_status = _WO_TO_PBG_STATUS.get(doc.status)
    if not new_status:
        return

    current_status = frappe.db.get_value("Production Batch Group", pbg_name, "status")
    # Don't downgrade a status that's already further along
    _STATUS_ORDER = ["Open", "In Wash", "In Press", "Inventory Verification", "Closed"]
    if (current_status in _STATUS_ORDER and new_status in _STATUS_ORDER and
            _STATUS_ORDER.index(new_status) <= _STATUS_ORDER.index(current_status)):
        return

    frappe.db.set_value("Production Batch Group", pbg_name, "status", new_status)
