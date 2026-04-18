def on_sales_invoice_submit(doc, method):
    """
    Triggered when a Sales Invoice is submitted.
    Sends a Slack notification with the due date and amount to be paid.
    """
    inv_url = frappe.utils.get_url("/app/sales-invoice/" + doc.name)
    amount_fmt = fmt_money(doc.grand_total, currency=doc.currency)
    due_fmt = formatdate(doc.due_date, "dd MMM yyyy")
    post_fmt = formatdate(doc.posting_date, "dd MMM yyyy")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":page_facing_up: New Sales Invoice Submitted"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Invoice:*\n<{0}|{1}>".format(inv_url, doc.name)},
                {"type": "mrkdwn", "text": "*Customer:*\n{0}".format(doc.customer)},
                {"type": "mrkdwn", "text": "*Invoice Date:*\n{0}".format(post_fmt)},
                {"type": "mrkdwn", "text": "*Due Date:*\n{0}".format(due_fmt)},
                {"type": "mrkdwn", "text": "*Amount to be Paid:*\n{0}".format(amount_fmt)},
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": ":bell: Payment of {0} is due by {1}.".format(amount_fmt, due_fmt)
                }
            ]
        }
    ]

    _send_slack(
        blocks,
        fallback_text="New invoice {0}: {1} due by {2} from {3}".format(
            doc.name, amount_fmt, due_fmt, doc.customer
        )
    )