# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Delivery Note -> Metrc outgoing transfer.

An API asymmetry worth knowing: there is no plain "create outgoing transfer"
endpoint. Metrc exposes POST /transfers/v2/external/incoming (a shipment plan
recorded by the receiver) and POST /transfers/v2/templates/outgoing (a reusable
template a dispatcher promotes to a real manifest in the Metrc UI).

We create the template. That is the closest the API gets to originating an
outgoing transfer, and it puts a named, fully-populated manifest in front of
dispatch instead of asking them to retype it. The manifest number comes back on
the pull side once the transfer is actually created.
"""

import frappe
from frappe.utils import flt, get_datetime

from cannabis_management.metrc import config, mapping
from cannabis_management.metrc.push.outbox import enqueue

DEFAULT_TRANSFER_TYPE = "Transfer"


def _recipient_license(doc):
    return frappe.db.get_value("Customer", doc.customer, "custom_license_number")


def _iso(value):
    if not value:
        return None
    return get_datetime(value).strftime("%Y-%m-%dT%H:%M:%S.000")


def build_template(doc, license_number):
    """Delivery Note -> transfer template payload."""
    packages = []
    for row in doc.get("items") or []:
        if not mapping.is_tracked_item(row.item_code):
            continue
        tag = _row_tag(row)
        if not tag:
            frappe.throw(
                f"Row {row.idx} ({frappe.bold(row.item_code)}) is METRC-tracked but has no package "
                "tag. Set a Batch carrying a METRC Tag before submitting."
            )
        packages.append(
            {
                "PackageLabel": tag,
                "WholesalePrice": flt(row.amount) or None,
            }
        )

    if not packages:
        return None

    recipient = _recipient_license(doc)
    if not recipient:
        frappe.throw(
            f"Customer {frappe.bold(doc.customer)} has no License Number. "
            "Metrc requires the recipient licence on every transfer."
        )

    departure = _iso(f"{doc.posting_date} {doc.get('posting_time') or '00:00:00'}")
    arrival = _iso(f"{doc.get('lr_date') or doc.posting_date} 23:59:00")

    destination = {
        "RecipientLicenseNumber": recipient,
        "InvoiceNumber": doc.name,
        "TransferTypeName": doc.get("custom_metrc_transfer_type") or DEFAULT_TRANSFER_TYPE,
        "PlannedRoute": doc.get("custom_planned_route") or "See dispatch.",
        "EstimatedDepartureDateTime": departure,
        "EstimatedArrivalDateTime": arrival,
        "PaymentTermDays": _payment_term_days(doc),
        "Transporters": _transporters(doc, departure, arrival),
        "Packages": packages,
    }

    return {
        "Name": doc.name,
        "TransporterFacilityLicenseNumber": license_number,
        "DriverOccupationalLicenseNumber": doc.get("driver") or None,
        "DriverName": doc.get("driver_name") or None,
        "DriverLicenseNumber": doc.get("license_plate") or None,
        "PhoneNumberForQuestions": doc.get("contact_mobile") or None,
        "VehicleMake": doc.get("vehicle_no") or None,
        "VehicleModel": None,
        "VehicleLicensePlateNumber": doc.get("license_plate") or None,
        "VehicleRegistrationNumber": None,
        "Destinations": [destination],
    }


def _payment_term_days(doc):
    terms = frappe.db.get_value("Delivery Note", doc.name, "payment_terms_template")
    if not terms:
        return None
    days = frappe.db.get_value(
        "Payment Terms Template Detail", {"parent": terms}, "credit_days"
    )
    return int(days) if days else None


def _transporters(doc, departure, arrival):
    """A transporter block is required even for self-distribution."""
    return [
        {
            "TransporterFacilityLicenseNumber": config.license_for_doc(doc),
            "DriverOccupationalLicenseNumber": doc.get("driver") or "N/A",
            "DriverName": doc.get("driver_name") or "N/A",
            "DriverLicenseNumber": doc.get("license_plate") or "N/A",
            "DriverLayoverLeg": None,
            "PhoneNumberForQuestions": doc.get("contact_mobile") or None,
            "VehicleMake": doc.get("vehicle_no") or "N/A",
            "VehicleModel": "N/A",
            "VehicleLicensePlateNumber": doc.get("license_plate") or "N/A",
            "VehicleRegistrationNumber": None,
            "IsLayover": False,
            "EstimatedDepartureDateTime": departure,
            "EstimatedArrivalDateTime": arrival,
            "TransporterDetails": None,
        }
    ]


def _row_tag(row):
    if row.get("batch_no"):
        tag = frappe.db.get_value("Batch", row.batch_no, "custom_metrc_tag")
        if tag:
            return tag
    for fieldname in ("muid", "metric_tag"):
        if row.get(fieldname):
            return row.get(fieldname)
    return None


# --------------------------------------------------------------------- hooks


def on_submit(doc, method=None):
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
    if not facility.sync_transfers:
        return

    payload = build_template(doc, license_number)
    if not payload:
        doc.db_set("custom_metrc_sync_status", "Not Tracked", update_modified=False)
        return

    enqueue(
        operation="transfers.template.create",
        license_number=license_number,
        payload=payload,
        reference_doctype="Delivery Note",
        reference_name=doc.name,
    )
    doc.db_set(
        {"custom_metrc_sync_status": "Queued", "custom_metrc_license_number": license_number},
        update_modified=False,
    )


# ------------------------------------------------------------------ handlers


def create_template(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    objects = payload if isinstance(payload, list) else [payload]
    ids = client.post_chunked("/transfers/v2/templates/outgoing", objects, reference=reference)
    return {"Ids": ids}


def update_template(client, payload, outbox_doc):
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    objects = payload if isinstance(payload, list) else [payload]
    return client.put("/transfers/v2/templates/outgoing", objects, reference=reference)


def create_incoming(client, payload, outbox_doc):
    """External incoming shipment plan, used when we are the receiver."""
    reference = (outbox_doc.reference_doctype, outbox_doc.reference_name)
    objects = payload if isinstance(payload, list) else [payload]
    ids = client.post_chunked("/transfers/v2/external/incoming", objects, reference=reference)
    return {"Ids": ids}
