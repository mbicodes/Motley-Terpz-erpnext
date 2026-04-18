"""
Daily scheduled task: send Slack delivery-date reminders for Sales Orders.

Logic:
  - Runs once per day.
  - Finds all submitted Sales Orders whose delivery_date == today.
  - Skips any SO that already has a submitted Delivery Note.
  - Skips companies not in COMPANY_CHANNEL_MAP.
  - Posts a "Has this been delivered/picked up?" message to the relevant
    Slack channel using the webhook URL stored in the Frappe
    `Slack Webhook URL` DocType.

Registered in hooks.py under scheduler_events → daily.
"""

import json
import http.client
import ssl
from urllib.parse import urlparse

import frappe
from frappe.utils import today, fmt_money


# Map company name → Slack Webhook URL record name (stored in ERPNext)
COMPANY_CHANNEL_MAP = {
    "Motley Terpz": "sales-order-motley-terpz",
    "TSBC Ranch":   "sales-order-tsbc",
}


def send_delivery_date_reminders():
    """Entry point called by the daily scheduler."""
    orders = _get_todays_orders()
    for so in orders:
        try:
            _process_order(so)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"SO Delivery Reminder - Error processing {so.name}"
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_todays_orders():
    """Return submitted SOs with delivery_date = today, excluding Closed/Cancelled."""
    return frappe.get_all(
        "Sales Order",
        filters={
            "docstatus": 1,
            "delivery_date": today(),
            "status": ["not in", ["Closed", "Cancelled", "Completed"]],
        },
        fields=["name", "customer", "company", "grand_total", "currency", "delivery_date"],
    )


def _has_delivery_note(so_name):
    """Return True if at least one submitted Delivery Note line references this SO."""
    return frappe.db.exists(
        "Delivery Note Item",
        {"against_sales_order": so_name, "docstatus": 1},
    )


def _get_webhook_url(webhook_record_name):
    """Fetch the actual Slack webhook URL from the Frappe DocType."""
    url = frappe.db.get_value("Slack Webhook URL", webhook_record_name, "webhook_url")
    if not url:
        frappe.log_error(
            f"No webhook_url found for Slack Webhook URL record: '{webhook_record_name}'",
            "SO Delivery Reminder - Config Missing"
        )
    return url


def _process_order(so):
    """Check one SO and fire Slack message if applicable."""
    # Skip companies we don't have a channel for
    channel_record = COMPANY_CHANNEL_MAP.get(so.company)
    if not channel_record:
        return

    # Skip if Delivery Note already submitted
    if _has_delivery_note(so.name):
        return

    webhook_url = _get_webhook_url(channel_record)
    if not webhook_url:
        return

    _post_slack_message(so, webhook_url)


def _post_slack_message(so, webhook_url):
    """Build Block Kit payload and POST to Slack webhook."""
    so_url = frappe.utils.get_url(f"/app/sales-order/{so.name}")
    amount_str = fmt_money(so.grand_total, currency=so.currency)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":truck: Delivery Check — Action Required"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Has this order been delivered or picked up?*\n\n"
                    f"*Sales Order:* <{so_url}|{so.name}>\n"
                    f"*Customer:* {so.customer}\n"
                    f"*Company:* {so.company}\n"
                    f"*Delivery Date:* {so.delivery_date}\n"
                    f"*Order Total:* {amount_str}"
                )
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":white_check_mark: If delivered — create a *Delivery Note* in ERP to close this reminder.\n"
                    ":x: If not yet delivered — update the *Delivery Date* on the Sales Order."
                )
            }
        }
    ]

    payload = {
        "text": f"Delivery Check: {so.name} — {so.customer} — {so.delivery_date}",
        "blocks": blocks,
    }

    try:
        body = json.dumps(payload).encode("utf-8")
        parsed = urlparse(webhook_url)
        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, context=context, timeout=10)
        conn.request(
            "POST",
            parsed.path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        resp_body = resp.read().decode()
        conn.close()

        if resp.status == 200:
            frappe.log_error(
                f"Delivery reminder sent for {so.name} ({so.company})",
                "SO Delivery Reminder - Sent"
            )
        else:
            frappe.log_error(
                f"Slack returned {resp.status}: {resp_body} for {so.name}",
                "SO Delivery Reminder - API Error"
            )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"SO Delivery Reminder - HTTP Error for {so.name}"
        )
