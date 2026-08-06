# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Stock movements -> Metrc package operations.

The tag on a stock row already reaches us through the existing "Muid" Inventory
Dimension, so this module reuses get_touched_tags() from the Metric Tag module
rather than re-deriving it. That keeps one definition of "which tags did this
document touch" across the app.

Mapping:
    Stock Reconciliation  -> PUT /packages/v2/adjust   (signed delta)
    Stock Entry (issue)   -> PUT /packages/v2/adjust   (negative delta)
    Batch fully depleted  -> PUT /packages/v2/finish
"""

import frappe
from frappe.utils import flt

from cannabis_management.cannabis_management.doctype.metric_tag.metric_tag import get_touched_tags
from cannabis_management.metrc import config, mapping
from cannabis_management.metrc.push.outbox import enqueue

# Metrc requires a reason from GET /packages/v2/adjust/reasons. These are the
# CA defaults; the Stock Reconciliation field can override per document.
DEFAULT_ADJUST_REASON = "Scale Variance"
WASTE_ADJUST_REASON = "Waste (Non-Mandated)"


def _uom_for_tag(tag, fallback=None):
    """Send quantities in the unit Metrc holds for that package.

    Never convert: rounding drift between grams and ounces shows up as a
    compliance variance.
    """
    metrc_uom = frappe.db.get_value("Metric Tag", tag, "custom_metrc_uom")
    if metrc_uom and mapping.is_metrc_uom(metrc_uom):
        return metrc_uom
    return mapping.to_metrc_uom(fallback) if fallback else "Grams"


# ---------------------------------------------------------------------------
# Stock Reconciliation -> adjust
# ---------------------------------------------------------------------------


def on_stock_reconciliation_submit(doc, method=None):
    """Metrc adjust takes a signed delta, not the new total.

    Stock Reconciliation carries both current_qty (before) and qty (after), so
    the delta is available without re-reading the ledger.
    """
    if not config.is_enabled():
        return

    license_number = config.license_for_doc(doc)
    if not license_number:
        return

    reason = doc.get("custom_metrc_adjustment_reason") or DEFAULT_ADJUST_REASON
    adjustments = []

    for row in doc.get("items") or []:
        tag = _row_tag(row)
        if not tag:
            continue
        delta = flt(row.get("qty")) - flt(row.get("current_qty"))
        if abs(delta) < 0.0001:
            continue
        adjustments.append(
            {
                "Label": tag,
                "Quantity": delta,
                "UnitOfMeasure": _uom_for_tag(tag, row.get("stock_uom") or row.get("uom")),
                "AdjustmentReason": reason,
                "AdjustmentDate": str(doc.posting_date),
                "ReasonNote": doc.get("custom_compliance_notes") or None,
            }
        )

    if not adjustments:
        doc.db_set("custom_metrc_sync_status", "Not Tracked", update_modified=False)
        return

    enqueue(
        operation="packages.adjust",
        license_number=license_number,
        payload=adjustments,
        reference_doctype="Stock Reconciliation",
        reference_name=doc.name,
    )
    doc.db_set("custom_metrc_sync_status", "Queued", update_modified=False)


# ---------------------------------------------------------------------------
# Stock Entry -> adjust
# ---------------------------------------------------------------------------


def on_stock_entry_submit(doc, method=None):
    """Report consumption/waste that leaves Metrc inventory.

    Only outbound purposes are pushed. Package *creation* (Material Receipt,
    Repack, Manufacture) has to originate from a harvest or a processing job in
    Metrc so the parent-child lineage is correct - those flow through
    push.processing, not here.
    """
    if not config.is_enabled():
        return
    if doc.purpose not in ("Material Issue", "Material Consumption for Manufacture"):
        return

    license_number = config.license_for_doc(doc)
    if not license_number:
        return

    reason = WASTE_ADJUST_REASON if doc.purpose == "Material Issue" else DEFAULT_ADJUST_REASON
    adjustments = []

    for tag, item_code, _warehouse in get_touched_tags(doc):
        qty = _issued_qty_for_tag(doc, tag)
        if not qty:
            continue
        adjustments.append(
            {
                "Label": tag,
                "Quantity": -abs(qty),
                "UnitOfMeasure": _uom_for_tag(tag, frappe.db.get_value("Item", item_code, "stock_uom")),
                "AdjustmentReason": reason,
                "AdjustmentDate": str(doc.posting_date),
                "ReasonNote": f"{doc.doctype} {doc.name} ({doc.purpose})",
            }
        )

    if not adjustments:
        doc.db_set("custom_metrc_sync_status", "Not Tracked", update_modified=False)
        return

    enqueue(
        operation="packages.adjust",
        license_number=license_number,
        payload=adjustments,
        reference_doctype="Stock Entry",
        reference_name=doc.name,
    )
    doc.db_set(
        {"custom_metrc_sync_status": "Queued", "custom_metrc_operation": "packages.adjust"},
        update_modified=False,
    )


def _issued_qty_for_tag(doc, tag):
    """Total quantity issued against a tag on this Stock Entry.

    A Stock Entry Detail row can carry two tags - "muid" for the s_warehouse
    leg and "to_muid" for the t_warehouse leg - so only count the issuing leg.
    """
    from cannabis_management.cannabis_management.doctype.metric_tag.metric_tag import (
        get_stock_entry_legs,
    )

    source_field = get_stock_entry_legs()[0][0]
    total = 0.0
    for row in doc.get("items") or []:
        if row.get(source_field) == tag and row.get("s_warehouse"):
            total += flt(row.get("qty"))
    return total


def _row_tag(row):
    if row.get("batch_no"):
        tag = frappe.db.get_value("Batch", row.batch_no, "custom_metrc_tag")
        if tag:
            return tag
    for fieldname in ("muid", "metric_tag"):
        if row.get(fieldname):
            return row.get(fieldname)
    return None


# ------------------------------------------------------------------ handlers


def adjust_package(client, payload, outbox_doc):
    """PUT /packages/v2/adjust, chunked to Metrc's 10-object limit."""
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    client.put_chunked("/packages/v2/adjust", payload, reference=reference)
    return {"Adjusted": len(payload)}


def finish_package(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    client.put_chunked("/packages/v2/finish", payload, reference=reference)
    return {"Finished": len(payload)}


def unfinish_package(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    client.put_chunked("/packages/v2/unfinish", payload, reference=reference)
    return {"Unfinished": len(payload)}


def create_package(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    objects = payload if isinstance(payload, list) else [payload]
    ids = client.post_chunked("/packages/v2/", objects, reference=reference)
    return {"Ids": ids}


def change_location(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    client.put_chunked("/packages/v2/location", payload, reference=reference)
    return {"Moved": len(payload)}


def change_item(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    client.put_chunked("/packages/v2/item", payload, reference=reference)
    return {"Changed": len(payload)}
