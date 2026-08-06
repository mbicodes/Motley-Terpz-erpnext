# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Pull Metrc packages into Metric Tag and Batch.

Important boundary: this module never touches Metric Tag.current_qty or the
Stock Ledger. Those are owned by the existing Inventory Dimension ("Muid")
machinery in cannabis_management.cannabis_management.doctype.metric_tag, which
derives quantity from the ledger on every stock transaction.

What we write here is the Metrc-side *mirror* - custom_metrc_quantity,
custom_metrc_status, custom_metrc_package_id - plus the variance between the
two. Divergence is reported, never silently reconciled: a difference is either
a data-entry error or a real physical discrepancy, and both need a human.
"""

import frappe
from frappe.utils import flt, now_datetime

from cannabis_management.metrc import config, mapping
from cannabis_management.metrc.pull.base import sweep

ENDPOINTS = (
    ("packages.active", "/packages/v2/active"),
    ("packages.inactive", "/packages/v2/inactive"),
    ("packages.onhold", "/packages/v2/onhold"),
)


def sync_packages(license_number):
    total = 0
    for endpoint_key, path in ENDPOINTS:
        total += sweep(license_number, endpoint_key, path, upsert_packages)
    return total


def upsert_packages(rows, license_number):
    """Idempotent upsert of a page of Metrc packages."""
    warehouse = config.warehouse_for_license(license_number)

    for pkg in rows:
        label = pkg.get("Label")
        if not label:
            continue
        try:
            _upsert_tag(pkg, label, license_number, warehouse)
            _upsert_batch(pkg, label, license_number, warehouse)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"[metrc] package upsert failed: {label}")
    frappe.db.commit()


def package_status(pkg):
    if pkg.get("FinishedDate") or pkg.get("IsFinished"):
        return "Finished"
    if pkg.get("IsOnHold"):
        return "On Hold"
    if pkg.get("IsInTransit"):
        return "In Transit"
    return "Active"


def _metrc_item_name(pkg):
    item = pkg.get("Item") or {}
    return item.get("Name") if isinstance(item, dict) else None


def _metrc_strain(pkg):
    item = pkg.get("Item") or {}
    return item.get("StrainName") if isinstance(item, dict) else None


def _upsert_tag(pkg, label, license_number, warehouse):
    """Mirror Metrc state onto Metric Tag without disturbing ledger fields."""
    metrc_qty = flt(pkg.get("Quantity"))
    values = {
        "custom_metrc_package_id": pkg.get("Id"),
        "custom_metrc_status": package_status(pkg),
        "custom_metrc_quantity": metrc_qty,
        "custom_metrc_uom": pkg.get("UnitOfMeasureName"),
        "custom_metrc_license_number": license_number,
        "custom_metrc_last_synced": now_datetime(),
    }

    if frappe.db.exists("Metric Tag", label):
        ledger_qty = flt(frappe.db.get_value("Metric Tag", label, "current_qty"))
        values["custom_metrc_variance"] = ledger_qty - metrc_qty
        frappe.db.set_value("Metric Tag", label, values, update_modified=True)
        return

    # A tag Metrc knows about that we have never seen. Create it so the tag
    # registry is complete, but leave status/current_qty for the ledger sync:
    # this package has no ERPNext stock behind it yet.
    doc = frappe.new_doc("Metric Tag")
    doc.tag_code = label
    doc.status = "Unused" if metrc_qty else "Empty"
    doc.warehouse = warehouse
    doc.last_transaction_type = "Metrc Sync"
    doc.update(values)
    doc.custom_metrc_variance = -metrc_qty
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)


def _upsert_batch(pkg, label, license_number, warehouse):
    """Batch is the ERPNext side of a Metrc package."""
    metrc_qty = flt(pkg.get("Quantity"))
    batch_name = frappe.db.get_value("Batch", {"custom_metrc_tag": label}, "name")

    values = {
        "custom_metrc_package_id": pkg.get("Id"),
        "custom_metrc_status": package_status(pkg),
        "custom_metrc_quantity": metrc_qty,
        "custom_metrc_uom": pkg.get("UnitOfMeasureName"),
        "custom_metrc_last_synced": now_datetime(),
    }
    if warehouse:
        values["custom_metrc_license_source"] = warehouse

    if batch_name:
        item_code = frappe.db.get_value("Batch", batch_name, "item")
        values["custom_metrc_variance"] = _ledger_qty(batch_name, item_code) - metrc_qty
        frappe.db.set_value("Batch", batch_name, values, update_modified=True)
        return

    item_code = mapping.erpnext_item_for_metrc(_metrc_item_name(pkg))
    if not item_code:
        # Package for an item we do not carry. Recorded on the tag above; a
        # Batch needs a valid Item link, so it stays an orphan until someone
        # maps the item. find_orphans() in reconcile.py surfaces these.
        return

    doc = frappe.new_doc("Batch")
    doc.batch_id = label
    doc.item = item_code
    doc.custom_metrc_tag = label
    doc.custom_metrc_variance = -metrc_qty

    strain = _metrc_strain(pkg)
    if strain and frappe.db.exists("Strain", strain):
        doc.custom_strain_name = strain

    doc.update(values)
    doc.flags.ignore_permissions = True
    try:
        doc.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        # Batch id already exists under a different tag field - link it instead.
        if frappe.db.exists("Batch", label):
            frappe.db.set_value("Batch", label, dict(values, custom_metrc_tag=label))


def _ledger_qty(batch_name, item_code=None):
    """Net ledger quantity for a batch, used for the variance mirror."""
    total = frappe.db.sql(
        """
        select sum(actual_qty) from `tabStock Ledger Entry`
        where batch_no = %s and is_cancelled = 0
        """,
        (batch_name,),
    )[0][0]
    return flt(total)
