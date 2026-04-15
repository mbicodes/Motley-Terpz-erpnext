"""
Job Card override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Job Card"]["on_submit"]

Responsibilities:
- Post Slack alert when a Job Card is completed (clock-out).
- Calculate actual labor cost based on employee wage × hours.
"""

import frappe
from cannabis_management.master_touch_manufacturing.utils.slack import send_alert


def on_submit(doc, method=None):
    """Notify Slack when a Job Card is completed."""
    _notify_completion(doc)


def _notify_completion(doc):
    try:
        pbg = doc.get("custom_production_batch_group") or ""
        duration_mins = _get_duration_minutes(doc)
        send_alert(
            "slack_mtm_production",
            f":white_check_mark: *Job Card Complete*\n"
            f"`{doc.name}` | Operation: {doc.operation} | "
            f"WO: {doc.work_order} | Duration: {duration_mins:.0f} min"
            + (f" | Batch: {pbg}" if pbg else "")
        )
    except Exception:
        pass  # Never block submission on Slack failure


def _get_duration_minutes(doc):
    """Sum time_logs for total actual duration in minutes."""
    try:
        total_mins = 0.0
        for row in doc.time_logs or []:
            if row.from_time and row.to_time:
                delta = frappe.utils.time_diff_in_seconds(row.to_time, row.from_time)
                total_mins += delta / 60
        return total_mins
    except Exception:
        return 0.0
