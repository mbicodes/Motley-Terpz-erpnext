"""
Auto-submit Timesheet hook
Place this file at: <your_app>/hooks_handlers/timesheet_hooks.py

Then register in hooks.py:

doc_events = {
    "Timesheet": {
        "after_insert": "your_app.hooks_handlers.timesheet_hooks.auto_submit_timesheet",
        "on_submit":    "your_app.hooks_handlers.timesheet_hooks.on_timesheet_submitted",
    }
}

Replace "your_app" with your actual app name (e.g. motley_terpz, cannabis_mgmt, etc.)
"""

import frappe
from frappe import _


def auto_submit_timesheet(doc, method=None):
    """
    Automatically submit a Timesheet immediately after it is created (saved as Draft).
    Triggered by: after_insert

    This bypasses the need for users to manually click Submit.
    Permissions are checked — only valid, saveable docs are submitted.
    """
    try:
        # Avoid re-submitting if already submitted (docstatus 1)
        if doc.docstatus == 1:
            return

        # Only submit if docstatus is 0 (Draft)
        if doc.docstatus == 0:
            frappe.db.set_value("Timesheet", doc.name, "docstatus", 0)  # ensure draft
            doc.reload()
            doc.submit()
            frappe.db.commit()

            frappe.msgprint(
                _("Timesheet {0} has been automatically submitted.").format(
                    frappe.bold(doc.name)
                ),
                indicator="green",
                alert=True,
            )

    except Exception as e:
        frappe.log_error(
            title=f"Auto-Submit Failed: {doc.name}",
            message=frappe.get_traceback(),
        )
        # Don't raise — let the insert succeed even if submit fails
        frappe.msgprint(
            _("Timesheet saved but could not be auto-submitted: {0}").format(str(e)),
            indicator="orange",
            alert=True,
        )


def on_timesheet_submitted(doc, method=None):
    """
    Optional: runs after a Timesheet is submitted (manually or auto).
    Use for downstream actions like notifications, salary slip creation, etc.
    Triggered by: on_submit
    """
    # Example: send Slack notification (if you have a notifier utility)
    # from your_app.utils.slack import notify_timesheet_submitted
    # notify_timesheet_submitted(doc)

    frappe.logger().info(
        f"Timesheet {doc.name} submitted for employee {doc.employee_name} "
        f"| Hours: {doc.total_hours} | Amount: {doc.total_billable_amount}"
    )