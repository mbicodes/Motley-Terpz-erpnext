import frappe
from frappe.utils import fmt_money, formatdate  # fmt_money kept for friday_overdue_report
import json
import http.client
import ssl
from urllib.parse import urlparse


def on_sales_invoice_submit(doc, method):
    """
    Triggered when a Sales Order is submitted.
    Sends a Slack notification with the order and delivery date (no pricing).
    """
    order_url = frappe.utils.get_url("/app/sales-order/" + doc.name)
    delivery_fmt = formatdate(doc.delivery_date, "dd MMM yyyy") if doc.delivery_date else "N/A"
    order_date_fmt = formatdate(doc.transaction_date, "dd MMM yyyy")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":page_facing_up: New Sales Order Submitted"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Order:*\n<{0}|{1}>".format(order_url, doc.name)},
                {"type": "mrkdwn", "text": "*Customer:*\n{0}".format(doc.customer)},
                {"type": "mrkdwn", "text": "*Order Date:*\n{0}".format(order_date_fmt)},
                {"type": "mrkdwn", "text": "*Delivery Date:*\n{0}".format(delivery_fmt)},
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": ":bell: Delivery is expected by {0}.".format(delivery_fmt)
                }
            ]
        }
    ]

    _send_slack(
        blocks,
        fallback_text="New order {0} from {1} — delivery by {2}".format(
            doc.name, doc.customer, delivery_fmt
        )
    )


def _send_slack(blocks, fallback_text):
    """POST a Block Kit message to the Slack webhook configured in site_config."""
    webhook_url = frappe.conf.get("slack_webhook_url")
    if not webhook_url:
        frappe.log_error(
            "slack_webhook_url is not set in site_config.json. Cannot send Slack notification.",
            "Sales Order Slack - Config Missing"
        )
        return

    payload = json.dumps({"text": fallback_text, "blocks": blocks}).encode("utf-8")
    try:
        parsed = urlparse(webhook_url)
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, context=context, timeout=10)
        conn.request("POST", parsed.path, body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp_body = resp.read().decode()
        conn.close()
        if resp.status != 200:
            frappe.log_error(
                "Slack API returned {0}: {1}".format(resp.status, resp_body),
                "Sales Order Slack - API Error"
            )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Sales Order Slack - Exception")


def friday_overdue_report():
    pass