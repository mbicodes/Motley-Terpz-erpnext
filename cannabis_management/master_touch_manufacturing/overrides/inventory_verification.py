"""
Inventory Verification override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Inventory Verification"]["on_update"]

Responsibilities:
- Validate that verified_by ≠ the wash/press tech who created the source batch.
- When approved_for_inventory = 1:
    * Set all related Batch records to batch_status = "Released".
    * Stamp qc_approved_by and qc_approved_date on each Batch.
    * Update Production Batch Group status to "Inventory Verification".
    * Auto-create a Quality Inspection record for each batch if none exists.
"""

import frappe
from frappe.utils import today, now_datetime


def on_update(doc, method=None):
    _validate_verified_by(doc)
    if doc.approved_for_inventory:
        _release_batches(doc)
        _update_pbg_status(doc)


# ── helpers ────────────────────────────────────────────────────────────────────

def _validate_verified_by(doc):
    """verified_by must NOT be the tech who ran the source batch."""
    if not doc.verified_by:
        return

    source_tech = None
    if doc.verification_type == "Bubble Hash" and doc.get("source_batch_ref_wash"):
        source_tech = frappe.db.get_value("Wash Batch", doc.source_batch_ref_wash, "wash_tech")
    elif doc.verification_type == "Rosin" and doc.get("source_batch_ref_press"):
        source_tech = frappe.db.get_value("Press Batch", doc.source_batch_ref_press, "press_tech")

    if source_tech and source_tech == doc.verified_by:
        frappe.throw(
            f"Verified By ({doc.verified_by}) cannot be the same person who ran the "
            f"source {doc.verification_type} batch. A second person must verify.",
            title="Verification Conflict"
        )


def _release_batches(doc):
    """
    Set batch_status = 'Released' on all Batch records linked to this IV.
    Stamp qc_approved_by / qc_approved_date.
    Auto-create Quality Inspection if none exists.
    """
    approved_by = doc.approved_by or frappe.session.user
    approved_date = today()

    for row in doc.get("metrc_packages") or []:
        batch_name = row.get("erpnext_batch")
        if not batch_name:
            continue
        if not frappe.db.exists("Batch", batch_name):
            continue

        # Update batch status + QC stamp
        frappe.db.set_value(
            "Batch", batch_name,
            {
                "custom_batch_status": "Released",
                "custom_qc_approved_by": approved_by,
                "custom_qc_approved_date": approved_date,
            }
        )

        # Auto-create Quality Inspection if not already linked
        try:
            _ensure_quality_inspection(doc, batch_name, row)
        except Exception:
            pass  # QI creation is non-blocking


def _ensure_quality_inspection(doc, batch_name, row):
    """Create a draft QI for the batch if none exists."""
    # Check if QI already exists for this batch
    existing = frappe.db.get_value(
        "Quality Inspection", {"reference_name": batch_name, "docstatus": ["!=", 2]}, "name"
    )
    if existing:
        return

    # Pick template based on type
    template_name = (
        "Bubble Hash QI" if doc.verification_type == "Bubble Hash" else "Rosin QI"
    )
    if not frappe.db.exists("Quality Inspection Template", template_name):
        return  # Template not created yet — skip silently

    batch_doc = frappe.get_doc("Batch", batch_name)
    item_code = batch_doc.item

    qi = frappe.new_doc("Quality Inspection")
    qi.inspection_type = "Incoming"
    qi.reference_type = "Batch"
    qi.reference_name = batch_name
    qi.item_code = item_code
    qi.batch_no = batch_name
    qi.quality_inspection_template = template_name
    # inspected_by links to User — convert Employee ID to user if needed
    verifier = doc.verified_by or frappe.session.user
    if verifier and verifier.startswith("HR-EMP-"):
        user_id = frappe.db.get_value("Employee", verifier, "user_id") or frappe.session.user
    else:
        user_id = verifier
    qi.inspected_by = user_id
    qi.report_date = today()

    # Pull readings from template (child table field: item_quality_inspection_parameter)
    template = frappe.get_doc("Quality Inspection Template", template_name)
    for reading in template.get("item_quality_inspection_parameter") or []:
        qi.append("readings", {
            "specification": reading.specification,
            "value": reading.value,
            "status": "Accepted",
            "min_value": reading.min_value,
            "max_value": reading.max_value,
            "numeric": reading.numeric,
        })

    qi.insert(ignore_permissions=True)


def _update_pbg_status(doc):
    """Move PBG to 'Inventory Verification' status when IV is approved."""
    pbg = doc.get("production_batch_group")
    if not pbg:
        return
    current = frappe.db.get_value("Production Batch Group", pbg, "status")
    # Only advance forward — don't overwrite a later status
    if current in ("Open", "In Wash", "In Press"):
        frappe.db.set_value(
            "Production Batch Group", pbg, "status", "Inventory Verification"
        )
