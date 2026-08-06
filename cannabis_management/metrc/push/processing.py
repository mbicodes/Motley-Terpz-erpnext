# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Work Order / Manufacture Stock Entry -> Metrc processing job.

Metrc's processing lifecycle:

    POST /processing/v2/start          job created, input packages consumed
    POST /processing/v2/adjust         correct inputs mid-job
    POST /processing/v2/createpackages outputs created; can close the job
    PUT  /processing/v2/finish         close the job

createpackages accepts FinishProcessingJob plus waste quantities, so the finish
happens in the same call as the outputs. That is one fewer request against the
rate limit and it is atomic, which matters because a half-closed job in Metrc
needs manual intervention.
"""

import frappe
from frappe.utils import flt

from cannabis_management.metrc import config, mapping
from cannabis_management.metrc.pull.masterdata import claim_tag, enumeration_names
from cannabis_management.metrc.push.outbox import enqueue

DEFAULT_JOB_TYPE = "Infusing"


def _job_type(doc):
    """Validate against Metrc's live job types rather than hardcoding."""
    requested = doc.get("custom_metrc_job_type") or DEFAULT_JOB_TYPE
    valid = enumeration_names("job_types")
    if valid and requested not in valid:
        frappe.throw(
            f"METRC Processing Job Type {frappe.bold(requested)} is not valid for this facility. "
            f"Valid types: {', '.join(valid)}"
        )
    return requested


def _row_tag(row, fieldnames=("batch_no",)):
    for fieldname in fieldnames:
        if row.get(fieldname):
            tag = frappe.db.get_value("Batch", row.get(fieldname), "custom_metrc_tag")
            if tag:
                return tag
    for fieldname in ("muid", "metric_tag"):
        if row.get(fieldname):
            return row.get(fieldname)
    return None


# ---------------------------------------------------------------------------
# Work Order -> start job
# ---------------------------------------------------------------------------


def on_work_order_submit(doc, method=None):
    if not config.is_enabled():
        return

    license_number = config.license_for_doc(doc) or config.license_for_warehouse(
        doc.get("wip_warehouse") or doc.get("fg_warehouse")
    )
    if not license_number:
        return

    packages = []
    for row in doc.get("required_items") or []:
        if not mapping.is_tracked_item(row.item_code):
            continue
        tag = _row_tag(row)
        if not tag:
            continue
        packages.append(
            {
                "Label": tag,
                "Quantity": flt(row.get("required_qty")),
                "UnitOfMeasure": mapping.to_metrc_uom(
                    frappe.db.get_value("Item", row.item_code, "stock_uom")
                ),
            }
        )

    if not packages:
        doc.db_set("custom_metrc_sync_status", "Not Tracked", update_modified=False)
        return

    payload = {
        "JobName": doc.name,
        "JobType": _job_type(doc),
        "CountUnitOfMeasure": "Each",
        "VolumeUnitOfMeasure": "Fluid Ounces",
        "WeightUnitOfMeasure": "Grams",
        "Packages": packages,
        "StartDate": f"{doc.get('planned_start_date') or frappe.utils.nowdate()}T00:00:00Z",
    }

    enqueue(
        operation="processing.start",
        license_number=license_number,
        payload=payload,
        reference_doctype="Work Order",
        reference_name=doc.name,
    )
    doc.db_set("custom_metrc_sync_status", "Queued", update_modified=False)


# ---------------------------------------------------------------------------
# Manufacture Stock Entry -> create output packages and close the job
# ---------------------------------------------------------------------------


def on_manufacture_stock_entry_submit(doc, method=None):
    if not config.is_enabled():
        return
    if doc.get("type") not in ("Manufacturing", "Premix", "Packing"):
        return

    license_number = config.license_for_doc(doc)
    if not license_number:
        return

    job_name = _linked_job_name(doc)
    if not job_name:
        return

    outputs = []
    for row in doc.get("manufacture_finished_goods") or []:
        if not mapping.is_tracked_item(row.item_code):
            continue
        outputs.append(
            {
                "JobName": job_name,
                "Tag": claim_tag(license_number, "Package"),
                "Location": None,
                "Sublocation": None,
                "Item": mapping.metrc_item_name(row.item_code),
                "Quantity": flt(row.get("qty")),
                "UnitOfMeasure": mapping.to_metrc_uom(
                    row.get("uom") or frappe.db.get_value("Item", row.item_code, "stock_uom")
                ),
                "IsFinishedGood": True,
                "PatientLicenseNumber": None,
                "Note": None,
                "ProductionBatchNumber": doc.name,
                "FinishProcessingJob": True,
                "FinishDate": str(doc.get("date") or frappe.utils.nowdate()),
                "WasteCountQuantity": None,
                "WasteCountUnitOfMeasureName": None,
                "WasteVolumeQuantity": None,
                "WasteVolumeUnitOfMeasureName": None,
                "WasteWeightQuantity": flt(doc.get("diff_qty_sum")) or None,
                "WasteWeightUnitOfMeasureName": "Grams" if doc.get("diff_qty_sum") else None,
                "FinishNote": None,
                "PackageDate": str(doc.get("date") or frappe.utils.nowdate()),
                "ExpirationDate": None,
                "SellByDate": None,
                "UseByDate": None,
            }
        )

    if not outputs:
        doc.db_set("custom_metrc_sync_status", "Not Tracked", update_modified=False)
        return

    enqueue(
        operation="processing.createpackages",
        license_number=license_number,
        payload=outputs,
        reference_doctype=doc.doctype,
        reference_name=doc.name,
    )
    doc.db_set("custom_metrc_sync_status", "Queued", update_modified=False)


def _linked_job_name(doc):
    """Metrc keys processing jobs by name, and we use the Work Order name."""
    for fieldname in ("work_order", "custom_work_order"):
        if doc.get(fieldname):
            return doc.get(fieldname)
    if doc.get("material_issue_ref"):
        return frappe.db.get_value("Stock Entry", doc.material_issue_ref, "work_order")
    return None


# ------------------------------------------------------------------ handlers


def start_job(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    objects = payload if isinstance(payload, list) else [payload]
    ids = client.post_chunked("/processing/v2/start", objects, reference=reference)
    return {"Ids": ids}


def create_packages(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    objects = payload if isinstance(payload, list) else [payload]
    ids = client.post_chunked("/processing/v2/createpackages", objects, reference=reference)
    return {"Ids": ids}


def finish_job(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    objects = payload if isinstance(payload, list) else [payload]
    return client.put("/processing/v2/finish", objects, reference=reference)
