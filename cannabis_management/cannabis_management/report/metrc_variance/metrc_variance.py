# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Metrc Variance — where Metrc and the ERPNext stock ledger disagree.

Read-only and diagnostic. The fix belongs in a Stock Reconciliation with
custom_metrc_correction_made set, so the correction is itself auditable.
"""

import frappe
from frappe import _

from cannabis_management.metrc.reconcile import find_variances


def execute(filters=None):
    filters = frappe._dict(filters or {})
    rows = find_variances(license_number=filters.get("license_number"))

    if filters.get("min_difference"):
        threshold = abs(float(filters.min_difference))
        rows = [r for r in rows if abs(r["difference"]) >= threshold]

    data = [
        [
            r["metric_tag"],
            r["item_code"],
            r["warehouse"],
            r["license_number"],
            r["erpnext_qty"],
            r["metrc_qty"],
            r["difference"],
            r["uom"],
            r["erpnext_status"],
            r["metrc_status"],
            r["last_synced"],
        ]
        for r in rows
    ]

    return get_columns(), data


def get_columns():
    return [
        {"label": _("METRC Tag"), "fieldname": "metric_tag", "fieldtype": "Link",
         "options": "Metric Tag", "width": 210},
        {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link",
         "options": "Item", "width": 150},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link",
         "options": "Warehouse", "width": 140},
        {"label": _("License"), "fieldname": "license_number", "fieldtype": "Data", "width": 130},
        {"label": _("ERPNext Qty"), "fieldname": "erpnext_qty", "fieldtype": "Float",
         "precision": 4, "width": 110},
        {"label": _("METRC Qty"), "fieldname": "metrc_qty", "fieldtype": "Float",
         "precision": 4, "width": 110},
        {"label": _("Difference"), "fieldname": "difference", "fieldtype": "Float",
         "precision": 4, "width": 110},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 80},
        {"label": _("ERPNext Status"), "fieldname": "erpnext_status", "fieldtype": "Data", "width": 110},
        {"label": _("METRC Status"), "fieldname": "metrc_status", "fieldtype": "Data", "width": 110},
        {"label": _("Last Synced"), "fieldname": "last_synced", "fieldtype": "Datetime", "width": 150},
    ]
