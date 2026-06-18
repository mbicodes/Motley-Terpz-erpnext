import frappe
import json
import http.client
import ssl
from urllib.parse import urlparse


SLACK_CHANNEL = "#conversions-motley"
SLACK_MENTION_MEMBER_ID = "U0AJ7HW183G"

# (item_code field, qty field) pairs on a Conversion Entry Item row
_RM_PAIRS = [
    ("raw_material_1", "qty_rm_1"),
    ("raw_material_2", "qty_rm_2"),
    ("raw_material_3", "qty_rm_3"),
    ("raw_material_4", "qty_rm_4"),
    ("raw_material_5", "qty_rm_5"),
    ("raw_material_6", "qty_rm_6"),
    ("raw_material_7", "qty_rm_7"),
]

_FG_PAIRS = [
    ("finished_good_1", "qty_fg_1"),
    ("finished_good_2", "qty_fg_2"),
]


def notify_conversion_entry_slack(doc, method):
    """On Conversion Entry submit, post an extract repack / strain conversion
    summary to Slack: one source-strain + target-strain block per item row,
    linking back to the Conversion Entry document."""

    frappe.log_error(
        "Slack hook triggered for Conversion Entry: {0}".format(doc.name),
        "Motley Terpz CE Slack - Hook Triggered",
    )

    webhook_url = frappe.conf.get("slack_webhook_url")
    if not webhook_url:
        frappe.log_error(
            "slack_webhook_url is not set in site_config.json. Cannot send Slack notification.",
            "Motley Terpz CE Slack - Config Missing",
        )
        return

    if not doc.items:
        frappe.log_error(
            "Slack notification skipped: Conversion Entry {0} has no item rows.".format(doc.name),
            "Motley Terpz CE Slack - No Items",
        )
        return

    doc_link = frappe.utils.get_url("/app/conversion-entry/" + doc.name)

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "MOTLEY TERPZ – EXTRACT REPACK & STRAIN CONVERSION",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Conversion Entry:* <{0}|{1}>\n*Date:* {2}".format(
                    doc_link, doc.name, doc.posting_date or ""
                ),
            },
        },
        {"type": "divider"},
    ]

    for idx, row in enumerate(doc.items, 1):
        source_lines = _strain_lines(row, _RM_PAIRS, row.source_warehouse)
        target_lines = _strain_lines(row, _FG_PAIRS, row.target_warehouse)

        row_text = ":package: *Source Strain(s):*\n"
        row_text += "\n".join(source_lines) if source_lines else " - _none_"
        row_text += "\n\n:dart: *Target Strain / Blend:*\n"
        row_text += "\n".join(target_lines) if target_lines else " - _none_"

        # Slack section text caps at 3000 chars; truncate defensively.
        if len(row_text) > 2900:
            row_text = row_text[:2900] + "\n …(truncated)"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": row_text},
        })
        if idx < len(doc.items):
            blocks.append({"type": "divider"})

    mention = "<@{0}> ".format(SLACK_MENTION_MEMBER_ID) if SLACK_MENTION_MEMBER_ID else ""
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "{0}:warning: *Action Required:*\nReview and confirm this extract conversion before execution.".format(mention),
        },
    })

    payload = {
        "channel": SLACK_CHANNEL,
        "text": "{0} – Extract Repack & Strain Conversion".format(doc.name),
        "blocks": blocks,
    }

    _post_to_slack(webhook_url, payload, doc.name)


def _strain_lines(row, pairs, warehouse):
    """Build ' - CODE | Item Name – qty UOM ⸱ Warehouse' lines for the given
    (item_field, qty_field) pairs on a row."""
    lines = []
    for item_field, qty_field in pairs:
        item_code = row.get(item_field)
        qty = frappe.utils.flt(row.get(qty_field))
        if not item_code or qty <= 0:
            continue

        item_name, uom = frappe.db.get_value(
            "Item", item_code, ["item_name", "stock_uom"]
        ) or (item_code, "")
        name_part = "{0} | {1}".format(item_code, item_name) if item_name and item_name != item_code else item_code

        lines.append(
            " - {0} – {1:g} {2} ⸱ {3}".format(name_part, qty, uom or "", warehouse or "")
        )
    return lines


def _post_to_slack(webhook_url, payload, doc_name):
    try:
        body = json.dumps(payload)
        parsed = urlparse(webhook_url)

        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, context=context)
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
                "✅ Slack notification sent successfully for Conversion Entry {0}!".format(doc_name),
                "Motley Terpz CE Slack - Success",
            )
        else:
            frappe.log_error(
                "Slack API returned error {0}: {1}".format(resp.status, resp_body),
                "Motley Terpz CE Slack - API Error",
            )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Motley Terpz CE Slack - Exception")
