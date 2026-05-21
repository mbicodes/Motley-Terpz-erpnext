import frappe
from frappe import _
from cannabis_management.doc_hooks.sales_invoice import check_ar_policy




def validate(doc, method=None):
    if doc.custom_mode_of_payment != "Payment Terms":
        return

    if not doc.custom_approval_status:
        doc.custom_approval_status = "Pending Approval"

    if doc.custom_approval_status == "Pending Approval":
        doc._notify_slack = True


def on_update(doc, method=None):
    if getattr(doc, "_notify_slack", False):
        _send_slack_approval_notification(doc)


def before_submit(doc, method=None):
    # AR policy — runs for all Sales Orders regardless of payment mode
    check_ar_policy(doc)

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


def _send_slack_approval_notification(doc):
    try:
        import json
        import urllib.request

        site_url = frappe.utils.get_url()
        so_link = f"{site_url}/app/sales-order/{doc.name}"

        schedule_rows = []
        if doc.payment_schedule:
            for row in doc.payment_schedule:
                due_date = frappe.format(row.due_date, {"fieldtype": "Date"}) if row.due_date else "-"
                payment_amount = frappe.format(row.payment_amount, {"fieldtype": "Currency"}) if row.payment_amount else "-"
                schedule_rows.append(f"• {due_date} — {payment_amount}")

        schedule_text = "\n".join(schedule_rows) if schedule_rows else "_No payment schedule entries_"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Sales Order Pending Approval",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Sales Order:*\n<{so_link}|{doc.name}>"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Customer:*\n{doc.customer}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Payment Schedule:*\n{schedule_text}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_This Sales Order uses *Payment Terms* mode and requires your approval._"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open Sales Order",
                            "emoji": True
                        },
                        "url": so_link,
                        "style": "primary"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "To approve: open the Sales Order and click *Submit* (HOO role required). The creator will automatically receive the PDF by email."
                    }
                ]
            }
        ]

        slack_channel = frappe.conf.get("slack_channel") or "#sales-order-approvals"
        slack_webhook_url = frappe.conf.get("slack_webhook_url")
        if not slack_webhook_url:
            frappe.log_error("Slack Webhook URL is missing in site config", "Sales Order Slack Notification Failed")
            return

        payload = json.dumps({"channel": slack_channel, "blocks": blocks}).encode("utf-8")
        req = urllib.request.Request(
            slack_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Sales Order Slack Notification Failed")
