import frappe
from frappe.utils import today, add_days


def send_payment_schedule_reminders():
    """
    Runs daily. Sends email to the SO creator 14 days and 7 days before each
    payment_schedule due_date on submitted Payment Terms Sales Orders.
    """
    for days_ahead in (14, 7):
        target_date = add_days(today(), days_ahead)
        _send_reminders_for_date(target_date, days_ahead)


def _send_reminders_for_date(target_date, days_ahead):
    schedules = frappe.db.sql("""
        SELECT
            ps.due_date,
            ps.payment_amount,
            ps.outstanding,
            so.name          AS so_name,
            so.customer      AS customer,
            so.owner         AS owner
        FROM `tabPayment Schedule` ps
        JOIN `tabSales Order` so ON so.name = ps.parent
        WHERE ps.due_date        = %s
          AND ps.parenttype      = 'Sales Order'
          AND so.docstatus       = 1
          AND so.custom_mode_of_payment = 'Payment Terms'
    """, (target_date,), as_dict=True)

    for row in schedules:
        _send_reminder_email(row, days_ahead)


def _send_reminder_email(row, days_ahead):
    try:
        creator_email = frappe.get_value("User", row.owner, "email")
        if not creator_email:
            return

        creator_name = frappe.get_fullname(row.owner)
        site_url = frappe.utils.get_url()
        so_link = f"{site_url}/app/sales-order/{row.so_name}"

        due_date_str = frappe.format(row.due_date, {"fieldtype": "Date"})
        amount_str = frappe.format_value(row.payment_amount or 0, {"fieldtype": "Currency"})
        outstanding_str = frappe.format_value(row.outstanding or 0, {"fieldtype": "Currency"})

        day_label = f"{days_ahead} days"

        frappe.sendmail(
            recipients=[creator_email],
            subject=f"Payment Due in {day_label} — {row.so_name} ({row.customer})",
            message=f"""
                <p>Dear {creator_name},</p>

                <p>This is a reminder that a payment is due in <strong>{day_label}</strong>
                for the following Sales Order:</p>

                <table style="border-collapse:collapse; width:100%; max-width:480px; font-family:Arial,sans-serif;">
                    <tr style="background:#f5f5f5;">
                        <td style="padding:10px 14px; border:1px solid #ddd; font-weight:bold;">Sales Order</td>
                        <td style="padding:10px 14px; border:1px solid #ddd;">
                            <a href="{so_link}">{row.so_name}</a>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:10px 14px; border:1px solid #ddd; font-weight:bold;">Customer</td>
                        <td style="padding:10px 14px; border:1px solid #ddd;">{row.customer}</td>
                    </tr>
                    <tr style="background:#f5f5f5;">
                        <td style="padding:10px 14px; border:1px solid #ddd; font-weight:bold;">Due Date</td>
                        <td style="padding:10px 14px; border:1px solid #ddd;">{due_date_str}</td>
                    </tr>
                    <tr>
                        <td style="padding:10px 14px; border:1px solid #ddd; font-weight:bold;">Amount Due</td>
                        <td style="padding:10px 14px; border:1px solid #ddd;">{amount_str}</td>
                    </tr>
                    <tr style="background:#f5f5f5;">
                        <td style="padding:10px 14px; border:1px solid #ddd; font-weight:bold;">Outstanding</td>
                        <td style="padding:10px 14px; border:1px solid #ddd;">{outstanding_str}</td>
                    </tr>
                </table>

                <p style="margin-top:16px;">
                    Please ensure collection of <strong>{amount_str}</strong> from
                    <strong>{row.customer}</strong> is arranged before <strong>{due_date_str}</strong>.
                </p>
            """
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Payment Schedule Reminder Email Failed")
