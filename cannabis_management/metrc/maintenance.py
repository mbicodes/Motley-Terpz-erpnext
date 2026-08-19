# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Housekeeping for the Metrc module."""

import frappe
from frappe.utils import add_days, now_datetime


def prune_logs():
    """Trim API logs and settled outbox rows.

    Parked rows are kept regardless of age: they represent unresolved
    compliance work and deleting them would hide it.
    """
    days = frappe.db.get_single_value("Metrc Settings", "log_retention_days") or 120
    cutoff = add_days(now_datetime(), -days)

    frappe.db.delete("Metrc API Log", {"timestamp": ["<", cutoff]})
    frappe.db.delete("Metrc Outbox", {"status": "Success", "modified": ["<", cutoff]})
    frappe.db.commit()


def clear_caches(doc=None, method=None):
    """Drop cached UOM maps and enumerations.

    Registered as the Metrc Settings on_update hook, so Frappe passes
    (doc, method) - both ignored, but the signature has to accept them.
    """
    for key in ("uom_map", "tracked_items"):
        frappe.cache.hdel("metrc", key)
    from cannabis_management.metrc.pull.masterdata import ENUMERATIONS

    for key in ENUMERATIONS:
        frappe.cache.hdel("metrc", f"enum:{key}")
