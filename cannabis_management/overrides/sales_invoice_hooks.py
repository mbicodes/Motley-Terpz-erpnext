import frappe
import json
import http.client
import ssl


def check_inventory_and_notify_slack(doc, method):
    TARGET_COMPANY = "Master Touch Manufacturing"
    TARGET_WAREHOUSE = "Master Touch Manufacturing Toll - MTM"
    SLACK_CHANNEL = "#conversions-motley"

    frappe.log_error(
        "Slack hook triggered for Sales Order: {0}, Company: {1}".format(doc.name, doc.company),
        "Motley Terpz Slack - Hook Triggered"
    )

    if doc.company != TARGET_COMPANY:
        msg = "Slack notification skipped: Sales Order {0} belongs to company '{1}', expected '{2}'.".format(
            doc.name, doc.company, TARGET_COMPANY
        )
        frappe.log_error(msg, "Motley Terpz Slack - Skipped")
        return

    webhook_url = frappe.conf.get("slack_webhook_url")
    if not webhook_url:
        msg = "slack_webhook_url is not set in site_config.json. Cannot send Slack notification."
        frappe.log_error(msg, "Motley Terpz Slack - Config Missing")
        return

    required_map = {}
    label_map = {}
    uom_map = {}

    for row in doc.items:
        if not row.item_code:
            continue
        label_map[row.item_code] = row.item_name or row.item_code
        uom_map[row.item_code] = row.stock_uom or ""
        required_qty = float(row.stock_qty or 0)
        required_map[row.item_code] = required_map.get(row.item_code, 0) + required_qty

    if not required_map:
        msg = "Slack notification skipped: No items with item_code found in Sales Order {0}.".format(doc.name)
        frappe.log_error(msg, "Motley Terpz Slack - No Items")
        return

    need_lines = []
    ok_lines = []

    for item_code in required_map:
        required_qty = required_map[item_code]
        available = float(
            frappe.db.get_value(
                "Bin",
                {"item_code": item_code, "warehouse": TARGET_WAREHOUSE},
                "actual_qty"
            ) or 0
        )
        shortage = max(0, required_qty - available)
        label = label_map[item_code]
        suom = uom_map[item_code]

        item_display = "*{0}* (`{1}`)".format(label, item_code) if label != item_code else "`{0}`".format(item_code)

        if shortage > 0:
            need_lines.append(
                "• {0} — need *{1:.2f} {2}* (required {3:.2f}, available {4:.2f})".format(
                    item_display, shortage, suom, required_qty, available
                )
            )
        else:
            ok_lines.append(
                "• {0} — ok ({1:.2f} {2})".format(item_display, required_qty, suom)
            )

    header = ":red_circle: Conversion required" if need_lines else ":large_green_circle: No conversion required"
    order_link = frappe.utils.get_url("/app/sales-order/" + doc.name)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Sales Order:* <{0}|{1}>\n*Customer:* {2}\n*Warehouse:* {3}".format(
                    order_link, doc.name, doc.customer, TARGET_WAREHOUSE
                )
            }
        },
        {"type": "divider"}
    ]

    if need_lines:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":warning: *Needs conversion*\n" + "\n".join(need_lines)
            }
        })

    if ok_lines:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Items OK*\n" + "\n".join(ok_lines[:10])
            }
        })

    payload = {
        "channel": SLACK_CHANNEL,
        "text": doc.name + " inventory check",
        "blocks": blocks
    }

    try:
        body = json.dumps(payload)

        from urllib.parse import urlparse
        parsed = urlparse(webhook_url)

        context = ssl.create_default_context()
        conn = http.client.HTTPSConnection(parsed.hostname, context=context)
        conn.request(
            "POST",
            parsed.path,
            body=body,
            headers={"Content-Type": "application/json"}
        )
        resp = conn.getresponse()
        resp_body = resp.read().decode()
        conn.close()

        if resp.status == 200:
            success_msg = "✅ Slack notification sent successfully for Sales Order {0}!".format(doc.name)
            frappe.log_error(success_msg, "Motley Terpz Slack - Success")
        else:
            error_msg = "Slack API returned error {0}: {1}".format(resp.status, resp_body)
            frappe.log_error(error_msg, "Motley Terpz Slack - API Error")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Motley Terpz Slack - Exception")