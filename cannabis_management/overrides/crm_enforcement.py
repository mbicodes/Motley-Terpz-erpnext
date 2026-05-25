"""
CRM AR Enforcement
  - check_customer_blocked(): fires on Sales Invoice + Sales Order before_submit.
    Blocked = customer AR > $50k OR oldest unpaid invoice > 60 days overdue.
    Non-admin → hard throw.  Admin → red warning (can proceed).
    Always fires a Slack notification to Matt, Imran, and Nikki.

  - crm_lead_query_conditions(): permission filter for CRM Lead.
    Hides Tolling pipeline leads from users who lack the "CRM Tolling Access" role.
"""

import frappe
from frappe import _
from frappe.utils import flt


BLOCKED_AR_THRESHOLD = 50_000.0
BLOCKED_AGING_DAYS   = 60

BLOCKED_SLACK_USERS = [
    "matt@motleyterpz.com",
    "imran@motleyterpz.com",
    "nikki@motleyterpz.com",
]

COD_NOTIFY_EMAIL = "mbi@alltechvirtual.com"


# ── Doc hook: fires on Sales Invoice + Sales Order before_submit ──────────────

def check_customer_blocked(doc, method=None):
    if not doc.customer:
        return

    blocked, reason = _is_customer_blocked(doc.customer)
    if not blocked:
        return

    _send_blocked_slack(doc, reason)

    msg = _(
        "Customer <b>{0}</b> is currently <b>BLOCKED</b>.<br><br>"
        "Reason: {1}<br><br>"
        "Matt, Imran, and Nikki have been notified via Slack. "
        "Contact Finance to resolve the outstanding balance before submitting."
    ).format(doc.customer, reason)

    if _is_admin():
        frappe.msgprint(msg, title=_("Blocked Customer — Admin Override"), indicator="red")
    else:
        frappe.throw(msg, title=_("Customer Blocked — Submission Not Allowed"))


# ── COD enforcement: notify Muhammad when a COD customer gets an invoice ─────

def check_cod_customer(doc, method=None):
    """
    If the customer is flagged COD-only in CRM, send a Slack alert to Muhammad
    so he can verify cash was collected before the invoice is posted.
    """
    if not doc.customer or not frappe.db.exists("DocType", "CRM Lead"):
        return
    if not frappe.db.has_column("CRM Lead", "custom_erp_customer"):
        return

    is_cod = frappe.db.get_value(
        "CRM Lead",
        {"custom_erp_customer": doc.customer, "custom_cod_only": 1},
        "name",
    )
    if not is_cod:
        return

    _send_cod_slack(doc)


def _send_cod_slack(doc):
    try:
        import json
        import urllib.request

        slack_webhook_url = frappe.conf.get("slack_webhook_url")
        if not slack_webhook_url:
            return

        site_url = frappe.utils.get_url()
        doc_link = f"{site_url}/app/sales-invoice/{doc.name or 'new'}"
        amount   = frappe.utils.flt(doc.grand_total)

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "💵 COD Customer Invoice Submitted", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer:*\n{doc.customer}"},
                    {"type": "mrkdwn", "text": f"*Amount:*\n${amount:,.2f}"},
                ],
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Invoice:*\n<{doc_link}|{doc.name or 'New'}>"},
                    {"type": "mrkdwn", "text": f"*Submitted by:*\n{frappe.get_fullname(frappe.session.user)}"},
                ],
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "This customer is marked *COD Only* in CRM. Confirm cash was collected."}],
            },
        ]

        slack_channel = frappe.conf.get("slack_channel") or "#ar-alerts"
        payload = json.dumps({"channel": slack_channel, "blocks": blocks}).encode("utf-8")
        req = urllib.request.Request(
            slack_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[crm_enforcement] COD Slack notification failed")


# ── CRM Lead permission filter: hide Tolling from unauthorised users ──────────

def crm_lead_query_conditions(user):
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return ""
    if "CRM Tolling Access" in frappe.get_roles(user):
        return ""
    return (
        "(`tabCRM Lead`.`custom_pipeline` != 'Tolling' "
        "OR `tabCRM Lead`.`custom_pipeline` IS NULL "
        "OR `tabCRM Lead`.`custom_pipeline` = '')"
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_customer_blocked(customer):
    row = frappe.db.sql("""
        SELECT
            COALESCE(SUM(outstanding_amount), 0)            AS balance,
            COALESCE(MAX(DATEDIFF(CURDATE(), due_date)), 0)  AS max_aging
        FROM `tabSales Invoice`
        WHERE customer = %s
          AND docstatus = 1
          AND outstanding_amount > 0.01
    """, customer, as_dict=True)

    if not row:
        return False, ""

    balance    = flt(row[0].balance)
    aging_days = int(row[0].max_aging or 0)

    reasons = []
    if balance > BLOCKED_AR_THRESHOLD:
        reasons.append(f"AR balance ${balance:,.2f} exceeds ${BLOCKED_AR_THRESHOLD:,.0f}")
    if aging_days > BLOCKED_AGING_DAYS:
        reasons.append(f"oldest unpaid invoice is {aging_days} days overdue ({BLOCKED_AGING_DAYS}-day limit)")

    if reasons:
        return True, " &amp; ".join(reasons)
    return False, ""


def _is_admin():
    roles = frappe.get_roles()
    return (
        frappe.session.user == "Administrator"
        or "System Manager" in roles
        or "Administrator" in roles
    )


def _send_blocked_slack(doc, reason):
    try:
        import json
        import urllib.request

        slack_webhook_url = frappe.conf.get("slack_webhook_url")
        if not slack_webhook_url:
            return

        site_url  = frappe.utils.get_url()
        doc_slug  = "sales-invoice" if doc.doctype == "Sales Invoice" else "sales-order"
        doc_link  = f"{site_url}/app/{doc_slug}/{doc.name or 'new'}"
        submitter = frappe.get_fullname(frappe.session.user)

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "⚠️ Blocked Customer — Submission Attempted", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Customer:*\n{doc.customer}"},
                    {"type": "mrkdwn", "text": f"*Document:*\n<{doc_link}|{doc.name or 'New ' + doc.doctype}>"},
                ],
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Type:*\n{doc.doctype}"},
                    {"type": "mrkdwn", "text": f"*Submitted by:*\n{submitter}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Reason:*\n{reason}"},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "Resolve the outstanding balance in ERPNext before this document can be submitted."},
                ],
            },
        ]

        slack_channel = frappe.conf.get("slack_channel") or "#ar-alerts"
        payload = json.dumps({"channel": slack_channel, "blocks": blocks}).encode("utf-8")
        req = urllib.request.Request(
            slack_webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "[crm_enforcement] Slack notification failed")
