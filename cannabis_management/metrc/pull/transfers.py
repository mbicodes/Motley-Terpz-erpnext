# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Pull Metrc transfers and stamp manifest data onto ERPNext documents.

The transfer chain costs three calls per transfer, and the Metrc docs warn
explicitly about rate limiting here because the ID is part of the URL:

    GET /transfers/v2/incoming              -> transfer ids
    GET /transfers/v2/{id}/deliveries       -> one call per transfer
    GET /transfers/v2/deliveries/{id}/packages -> one call per delivery

So we only walk the chain for transfers whose LastModified actually advanced,
and we record the transfer id on the matched document so a completed transfer
is never walked twice.
"""

import frappe
from frappe.utils import now_datetime

from cannabis_management.metrc.client import get_client
from cannabis_management.metrc.pull.base import sweep

DIRECTIONS = (
    ("transfers.incoming", "/transfers/v2/incoming", "Incoming"),
    ("transfers.outgoing", "/transfers/v2/outgoing", "Outgoing"),
    ("transfers.rejected", "/transfers/v2/rejected", "Rejected"),
)


def sync_transfers(license_number):
    total = 0
    for endpoint_key, path, direction in DIRECTIONS:
        total += sweep(
            license_number,
            endpoint_key,
            path,
            _make_handler(direction),
        )
    return total


def _make_handler(direction):
    def handler(rows, license_number):
        upsert_transfers(rows, license_number, direction)

    return handler


def upsert_transfers(rows, license_number, direction):
    client = get_client(license_number)

    for transfer in rows:
        transfer_id = transfer.get("Id")
        manifest = transfer.get("ManifestNumber")
        if not transfer_id:
            continue
        try:
            packages = _packages_for_transfer(client, transfer_id)
            _stamp_documents(transfer, direction, packages, license_number)
            _stamp_tags(packages, manifest, transfer_id, direction)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"[metrc] transfer walk failed: {transfer_id}"
            )
    frappe.db.commit()


def _packages_for_transfer(client, transfer_id):
    """Walk transfer -> deliveries -> packages. Returns package label list."""
    labels = []
    for delivery in client.get(f"/transfers/v2/{transfer_id}/deliveries"):
        delivery_id = delivery.get("Id")
        if not delivery_id:
            continue
        for pkg in client.get(f"/transfers/v2/deliveries/{delivery_id}/packages"):
            label = pkg.get("PackageLabel") or pkg.get("Label")
            if label:
                labels.append(label)
    return labels


def _stamp_documents(transfer, direction, labels, license_number):
    """Attach the manifest to whichever ERPNext document carries these tags."""
    if not labels:
        return

    transfer_id = str(transfer.get("Id"))
    manifest = transfer.get("ManifestNumber")

    # Incoming transfers land as Purchase Receipts, outgoing as Delivery Notes.
    doctype = "Purchase Receipt" if direction == "Incoming" else "Delivery Note"
    child = f"tab{doctype} Item"

    names = frappe.db.sql_list(
        f"""
        select distinct parent from `{child}`
        where docstatus = 1 and batch_no in %(labels)s
        """,  # nosemgrep
        {"labels": tuple(labels)},
    )

    for name in names:
        frappe.db.set_value(
            doctype,
            name,
            {
                "custom_metrc_transfer_id": transfer_id,
                "custom_metrc_manifest_number": manifest,
                "custom_metrc_sync_status": "Synced",
            },
            update_modified=False,
        )


def _stamp_tags(labels, manifest, transfer_id, direction):
    """Mark tags that are mid-transfer so stock users can see why they moved."""
    for label in labels:
        if not frappe.db.exists("Metric Tag", label):
            continue
        frappe.db.set_value(
            "Metric Tag",
            label,
            {
                "custom_metrc_status": "In Transit" if direction == "Outgoing" else "Active",
                "custom_metrc_last_synced": now_datetime(),
            },
            update_modified=False,
        )
