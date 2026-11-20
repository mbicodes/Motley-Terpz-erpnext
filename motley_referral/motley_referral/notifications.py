"""Email (and Slack) notifications. Templates live in Email Template and are chosen in Referral Settings;
built-in English defaults are used when a template is not configured."""
import json

import frappe
from frappe import _
from frappe.utils import fmt_money, formatdate

BRAND = "Motley"

# event -> (settings field, audience, default subject, default message)
EVENTS = {
    "submitted_partner": ("tpl_submitted_partner", "partner", "We received your referral: {{ ref.business_name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>Thank you for submitting <b>{{ ref.business_name }}</b> ({{ ref.name }}). Our team will review it and confirm the outcome by email.</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "submitted_team": ("tpl_submitted_team", "team", "New referral to review: {{ ref.business_name }}",
        "<p>A new referral <b>{{ ref.name }}</b> was submitted by {{ partner.partner_name }}.</p><p>Business: {{ ref.business_name }}<br>Contact: {{ ref.contact_name or '-' }} ({{ ref.email }})<br>Duplicate check: {{ ref.duplicate_check_result or '-' }}</p><p>Open the Referral Program Board to acknowledge or reject it.</p>"),
    "acknowledged": ("tpl_acknowledged", "partner", "Referral acknowledged: {{ ref.business_name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>We are pleased to confirm that your referral <b>{{ ref.business_name }}</b> was acknowledged on {{ frappe.utils.formatdate(ref.acknowledged_on) }}. Our acknowledgement letter is attached.</p><p>Commission is earned on payments received on or after that date, from the month of the first qualifying payment.</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "rejected": ("tpl_rejected", "partner", "Referral update: {{ ref.business_name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>Thank you for your referral <b>{{ ref.business_name }}</b>. Unfortunately we are unable to accept it at this time.</p><p>Reason: {{ ref.rejection_reason }}{% if ref.rejection_note %} - {{ ref.rejection_note }}{% endif %}</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "first_payment": ("tpl_first_payment", "partner", "Your commission window has started: {{ ref.business_name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>We received the first qualifying payment from <b>{{ ref.business_name }}</b>. Your 24-month commission window started on {{ frappe.utils.formatdate(ref.commission_start_date) }}.</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "statement_approved": ("tpl_statement_approved", "partner", "Commission statement {{ statement.name }} is ready",
        "<p>Dear {{ partner.partner_name }},</p><p>Your commission statement for {{ period_label }} is ready. Net payable: <b>{{ net_payable }}</b>, due {{ frappe.utils.formatdate(statement.due_date) }}.</p><p>You can download it from the partner portal.</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "run_ready": ("tpl_run_ready", "team", "Commission statement run ready for review: {{ period }}",
        "<p>{{ count }} draft commission statement(s) were created for period {{ period }}. Please review and approve them on the Referral Program Board.</p>"),
    "statement_paid": ("tpl_statement_paid", "partner", "Payment sent: commission statement {{ statement.name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>Your commission for {{ period_label }} ({{ net_payable }}) has been paid. The statement is attached for your records.</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "month13": ("tpl_month13", "partner", "Your referral moves to the Year 2 rate: {{ ref.business_name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>The commission window for <b>{{ ref.business_name }}</b> has moved into Month 13. From now on the Year 2 rate of {{ partner.year2_rate }}% applies.</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "month24": ("tpl_month24", "partner", "Commission window ended: {{ ref.business_name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>The 24-month commission window for <b>{{ ref.business_name }}</b> has ended. No further commission is earned on this account. Thank you for your referral.</p><p>Kind regards,<br>Motley Referral Program</p>"),
    "overdue": ("tpl_overdue", "team", "Commission statement overdue: {{ statement.name }}",
        "<p>Statement <b>{{ statement.name }}</b> for {{ partner.partner_name }} ({{ net_payable }}) was due on {{ frappe.utils.formatdate(statement.due_date) }} and has not been paid.</p>"),
    "expired": ("tpl_expired", "partner", "Referral expired: {{ ref.business_name }}",
        "<p>Dear {{ partner.partner_name }},</p><p>Your referral <b>{{ ref.business_name }}</b> was not acknowledged within the review period and has expired. You are welcome to submit it again.</p><p>Kind regards,<br>Motley Referral Program</p>"),
}


def default_templates():
    return {k: (v[0], v[2], v[3]) for k, v in EVENTS.items()}


def _team_emails():
    roles = ["Referral Manager"]
    try:
        roles += [r.role for r in frappe.get_cached_doc("Referral Settings").get("acknowledger_roles") or []]
    except Exception:
        pass
    users = frappe.get_all("Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent")
    out = []
    for u in set(users):
        if u in ("Administrator", "Guest"):
            continue
        row = frappe.db.get_value("User", u, ["email", "enabled", "user_type"], as_dict=True)
        if row and row.enabled and row.user_type == "System User" and row.email:
            out.append(row.email)
    return out


def _render(event, ctx):
    field, _aud, subject, message = EVENTS[event]
    tpl_name = frappe.db.get_single_value("Referral Settings", field)
    if tpl_name and frappe.db.exists("Email Template", tpl_name):
        t = frappe.get_doc("Email Template", tpl_name)
        body = t.response_html if t.use_html else t.response
        return frappe.render_template(t.subject, ctx), frappe.render_template(body or message, ctx)
    return frappe.render_template(subject, ctx), frappe.render_template(message, ctx)


def _slack(text):
    url = frappe.db.get_single_value("Referral Settings", "slack_webhook_url")
    if not url:
        return
    try:
        import requests

        requests.post(url, data=json.dumps({"text": text}), headers={"Content-Type": "application/json"}, timeout=8)
    except Exception:
        frappe.log_error(title="Referral Slack", message=frappe.get_traceback())


def notify(event, **kwargs):
    """Never lets a mail problem (for example no outgoing account) break the business transaction."""
    try:
        _notify(event, **kwargs)
    except Exception:
        frappe.log_error(title=f"Referral notification: {event}", message=frappe.get_traceback())


def _notify(event, ref=None, statement=None, period=None, count=None, attach_pdf=False, attachments=None):
    audience = EVENTS[event][1]
    partner_name = (ref.referral_partner if ref else statement.referral_partner) if (ref or statement) else None
    partner = frappe.get_doc("Referral Partner", partner_name) if partner_name else None
    ctx = {
        "ref": ref, "statement": statement, "partner": partner, "period": period, "count": count,
        "period_label": None, "net_payable": None, "frappe": frappe,
    }
    if statement:
        y, m = statement.period.split("-")
        ctx["period_label"] = formatdate(f"{y}-{m}-01", "MMMM yyyy")
        ctx["net_payable"] = fmt_money(statement.net_payable, currency="USD")
    subject, message = _render(event, ctx)
    attachments = list(attachments or [])
    if attach_pdf and statement:
        attachments.append(frappe.attach_print(statement.doctype, statement.name, print_format="Referral Commission Statement"))
    if audience == "partner":
        if partner and partner.email:
            frappe.sendmail(recipients=[partner.email], subject=subject, message=message, attachments=attachments,
                            reference_doctype=(ref or statement).doctype, reference_name=(ref or statement).name)
    else:
        team = _team_emails()
        if team:
            frappe.sendmail(recipients=team, subject=subject, message=message,
                            reference_doctype=(ref or statement).doctype if (ref or statement) else None,
                            reference_name=(ref or statement).name if (ref or statement) else None)
        _slack(f"*{subject}*")
