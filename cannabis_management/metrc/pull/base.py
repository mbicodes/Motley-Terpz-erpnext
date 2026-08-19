# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Cursor-window sweep driver for inbound sync.

Metrc requires a bounded lastModified range on list endpoints, and the spec is
explicit that sweeps must run oldest -> newest: LastModified only ever moves
forward, so polling newest-first loses any record modified mid-sweep.

Each (licence, endpoint) pair therefore keeps a persisted watermark, advanced
one window at a time and committed after each window so a long backfill is
resumable rather than all-or-nothing.
"""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from cannabis_management.metrc import config
from cannabis_management.metrc.client import get_client

# Metrc's LastModified is set server-side and can lag slightly behind the write,
# so a hard window boundary can drop a record. Overlapping costs a few duplicate
# rows, which is free because every handler is idempotent.
OVERLAP_MINUTES = 5

# How far back a brand-new cursor starts.
INITIAL_BACKFILL_DAYS = 90

# Safety valve: stop after this many windows in one run so a cursor that has
# been idle for years cannot monopolise the scheduler.
MAX_WINDOWS_PER_RUN = 200


def iso(dt):
    """ISO 8601 for Metrc. urlencode handles %2B escaping downstream."""
    return get_datetime(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_sync_state(license_number, endpoint_key):
    name = f"{license_number}::{endpoint_key}"
    if frappe.db.exists("Metrc Sync State", name):
        return frappe.get_doc("Metrc Sync State", name)

    doc = frappe.new_doc("Metrc Sync State")
    doc.name = name
    doc.license_number = license_number
    doc.endpoint_key = endpoint_key
    doc.cursor_last_modified = add_to_date(now_datetime(), days=-INITIAL_BACKFILL_DAYS)
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def sweep(license_number, endpoint_key, path, handler, window_hours=None, extra_params=None):
    """Advance the cursor for one (licence, endpoint) pair.

    `handler(rows, license_number)` upserts a page of rows and must be
    idempotent, because windows overlap by design.

    Returns the number of records processed.
    """
    state = get_sync_state(license_number, endpoint_key)
    settings = config.get_settings()
    window_hours = window_hours or settings.window_hours or 24

    client = get_client(license_number)
    window_start = get_datetime(state.cursor_last_modified)
    ceiling = now_datetime()
    total = 0
    windows = 0
    caught_up = False

    state.db_set("last_run_start", now_datetime(), update_modified=False, commit=True)

    try:
        while windows < MAX_WINDOWS_PER_RUN:
            window_end = min(add_to_date(window_start, hours=window_hours), ceiling)

            params = dict(extra_params or {})
            params["lastModifiedStart"] = iso(window_start)
            params["lastModifiedEnd"] = iso(window_end)

            rows = list(client.get_all(path, params=params))
            if rows:
                handler(rows, license_number)
                total += len(rows)

            windows += 1

            # The persisted watermark is always rolled back by the overlap, so
            # the next window re-reads the last few minutes and cannot drop a
            # record whose LastModified landed just after the boundary.
            # Loop control uses window_end, NOT the rolled-back cursor: the two
            # were the same variable once, which meant the final window could
            # never reach the ceiling and the sweep span the window cap.
            state.db_set(
                "cursor_last_modified",
                add_to_date(window_end, minutes=-OVERLAP_MINUTES),
                update_modified=False,
                commit=True,
            )

            if window_end >= ceiling:
                caught_up = True
                break

            window_start = add_to_date(window_end, minutes=-OVERLAP_MINUTES)

        state.last_status = "Success" if caught_up else "Partial"
        state.last_error = (
            None
            if caught_up
            else f"Stopped after {MAX_WINDOWS_PER_RUN} windows; will continue next run."
        )
        state.consecutive_failures = 0

    except Exception as e:
        state.last_status = "Failed"
        state.last_error = str(e)[:1000]
        state.consecutive_failures = (state.consecutive_failures or 0) + 1
        frappe.log_error(
            frappe.get_traceback(), f"[metrc] sweep failed {license_number}/{endpoint_key}"
        )
        raise

    finally:
        state.last_run_end = now_datetime()
        state.records_synced = (state.records_synced or 0) + total
        state.flags.ignore_permissions = True
        state.save(ignore_permissions=True)
        frappe.db.commit()

    return total


def simple_pull(license_number, path, handler, params=None):
    """For endpoints with no lastModified filter (enumerations, tag pools)."""
    client = get_client(license_number)
    rows = client.get(path, params=params)
    if rows:
        handler(rows, license_number)
    return len(rows or [])
