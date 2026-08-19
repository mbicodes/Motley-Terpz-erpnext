# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Sales Invoice -> Metrc sales receipt.

CRITICAL, and the most common cause of rejected receipts: SalesDateTime must be
the facility's LOCAL wall-clock time with no timezone suffix. Metrc reads it as
facility-local. Sending UTC shifts every California receipt eight hours and
pushes transactions into the wrong reporting day. Every other datetime field in
the API is the opposite - ISO 8601 with offset.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import flt, get_datetime, get_system_timezone

from cannabis_management.metrc import config, mapping
from cannabis_management.metrc.push.outbox import enqueue


def facility_local_naive(value, license_number):
    """Site-timezone datetime -> facility wall clock, tzinfo stripped."""
    dt = get_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(get_system_timezone()))
    local = dt.astimezone(ZoneInfo(config.facility_timezone(license_number)))
    return local.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S.000")


def tag_for_row(row):
    """Metrc package label backing an item row.

    Batch is the ERPNext side of a package, so batch_no -> custom_metrc_tag is
    the primary path. The Muid inventory dimension is the fallback for rows
    that carry a tag without a batch.
    """
    if row.get("batch_no"):
        tag = frappe.db.get_value("Batch", row.batch_no, "custom_metrc_tag")
        if tag:
            return tag
    for fieldname in ("muid", "metric_tag"):
        if row.get(fieldname):
            return row.get(fieldname)
    return None


def customer_type(invoice):
    """Metrc SalesCustomerType. Consumer is correct for adult-use retail;
    Patient/Caregiver require licence numbers we do not collect today."""
    licence = frappe.db.get_value("Customer", invoice.customer, "custom_license_number")
    return "Patient" if licence and licence.upper().startswith("PTN") else "Consumer"


def build_receipt(invoice, license_number):
    transactions = []
    skipped = []

    for row in invoice.items:
        if not mapping.is_tracked_item(row.item_code):
            skipped.append(row.item_code)
            continue

        tag = tag_for_row(row)
        if not tag:
            frappe.throw(
                f"Row {row.idx} ({frappe.bold(row.item_code)}) is METRC-tracked but has no package tag. "
                "Set a Batch carrying a METRC Tag before submitting."
            )

        transactions.append(
            {
                "PackageLabel": tag,
                "Quantity": flt(row.qty),
                "UnitOfMeasure": mapping.to_metrc_uom(row.uom or row.stock_uom),
                "TotalAmount": flt(row.amount),
                "UnitThcPercent": None,
                "UnitThcContent": None,
                "UnitThcContentUnitOfMeasure": None,
                "UnitWeight": None,
                "UnitWeightUnitOfMeasure": None,
                "InvoiceNumber": invoice.name,
                "Price": flt(row.rate),
                "ExciseTax": None,
                "CityTax": None,
                "CountyTax": None,
                "MunicipalTax": None,
                "DiscountAmount": flt(row.get("discount_amount") or 0) or None,
                "SubTotal": flt(row.get("net_amount") or row.amount),
                "SalesTax": None,
                "QrCodes": None,
            }
        )

    if not transactions:
        return None

    posting = f"{invoice.posting_date} {invoice.get('posting_time') or '00:00:00'}"
    return {
        "SalesDateTime": facility_local_naive(posting, license_number),
        "ExternalReceiptNumber": invoice.name,
        "SalesCustomerType": customer_type(invoice),
        "PatientLicenseNumber": None,
        "CaregiverLicenseNumber": None,
        "IdentificationMethod": None,
        "PatientRegistrationLocationId": None,
        "Transactions": transactions,
    }


# --------------------------------------------------------------------- hooks


def on_submit(doc, method=None):
    """Enqueue a Metrc receipt. Runs inside the submit transaction."""
    if not config.is_enabled():
        return
    if doc.get("custom_metrc_sync_status") in ("Synced", "Not Tracked"):
        return

    license_number = config.license_for_doc(doc)
    if not license_number:
        return

    try:
        facility = config.get_facility(license_number)
    except Exception:
        return
    if not facility.sync_sales:
        return

    payload = build_receipt(doc, license_number)
    if not payload:
        doc.db_set("custom_metrc_sync_status", "Not Tracked", update_modified=False)
        return

    enqueue(
        operation="sales.receipt.create",
        license_number=license_number,
        payload=payload,
        reference_doctype="Sales Invoice",
        reference_name=doc.name,
    )
    doc.db_set(
        {"custom_metrc_sync_status": "Queued", "custom_metrc_license_number": license_number},
        update_modified=False,
    )


def on_cancel(doc, method=None):
    """A cancelled invoice must not stay reported. Metrc deletes receipts by
    their own Id, so we can only act if the push already succeeded."""
    if not config.is_enabled():
        return
    receipt_id = doc.get("custom_metrc_receipt_id")
    if not receipt_id:
        doc.db_set("custom_metrc_sync_status", None, update_modified=False)
        return

    license_number = doc.get("custom_metrc_license_number") or config.license_for_doc(doc)
    if not license_number:
        return

    enqueue(
        operation="sales.receipt.delete",
        license_number=license_number,
        payload={"Id": receipt_id},
        reference_doctype="Sales Invoice",
        reference_name=doc.name,
        discriminator="cancel",
    )


# ------------------------------------------------------------------ handlers


def create_receipt(client, payload, outbox_doc):
    """Create a receipt, verifying first that it does not already exist.

    Metrc has no idempotency keys. If a POST times out after Metrc committed,
    we cannot tell from the response - so we look the receipt up by our own
    ExternalReceiptNumber before creating. Without this, one ambiguous timeout
    means a duplicate receipt in a state system.
    """
    external = payload.get("ExternalReceiptNumber")
    if external:
        existing = _find_by_external(client, external)
        if existing:
            return {"Ids": [existing], "AlreadyExisted": True}

    return client.post(
        "/sales/v2/receipts",
        [payload],
        reference=(outbox_doc.reference_doctype, outbox_doc.reference_name),
    )


def _find_by_external(client, external):
    try:
        rows = client.get(f"/sales/v2/receipts/external/{external}")
    except Exception:
        # 404 is the normal "not there yet" path.
        return None
    if not rows:
        return None
    row = rows[0] if isinstance(rows, list) else rows
    return row.get("Id") if isinstance(row, dict) else None


def update_receipt(client, payload, outbox_doc):
    return client.put(
        "/sales/v2/receipts",
        [payload],
        reference=(outbox_doc.reference_doctype, outbox_doc.reference_name),
    )


def delete_receipt(client, payload, outbox_doc):
    receipt_id = payload.get("Id")
    return client.delete(
        f"/sales/v2/receipts/{receipt_id}",
        reference=(outbox_doc.reference_doctype, outbox_doc.reference_name),
    )
