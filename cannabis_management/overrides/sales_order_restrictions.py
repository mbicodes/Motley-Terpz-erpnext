import frappe
from frappe import _
# AR Policy disabled — import removed
# from cannabis_management.doc_hooks.sales_invoice import check_ar_policy




# Approver who must sign off on Payment-Terms Sales Orders.
APPROVER_EMAIL = "muhammad@motleyterpz.com"


def validate(doc, method=None):
    if doc.custom_mode_of_payment != "Payment Terms":
        return

    if not doc.custom_approval_status:
        doc.custom_approval_status = "Pending Approval"


def on_update(doc, method=None):
    # Email the approver once, when the Sales Order first enters "Pending
    # Approval" (on creation, or when it transitions into that state) — not on
    # every subsequent save.
    if doc.custom_mode_of_payment != "Payment Terms":
        return
    if doc.custom_approval_status != "Pending Approval":
        return

    before = doc.get_doc_before_save()
    if before is None or before.get("custom_approval_status") != "Pending Approval":
        _send_approval_email(doc)


def before_submit(doc, method=None):
    # AR policy disabled
    # check_ar_policy(doc)

    if doc.custom_mode_of_payment != "Payment Terms":
        return

    if "HOO" in frappe.get_roles(frappe.session.user):
        # HOO submitting = implicit approval; stamp status before save
        doc.custom_approval_status = "Approved"
        return

    if doc.custom_approval_status != "Approved":
        frappe.throw(
            msg=_("This Sales Order requires approval from the Operation Manager before it can be submitted."),
            title=_("Approval Required")
        )


def on_submit(doc, method=None):
    if doc.custom_mode_of_payment == "Payment Terms":
        _send_print_to_creator(doc)


def _send_print_to_creator(doc):
    try:
        creator_email = frappe.get_value("User", doc.owner, "email")
        creator_name = frappe.get_fullname(doc.owner)
        approver_name = frappe.get_fullname(frappe.session.user)

        if not creator_email:
            frappe.log_error(f"No email found for user {doc.owner}", "Sales Order Print Email")
            return

        pdf_content = frappe.get_print(
            doctype="Sales Order",
            name=doc.name,
            print_format=None,
            as_pdf=True
        )

        frappe.sendmail(
            recipients=[creator_email],
            subject=f"Sales Order {doc.name} — Approved & Submitted",
            message=f"""
                <p>Dear {creator_name},</p>
                <p>Sales Order <strong>{doc.name}</strong> for customer <strong>{doc.customer}</strong>
                has been approved and submitted by <strong>{approver_name}</strong>.</p>
                <p>Please find the Sales Order attached.</p>
            """,
            attachments=[{
                "fname": f"{doc.name}.pdf",
                "fcontent": pdf_content
            }]
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Sales Order Print Email Failed")


def _send_approval_email(doc):
    """Email the approver that a Payment-Terms Sales Order needs sign-off."""
    try:
        site_url = frappe.utils.get_url()
        so_link = f"{site_url}/app/sales-order/{doc.name}"
        currency = doc.get("currency")

        schedule_rows = []
        if doc.payment_schedule:
            for row in doc.payment_schedule:
                due_date = frappe.format(row.due_date, {"fieldtype": "Date"}) if row.due_date else "-"
                payment_amount = (
                    frappe.format(row.payment_amount, {"fieldtype": "Currency", "options": "currency"}, doc)
                    if row.payment_amount else "-"
                )
                schedule_rows.append(
                    f"<tr><td style='padding:6px 12px;border:1px solid #e2e8f0;'>{due_date}</td>"
                    f"<td style='padding:6px 12px;border:1px solid #e2e8f0;text-align:right;'>{payment_amount}</td></tr>"
                )
        if schedule_rows:
            schedule_html = (
                "<table style='border-collapse:collapse;margin:8px 0;font-size:13px;'>"
                "<thead><tr>"
                "<th style='padding:6px 12px;border:1px solid #e2e8f0;text-align:left;background:#f8fafc;'>Due Date</th>"
                "<th style='padding:6px 12px;border:1px solid #e2e8f0;text-align:right;background:#f8fafc;'>Amount</th>"
                "</tr></thead><tbody>" + "".join(schedule_rows) + "</tbody></table>"
            )
        else:
            schedule_html = "<p style='color:#888;'><em>No payment schedule entries.</em></p>"

        grand_total = (
            frappe.format(doc.grand_total, {"fieldtype": "Currency", "options": "currency"}, doc)
            if doc.get("grand_total") else "-"
        )
        creator_name = frappe.utils.get_fullname(doc.owner)

        message = f"""
            <p>Hello,</p>
            <p>A new Sales Order using <strong>Payment Terms</strong> requires your approval.</p>
            <table style='font-size:14px;margin:8px 0;'>
                <tr><td style='padding:2px 12px 2px 0;color:#666;'>Sales Order</td>
                    <td><a href="{so_link}"><strong>{doc.name}</strong></a></td></tr>
                <tr><td style='padding:2px 12px 2px 0;color:#666;'>Customer</td>
                    <td>{doc.customer}</td></tr>
                <tr><td style='padding:2px 12px 2px 0;color:#666;'>Grand Total</td>
                    <td>{grand_total}</td></tr>
                <tr><td style='padding:2px 12px 2px 0;color:#666;'>Created By</td>
                    <td>{creator_name}</td></tr>
            </table>
            <p style='margin-bottom:4px;'><strong>Payment Schedule</strong></p>
            {schedule_html}
            <p style='margin-top:16px;'>
                <a href="{so_link}"
                   style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;
                          padding:9px 18px;border-radius:6px;font-weight:600;">Open Sales Order</a>
            </p>
            <p style='color:#666;font-size:13px;'>To approve, open the Sales Order and click
            <strong>Submit</strong> (HOO role required). The creator will automatically receive
            the approved PDF by email.</p>
        """

        frappe.sendmail(
            recipients=[APPROVER_EMAIL],
            subject=f"Sales Order {doc.name} — Approval Required",
            message=message,
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Sales Order Approval Email Failed")
