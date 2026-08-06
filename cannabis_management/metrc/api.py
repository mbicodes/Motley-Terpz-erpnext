# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Whitelisted endpoints backing the Metrc UI.

Everything a button in the desk calls lives here, so the permission surface of
the integration is one file rather than scattered across the sync modules.
"""

import frappe
from frappe.utils import now_datetime

from cannabis_management.metrc import config
from cannabis_management.metrc.client import get_client


def _guard():
    frappe.only_for(("System Manager", "Stock Manager"))


@frappe.whitelist()
def test_connection(license_number=None):
    """Verify credentials and report which facilities the keys can reach.

    Deliberately calls GET /facilities/v2/ - it is read-only, needs no licence
    parameter, and failing it tells you immediately whether the problem is the
    keys or the environment.
    """
    _guard()

    if not config.is_enabled():
        return {"ok": False, "message": "Metrc integration is disabled. Tick <b>Enabled</b> first."}

    licenses = [license_number] if license_number else config.configured_licenses()
    if not licenses:
        return {"ok": False, "message": "No active facilities configured."}

    lic = licenses[0]
    try:
        client = get_client(lic)
        rows = client.get("/facilities/v2/")
    except Exception as e:
        return {
            "ok": False,
            "environment": config.get_settings().environment,
            "message": str(e)[:800],
        }

    facilities = []
    for row in rows:
        licence = row.get("License") or {}
        facilities.append(
            {
                "license_number": licence.get("Number"),
                "license_type": licence.get("LicenseType"),
                "name": row.get("DisplayName") or row.get("Name"),
                "mapped_warehouse": config.warehouse_for_license(licence.get("Number")),
            }
        )

    configured = set(config.configured_licenses())
    reachable = {f["license_number"] for f in facilities}
    missing = sorted(configured - reachable)

    return {
        "ok": True,
        "environment": config.get_settings().environment,
        "base_url": config.base_url(),
        "facility_count": len(facilities),
        "facilities": facilities,
        "unreachable_configured": missing,
        "message": f"Connected. {len(facilities)} facility(ies) reachable.",
    }


@frappe.whitelist()
def import_facilities():
    """Populate the Facilities table from GET /facilities/v2/.

    Saves retyping licence numbers, which is where typos become 401s.
    """
    _guard()

    settings = config.get_settings()
    if not settings.facilities:
        frappe.throw(
            "Add one facility row with a licence number and user key first, "
            "so the integration has a key to authenticate with."
        )

    seed = settings.facilities[0].license_number
    rows = get_client(seed).get("/facilities/v2/")
    existing = {row.license_number for row in settings.facilities}
    added = 0

    for facility in rows:
        licence = (facility.get("License") or {}).get("Number")
        if not licence or licence in existing:
            continue
        settings.append(
            "facilities",
            {
                "license_number": licence,
                "facility_name": facility.get("DisplayName") or facility.get("Name"),
                "warehouse": config.warehouse_for_license(licence),
                "is_active": 0,  # opt in explicitly; each needs its own user key
                "facility_timezone": "America/Los_Angeles",
            },
        )
        added += 1

    if added:
        settings.flags.ignore_permissions = True
        settings.save(ignore_permissions=True)

    return {
        "added": added,
        "message": (
            f"Added {added} facility(ies), all inactive. Set a user key and tick Active "
            "on each one you want to sync."
        ),
    }


@frappe.whitelist()
def sync_now(license_number=None):
    """Run a full sync in the background so the request does not block."""
    _guard()
    frappe.enqueue(
        "cannabis_management.metrc.pull.sync_all",
        queue="long",
        timeout=3600,
        license_number=license_number,
    )
    return {"message": "Sync queued. Watch Metrc Sync State and Metrc API Log for progress."}


@frappe.whitelist()
def drain_outbox():
    """Process the outbox immediately rather than waiting for the scheduler."""
    _guard()
    frappe.enqueue(
        "cannabis_management.metrc.push.outbox.process_outbox", queue="long", timeout=1800
    )
    return {"message": "Outbox worker queued."}


@frappe.whitelist()
def sync_status():
    """Everything the Metrc Settings dashboard shows, in one call."""
    _guard()

    from cannabis_management.metrc.reconcile import variance_summary

    cursors = frappe.get_all(
        "Metrc Sync State",
        fields=[
            "name",
            "license_number",
            "endpoint_key",
            "cursor_last_modified",
            "last_status",
            "records_synced",
            "consecutive_failures",
        ],
        order_by="license_number asc, endpoint_key asc",
    )
    outbox = {
        status: frappe.db.count("Metrc Outbox", {"status": status})
        for status in ("Queued", "In Progress", "Success", "Failed", "Parked")
    }
    recent_errors = frappe.get_all(
        "Metrc API Log",
        filters={"response_status": [">=", 400]},
        fields=["timestamp", "method", "endpoint", "response_status", "error"],
        order_by="timestamp desc",
        limit=10,
    )

    return {
        "enabled": config.is_enabled(),
        "push_enabled": config.push_enabled(),
        "dry_run": config.is_dry_run(),
        "environment": frappe.db.get_single_value("Metrc Settings", "environment"),
        "cursors": cursors,
        "outbox": outbox,
        "recent_errors": recent_errors,
        "variance": variance_summary(),
        "as_of": now_datetime(),
    }


@frappe.whitelist()
def resync_document(doctype, name):
    """Re-run the push hook for one document, from a button on its form."""
    _guard()

    handlers = {
        "Sales Invoice": "cannabis_management.metrc.push.sales.on_submit",
        "Delivery Note": "cannabis_management.metrc.push.transfers.on_submit",
        "Stock Entry": "cannabis_management.metrc.push.packages.on_stock_entry_submit",
        "Stock Reconciliation": (
            "cannabis_management.metrc.push.packages.on_stock_reconciliation_submit"
        ),
        "Work Order": "cannabis_management.metrc.push.processing.on_work_order_submit",
    }
    path = handlers.get(doctype)
    if not path:
        frappe.throw(f"{doctype} has no Metrc push handler.")

    doc = frappe.get_doc(doctype, name)
    # Clear the guard so the hook does not short-circuit on a prior status.
    doc.db_set("custom_metrc_sync_status", None, update_modified=False)
    frappe.get_attr(path)(doc)
    frappe.db.commit()

    from cannabis_management.metrc.push.outbox import process_outbox

    process_outbox()

    return frappe.db.get_value(
        doctype, name, ["custom_metrc_sync_status", "custom_metrc_message"], as_dict=True
    )


@frappe.whitelist()
def tag_pool_summary():
    """Unused / active / empty counts, for the workspace."""
    _guard()
    return {
        "unused_package": frappe.db.count(
            "Metric Tag", {"status": "Unused", "last_transaction_type": "Metrc Package Tag"}
        ),
        "unused_plant": frappe.db.count(
            "Metric Tag", {"status": "Unused", "last_transaction_type": "Metrc Plant Tag"}
        ),
        "active": frappe.db.count("Metric Tag", {"status": "Active"}),
        "empty": frappe.db.count("Metric Tag", {"status": "Empty"}),
    }
