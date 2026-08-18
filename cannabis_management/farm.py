# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""TSBC Ranch — Farm / Cultivation server logic.

Extends the existing MTM METRC integration (Metric Tag, Batch) with the
cultivation lifecycle: promote immature plants to tagged individuals, destroy /
record waste, and roll plant counts back onto the Batch. Nothing here changes
the stock/METRC sync behaviour — it only reads/writes the Farm-only fields.

Whitelisted entry points are called directly from the Batch / bulk-list client
scripts (no hooks.py wiring needed for those).
"""

import frappe
from frappe import _
from frappe.utils import flt, today

# Metric Tag status that marks a pre-loaded, unassigned tag in the ~9,000-tag
# pool. The spec said "Empty", but on this site the pool is "Unused" (Empty
# means a used tag drained to zero qty) — confirmed against live data.
UNUSED_TAG_STATUS = "Unused"

FLOWERING = "Flowering"
DESTROYED = "Destroyed"
HARVESTED = "Harvested"

# immature_plant_count may only be hand-edited within this window of Batch
# creation (compliance rule, Section 3).
PLANT_COUNT_EDIT_WINDOW_HOURS = 48


# ---------------------------------------------------------------------------
# Change Growth Phase — Batch → Metric Tag (Section 8)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def change_growth_phase(batch, num_plants, output_warehouse):
    """Promote `num_plants` immature plants from `batch` to individually tagged
    Vegetative plants, pulling unused tags from the pre-loaded pool.

    Replaces manual Starting-Tag/Ending-Tag entry: tags are drawn oldest-first
    from the Metric Tag pool, assigned to the batch, and the batch's immature
    count is decremented.
    """
    num_plants = int(num_plants)
    if num_plants <= 0:
        frappe.throw(_("Number of plants to promote must be greater than zero."))

    batch_doc = frappe.get_doc("Batch", batch)
    remaining = int(batch_doc.get("custom_immature_plant_count") or 0)
    if num_plants > remaining:
        frappe.throw(
            _("Cannot promote {0} plants — only {1} remain immature in this batch.").format(
                num_plants, remaining
            )
        )

    available_tags = frappe.get_all(
        "Metric Tag",
        filters={"status": UNUSED_TAG_STATUS},
        order_by="muid asc",
        limit=num_plants,
        pluck="name",
    )
    if len(available_tags) < num_plants:
        frappe.throw(
            _("Only {0} unused tags available, requested {1}. Resync tags before proceeding.").format(
                len(available_tags), num_plants
            )
        )

    strain_item = batch_doc.get("custom_strain_name") or batch_doc.get("item")

    for tag_name in available_tags:
        tag = frappe.get_doc("Metric Tag", tag_name)
        tag.source_batch = batch_doc.name
        tag.growth_stage = "Vegetative"
        tag.warehouse = output_warehouse
        if strain_item:
            tag.item_code = strain_item
        tag.status = "Active"
        tag.save(ignore_permissions=True)

    batch_doc.custom_immature_plant_count = remaining - num_plants
    batch_doc.flags.ignore_farm_count_lock = True
    _refresh_batch_counts(batch_doc, save=False)
    batch_doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "promoted": num_plants,
        "immature_remaining": batch_doc.custom_immature_plant_count,
        "tags": available_tags,
    }


# ---------------------------------------------------------------------------
# Destroy & Record Waste (Section 9)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def destroy_plants(tag_names, disposal_method, waste_weight=0, waste_uom=None,
                   waste_reason=None, logged_by=None, note=None):
    """Destructive: set each tag's growth_stage = Destroyed, stamp destroyed_by,
    and file a Plant Waste Log per tag."""
    tag_names = frappe.parse_json(tag_names) if isinstance(tag_names, str) else tag_names
    if not tag_names:
        frappe.throw(_("Select at least one plant to destroy."))

    affected_batches = set()
    for name in tag_names:
        tag = frappe.get_doc("Metric Tag", name)
        tag.growth_stage = DESTROYED
        if logged_by:
            tag.destroyed_by = logged_by
        tag.save(ignore_permissions=True)
        if tag.source_batch:
            affected_batches.add(tag.source_batch)

        _insert_waste_log(name, disposal_method, waste_weight, waste_uom,
                          waste_reason, logged_by, note)

    for batch in affected_batches:
        _refresh_batch_counts(frappe.get_doc("Batch", batch))
    frappe.db.commit()
    return {"destroyed": len(tag_names)}


@frappe.whitelist()
def record_waste(tag_names, disposal_method, waste_weight=0, waste_uom=None,
                 waste_reason=None, logged_by=None, note=None):
    """Non-destructive: file a Plant Waste Log per tag WITHOUT changing
    growth_stage (the plant stays alive)."""
    tag_names = frappe.parse_json(tag_names) if isinstance(tag_names, str) else tag_names
    if not tag_names:
        frappe.throw(_("Select at least one plant to record waste for."))

    for name in tag_names:
        _insert_waste_log(name, disposal_method, waste_weight, waste_uom,
                          waste_reason, logged_by, note)
    frappe.db.commit()
    return {"logged": len(tag_names)}


def _insert_waste_log(metric_tag, disposal_method, waste_weight, waste_uom,
                      waste_reason, logged_by, note):
    frappe.get_doc({
        "doctype": "Plant Waste Log",
        "metric_tag": metric_tag,
        "waste_date": today(),
        "disposal_method": disposal_method,
        "waste_weight": flt(waste_weight),
        "waste_uom": waste_uom,
        "waste_reason": waste_reason,
        "logged_by": logged_by,
        "note": note,
    }).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Batch rollup counts + 48-hour edit lock (Sections 3 & the is_active rule)
# ---------------------------------------------------------------------------


def _refresh_batch_counts(batch_doc, save=True):
    """Recompute tagged/destroyed counts and is_active from the tag population."""
    name = batch_doc.name
    tagged = frappe.db.count("Metric Tag", {"source_batch": name})
    destroyed = frappe.db.count("Metric Tag", {"source_batch": name, "growth_stage": DESTROYED})
    harvested = frappe.db.count("Metric Tag", {"source_batch": name, "growth_stage": HARVESTED})

    batch_doc.custom_tagged_count = tagged
    batch_doc.custom_destroyed_count = destroyed
    # Inactive once nothing immature remains AND every tagged plant is gone
    # (destroyed or harvested).
    immature = int(batch_doc.get("custom_immature_plant_count") or 0)
    batch_doc.custom_is_active = 0 if (immature == 0 and tagged > 0 and (destroyed + harvested) >= tagged) else 1

    if save:
        batch_doc.flags.ignore_farm_count_lock = True
        batch_doc.save(ignore_permissions=True)


def batch_validate(doc, method=None):
    """doc_events validate hook for Batch.

    1. Set the Dynamic Link target doctype from Source Type.
    2. Enforce the 48-hour edit lock on immature_plant_count.
    """
    # 1. Dynamic Link companion
    source_type = doc.get("custom_source_type")
    if source_type == "Mother Plant":
        doc.custom_source_reference_type = "Metric Tag"
    elif source_type == "Package":
        doc.custom_source_reference_type = "Batch"

    # 2. 48-hour lock — only applies to edits of an existing batch.
    if doc.is_new() or doc.flags.get("ignore_farm_count_lock"):
        return

    # Read the persisted value directly: validate() runs before the row is
    # updated, so the DB still holds the pre-edit count.
    old_count = frappe.db.get_value("Batch", doc.name, "custom_immature_plant_count")
    new_count = doc.get("custom_immature_plant_count")
    if old_count == new_count:
        return

    created = frappe.utils.get_datetime(doc.creation)
    hours = frappe.utils.time_diff_in_hours(frappe.utils.now_datetime(), created)
    if hours > PLANT_COUNT_EDIT_WINDOW_HOURS:
        frappe.throw(
            _("Immature Plant Count can only be adjusted within {0} hours of batch creation "
              "(this batch is {1:.0f} hours old). Use Change Growth Phase / Destroy to move plants.").format(
                PLANT_COUNT_EDIT_WINDOW_HOURS, hours
            )
        )


# ---------------------------------------------------------------------------
# Individual KPI — Plant Loss Rate (Section 12)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_plant_loss_rate(employee):
    """Plant Loss Rate for an employee = destroyed / total tagged plants across
    the batches that employee is responsible for.

    'Batches for employee' is derived from Farm Employee KPI Profile responsibility,
    falling back to batches whose tags this employee destroyed. Reported as a
    percentage.
    """
    batches = _batches_for_employee(employee)
    if not batches:
        # Fall back to tags this employee personally destroyed.
        destroyed = frappe.db.count("Metric Tag", {"destroyed_by": employee, "growth_stage": DESTROYED})
        total = frappe.db.count("Metric Tag", {"destroyed_by": employee}) or destroyed
        return round((destroyed / total * 100), 2) if total else 0.0

    destroyed = frappe.db.count("Metric Tag", {"growth_stage": DESTROYED, "source_batch": ["in", batches]})
    total = frappe.db.count("Metric Tag", {"source_batch": ["in", batches]})
    return round((destroyed / total * 100), 2) if total else 0.0


def _batches_for_employee(employee):
    """Batches an employee is accountable for. Best-effort: any batch whose
    tags were destroyed by them (extend here to read KPI responsibilities)."""
    rows = frappe.get_all(
        "Metric Tag",
        filters={"destroyed_by": employee},
        distinct=True,
        pluck="source_batch",
    )
    return [b for b in rows if b]
