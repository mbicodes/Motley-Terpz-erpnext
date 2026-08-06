# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Pull lab test results and stamp pass/fail onto the tag and batch.

Lab results gate whether product can be sold, so surfacing them on the Batch is
the single most operationally useful thing this pull does: a Batch showing
"Failed" should never reach a Sales Invoice.
"""

import frappe
from frappe.utils import now_datetime

from cannabis_management.metrc.pull.base import sweep


def sync_labtests(license_number):
    return sweep(license_number, "labtests.results", "/labtests/v2/results", upsert_results)


def upsert_results(rows, license_number):
    """Aggregate per-package results into a single overall state.

    Metrc returns one row per analyte per package, so a package with 12 tests
    yields 12 rows. Any failure fails the package.
    """
    by_label = {}
    for row in rows:
        label = row.get("PackageLabel") or row.get("Label")
        if not label:
            continue
        entry = by_label.setdefault(label, {"passed": True, "tested": False, "date": None})
        entry["tested"] = True
        if row.get("TestPassed") is False or row.get("Passed") is False:
            entry["passed"] = False
        result_date = row.get("TestPerformedDate") or row.get("ResultDate")
        if result_date and (not entry["date"] or result_date > entry["date"]):
            entry["date"] = result_date

    for label, entry in by_label.items():
        state = "Passed" if entry["passed"] else "Failed"
        try:
            _stamp(label, state, entry["date"])
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"[metrc] labtest stamp failed: {label}")

    frappe.db.commit()


def _stamp(label, state, result_date):
    if frappe.db.exists("Metric Tag", label):
        frappe.db.set_value(
            "Metric Tag",
            label,
            {"custom_metrc_lab_state": state, "custom_metrc_last_synced": now_datetime()},
            update_modified=False,
        )

    batch = frappe.db.get_value("Batch", {"custom_metrc_tag": label}, "name")
    if batch:
        values = {"custom_metrc_lab_state": state}
        if result_date:
            values["custom_metrc_lab_result_date"] = result_date
        frappe.db.set_value("Batch", batch, values, update_modified=False)
