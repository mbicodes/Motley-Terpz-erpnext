# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Remove sandbox-sourced Metrc data.

    bench --site <site> execute cannabis_management.metrc.purge.purge_sandbox_data

Pulling from the Metrc sandbox writes thousands of Metric Tag rows into the
same table as real tags. They are distinguishable by
custom_metrc_license_number, but before switching to Production you want them
gone so a sandbox tag can never be mistaken for a real one.

Deliberately conservative: only deletes tags that came from the sync and have
never been touched by a stock transaction (last_transaction_type is a Metrc
label, current_qty is zero, and no Stock Ledger Entry references them).
"""

import frappe

SANDBOX_TRANSACTION_TYPES = ("Metrc Sync", "Metrc Package Tag", "Metrc Plant Tag")


def _referenced_tags():
    """Tags any stock document has touched - never delete these."""
    from cannabis_management.cannabis_management.doctype.metric_tag.metric_tag import (
        get_metric_tag_dimension_fieldname,
    )

    column = frappe.utils.sanitize_column(get_metric_tag_dimension_fieldname())
    rows = frappe.db.sql(
        f"select distinct {column} from `tabStock Ledger Entry` where {column} is not null"
    )  # nosemgrep
    return {r[0] for r in rows if r[0]}


def purge_sandbox_data(license_number=None, dry_run=True):
    """Delete sync-created tags plus all sync bookkeeping."""
    filters = {"last_transaction_type": ["in", SANDBOX_TRANSACTION_TYPES]}
    if license_number:
        filters["custom_metrc_license_number"] = license_number

    candidates = frappe.get_all(
        "Metric Tag", filters=filters, fields=["name", "current_qty"]
    )
    protected = _referenced_tags()

    deletable = [
        c.name for c in candidates if c.name not in protected and not (c.current_qty or 0)
    ]
    skipped = len(candidates) - len(deletable)

    print(f"Metric Tag: {len(candidates)} sync-created, {len(deletable)} deletable, {skipped} in use")

    if dry_run:
        print("\nDRY RUN - nothing deleted. Re-run with dry_run=False to apply.")
        return {"deletable": len(deletable), "skipped": skipped}

    for chunk_start in range(0, len(deletable), 500):
        chunk = deletable[chunk_start : chunk_start + 500]
        frappe.db.delete("Metric Tag", {"name": ["in", chunk]})
        frappe.db.commit()

    # Clear the Metrc mirror on Batches without deleting the Batches themselves.
    frappe.db.sql(
        """
        update `tabBatch`
        set custom_metrc_package_id = null, custom_metrc_quantity = 0,
            custom_metrc_status = null, custom_metrc_variance = 0,
            custom_metrc_last_synced = null
        where custom_metrc_package_id is not null
        """
    )

    frappe.db.delete("Metrc Sync State", {})
    frappe.db.delete("Metrc API Log", {})
    frappe.db.delete("Metrc Outbox", {"status": ["in", ["Success", "Queued", "Failed"]]})
    frappe.db.commit()

    print(f"Deleted {len(deletable)} tags and reset all sync state.")
    print("Parked outbox rows were kept - review them before deleting.")
    return {"deleted": len(deletable), "skipped": skipped}


def reset_cursors(license_number=None):
    """Force a full re-sync on the next run without deleting pulled data."""
    filters = {"license_number": license_number} if license_number else {}
    names = frappe.get_all("Metrc Sync State", filters=filters, pluck="name")
    frappe.db.delete("Metrc Sync State", {"name": ["in", names]} if names else {})
    frappe.db.commit()
    print(f"Reset {len(names)} cursor(s). The next sync backfills from scratch.")
    return len(names)
