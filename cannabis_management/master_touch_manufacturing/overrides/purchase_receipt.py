"""
Purchase Receipt override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Purchase Receipt"]["on_submit"]

Responsibilities:
- Calculate weight variance (sent vs received); Slack alert if > 50g.
- Fire Slack METRC retag alerts for each retag log row.
- Auto-create one ERPNext Batch per METRC Retag Log row (FF batches).
"""

import frappe
from frappe.utils import flt
from cannabis_management.master_touch_manufacturing.utils.slack import (
    alert_metrc_retag_required,
    send_alert,
)


def on_submit(doc, method=None):
    _calculate_weight_variance(doc)
    _create_ff_batches(doc)
    _fire_retag_alerts(doc)


def _calculate_weight_variance(doc):
    sent = float(doc.get("custom_weight_sent_g") or 0)
    received = float(doc.get("custom_weight_received_g") or 0)
    if sent or received:
        frappe.db.set_value(
            "Purchase Receipt", doc.name,
            "custom_weight_variance_g", round(sent - received, 2)
        )

    variance = round(sent - received, 2)
    if abs(variance) > 50:
        # Flag significant weight discrepancy to Slack
        try:
            send_alert(
                "slack_mtm_compliance",
                f":scales: *Weight Discrepancy on PR `{doc.name}`*\n"
                f"Sent: {sent}g | Received: {received}g | Variance: {variance}g\n"
                f"Supplier: {doc.supplier}"
            )
        except Exception:
            pass


def _create_ff_batches(doc):
    """Create one Fresh Frozen ERPNext Batch per METRC Retag Log row."""
    retag_rows = doc.get("custom_retag_log") or []
    if not retag_rows:
        return

    # Find FF item from receipt line items
    ff_item = None
    for row in doc.get("items") or []:
        ig = frappe.db.get_value("Item", row.item_code, "item_group") or ""
        if "Fresh Frozen" in ig:
            ff_item = row.item_code
            break

    if not ff_item:
        return

    pbg = doc.get("custom_production_batch_group")

    for row in retag_rows:
        new_tag = row.get("new_tag") or ""
        if not new_tag:
            continue
        # Skip if a batch with this METRC tag already exists
        if frappe.db.exists("Batch", {"custom_metrc_tag": new_tag}):
            continue

        batch = frappe.new_doc("Batch")
        batch.item = ff_item
        batch.batch_qty = flt(row.get("weight_g") or 0)
        batch.manufacturing_date = doc.posting_date
        batch.custom_batch_type = "Fresh Frozen"
        batch.custom_metrc_tag = new_tag
        batch.custom_batch_status = "Active"
        batch.custom_net_weight_g = flt(row.get("weight_g") or 0)
        if pbg:
            batch.custom_production_batch_group = pbg
        batch.insert(ignore_permissions=True)
        frappe.db.commit()


def _fire_retag_alerts(doc):
    """Post Slack alert for every METRC retag log row."""
    retag_rows = doc.get("custom_retag_log") or []
    if not retag_rows:
        return

    try:
        for row in retag_rows:
            alert_metrc_retag_required(
                doc.name,
                row.get("strain") or "",
                row.get("original_tag") or ""
            )
    except Exception:
        pass
