# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Scheduled pull orchestration.

Three cadences, chosen to balance rate limit against compliance freshness:

  * master data  - hourly. Items, strains, facilities, tag pool, enumerations.
  * inventory    - every 30 min. Packages and transfers, the compliance path.
  * operations   - daily. Sales receipts and lab tests.

Every facility is filtered by its own sync_* flags, because polling endpoints a
licence type cannot use (plants at a retailer, sales at a cultivator) just
burns rate limit and logs 401s.
"""

import frappe

from cannabis_management.metrc import config
from cannabis_management.metrc.pull import labtests, masterdata, packages, sales, transfers

ALERT_AFTER_FAILURES = 3


def _run(fn, license_number, label):
    """Run one sync, isolating failures to a single (facility, endpoint)."""
    try:
        return fn(license_number) or 0
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"[metrc] {label} failed for {license_number}")
        return 0


def sync_master_data():
    """Hourly."""
    if not config.is_enabled():
        return
    facilities = config.active_facilities()
    if not facilities:
        return

    # Facilities and enumerations are licence-agnostic; one call each is enough.
    first = facilities[0].license_number
    _run(masterdata.sync_facilities, first, "facilities")
    _run(masterdata.refresh_enumerations, first, "enumerations")

    for facility in facilities:
        lic = facility.license_number
        _run(masterdata.sync_items, lic, "items")
        _run(masterdata.sync_strains, lic, "strains")
        _run(masterdata.sync_available_tags, lic, "tags")


def sync_inventory():
    """Every 30 minutes - the compliance-critical path."""
    if not config.is_enabled():
        return
    for facility in config.active_facilities(feature="sync_packages"):
        _run(packages.sync_packages, facility.license_number, "packages")
    for facility in config.active_facilities(feature="sync_transfers"):
        _run(transfers.sync_transfers, facility.license_number, "transfers")


def sync_new_masters():
    """Daily - create ERPNext masters for things that are new in Metrc.

    Separate from the hourly master-data job on purpose. The hourly run only
    *matches* existing records, which is always safe. Creating Items is a
    master-data change, so it happens once a day at a predictable time where
    the resulting review queue can be worked as a batch, rather than trickling
    in twenty-four times a day.
    """
    if not config.is_enabled():
        return

    created_items = created_tags = 0
    for facility in config.active_facilities():
        lic = facility.license_number
        created_items += _run(masterdata.create_missing_items, lic, "create items")
        created_tags += _run(masterdata.sync_available_tags, lic, "create tags")

    if created_items:
        _notify_new_items(created_items)
    return {"items": created_items, "tags": created_tags}


def _notify_new_items(count):
    """Auto-created Items need a human to confirm group, UOM and accounts."""
    recipient = frappe.db.get_single_value("Metrc Settings", "alert_email")
    if not recipient:
        return
    frappe.sendmail(
        recipients=[recipient],
        subject=f"[METRC] {count} new Item(s) created from METRC - review needed",
        message=(
            f"<p>The daily METRC sync created <b>{count}</b> new Item(s).</p>"
            "<p>They were built from the defaults in Metrc Settings and are "
            "<b>not sales or purchase enabled</b> until reviewed.</p>"
            "<p>Open the Item list and filter on "
            "<b>Auto-Created from METRC (needs review)</b>. For each one: confirm the "
            "item group, UOM and accounts, enable sales/purchase as appropriate, then "
            "untick the review flag.</p>"
        ),
    )


def sync_operations():
    """Daily."""
    if not config.is_enabled():
        return
    for facility in config.active_facilities(feature="sync_sales"):
        _run(sales.sync_receipts, facility.license_number, "sales")
    for facility in config.active_facilities(feature="sync_labtests"):
        _run(labtests.sync_labtests, facility.license_number, "labtests")


def sync_all(license_number=None):
    """Manual full sync, used by the Sync Now button in Metrc Settings."""
    licenses = [license_number] if license_number else config.configured_licenses()
    summary = {}
    for lic in licenses:
        summary[lic] = {
            "facilities": _run(masterdata.sync_facilities, lic, "facilities"),
            "items": _run(masterdata.sync_items, lic, "items"),
            "strains": _run(masterdata.sync_strains, lic, "strains"),
            "tags": _run(masterdata.sync_available_tags, lic, "tags"),
            "packages": _run(packages.sync_packages, lic, "packages"),
            "transfers": _run(transfers.sync_transfers, lic, "transfers"),
        }
    return summary


def alert_on_stalled_syncs():
    """Daily - email when a cursor has failed repeatedly."""
    stalled = frappe.get_all(
        "Metrc Sync State",
        filters={"consecutive_failures": [">=", ALERT_AFTER_FAILURES]},
        fields=["name", "consecutive_failures", "last_error"],
    )
    parked = frappe.db.count("Metrc Outbox", {"status": "Parked"})
    if not stalled and not parked:
        return

    recipient = frappe.db.get_single_value("Metrc Settings", "alert_email")
    if not recipient:
        return

    rows = "".join(
        f"<tr><td>{frappe.utils.escape_html(s.name)}</td>"
        f"<td align='right'>{s.consecutive_failures}</td>"
        f"<td>{frappe.utils.escape_html(s.last_error or '')}</td></tr>"
        for s in stalled
    )
    message = ""
    if stalled:
        message += (
            f"<p><b>{len(stalled)} sync cursor(s) failing repeatedly:</b></p>"
            "<table border='1' cellpadding='4' cellspacing='0'>"
            "<tr><th>Cursor</th><th>Failures</th><th>Last error</th></tr>"
            f"{rows}</table>"
        )
    if parked:
        message += (
            f"<p><b>{parked} outbox row(s) parked</b> - these need manual review; "
            "they will not retry on their own.</p>"
        )

    frappe.sendmail(
        recipients=[recipient],
        subject=f"[METRC] {len(stalled)} stalled cursor(s), {parked} parked write(s)",
        message=message,
    )
