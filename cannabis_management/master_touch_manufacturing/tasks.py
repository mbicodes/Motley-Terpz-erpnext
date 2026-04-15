"""
Scheduled tasks for Masters Touch Manufacturing module.

Registered in hooks.py under scheduler_events:
    "daily":   ["cannabis_management.master_touch_manufacturing.tasks.daily"]
    "weekly":  ["cannabis_management.master_touch_manufacturing.tasks.weekly"]
    "monthly": ["cannabis_management.master_touch_manufacturing.tasks.monthly"]
"""

import frappe
from cannabis_management.master_touch_manufacturing.utils.slack import send_alert


def daily():
    """Run every day. Check for open batches older than 7 days."""
    _alert_stale_batches()


def weekly():
    """Run every week. Send weekly production summary."""
    _send_weekly_production_summary()


def monthly():
    """Run every month. Send monthly yield + cost report."""
    _send_monthly_cost_report()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _alert_stale_batches():
    """Alert #mtm-production for any Wash/Press Batches open > 7 days."""
    for doctype in ["Wash Batch", "Press Batch"]:
        try:
            stale = frappe.get_all(
                doctype,
                filters={
                    "docstatus": 0,
                    "creation": ["<", frappe.utils.add_days(frappe.utils.today(), -7)],
                },
                fields=["name", "creation"],
            )
            for rec in stale:
                send_alert(
                    "slack_mtm_production",
                    f":hourglass: *Stale {doctype}* `{rec['name']}` has been open since {rec['creation'].strftime('%Y-%m-%d')} — please review."
                )
        except Exception:
            pass  # DocType may not exist yet during initial migration


def _send_weekly_production_summary():
    """Post a weekly summary of submitted Wash + Press Batches to Slack."""
    from frappe.utils import add_days, today
    week_ago = add_days(today(), -7)
    try:
        wash_count = frappe.db.count("Wash Batch", {"docstatus": 1, "posting_date": [">=", week_ago]})
        press_count = frappe.db.count("Press Batch", {"docstatus": 1, "posting_date": [">=", week_ago]})
        send_alert(
            "slack_mtm_production",
            f":bar_chart: *Weekly Production Summary*\n"
            f"Wash runs: *{wash_count}* | Press runs: *{press_count}*\n"
            f"Period: {week_ago} to {today()}"
        )
    except Exception:
        pass


def _send_monthly_cost_report():
    """
    Placeholder for monthly yield + cost report.
    Full implementation in Phase 13.
    """
    pass
