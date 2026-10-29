import frappe
from frappe import _
from frappe.utils import flt


def auto_submit_timesheet(doc, method=None):
    try:
        if doc.docstatus == 1:
            return

        if any(not row.to_time or flt(row.hours) == 0.0 for row in doc.time_logs):
            return

        if doc.docstatus == 0:
            frappe.db.set_value("Timesheet", doc.name, "docstatus", 0)
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
        doc._action = "save"

        frappe.log_error(
            title=f"Auto-Submit Failed: {doc.name}",
            message=frappe.get_traceback(),
        )
        frappe.msgprint(
            _("Timesheet saved but could not be auto-submitted: {0}").format(str(e)),
            indicator="orange",
            alert=True,
        )


def on_timesheet_submitted(doc, method=None):
    frappe.logger().info(
        f"Timesheet {doc.name} submitted for employee {doc.employee_name} "
        f"| Hours: {doc.total_hours} | Amount: {doc.total_billable_amount}"
    )
