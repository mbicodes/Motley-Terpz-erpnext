# -*- coding: utf-8 -*-
"""
Role-gated submit notifications.

On submit of a configured doctype, email the document's details to the users
holding that doctype's target role — but ONLY when the user who SUBMITTED the
document also holds one of those roles.

Everything (templates, roles, CC) lives here in code — there are intentionally
no Notification DB records, so nothing can be toggled into an ungated state and
there is no double-send. Wired via hooks.py: doc_events["*"]["on_submit"].

Gate: submitter must hold >= 1 of the doctype's roles, else no email is sent.
Recipients: all enabled non-system users holding any of those roles, CC Admin.
"""

import frappe

ADMIN_EMAIL = "admin@example.com"  # Administrator (placeholder address)
SYSTEM_USERS = {"Administrator", "Guest"}


# ---------------------------------------------------------------------------
# HTML template builders
# ---------------------------------------------------------------------------
def _row(label, val):
    return (
        '<tr>'
        f'<td style="padding:7px 0;color:#6b7280;border-bottom:1px solid #f1f5f9;width:42%;vertical-align:top;">{label}</td>'
        f'<td style="padding:7px 0;font-weight:600;border-bottom:1px solid #f1f5f9;color:#1f2933;">{val}</td>'
        '</tr>'
    )


def _rows(pairs):
    return "".join(_row(l, v) for l, v in pairs)


def _table(headers, body_loop):
    ths = "".join(
        f'<th style="padding:6px 8px;border-bottom:2px solid #e5e7eb;text-align:{align};font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#6b7280;">{txt}</th>'
        for txt, align in headers
    )
    return (
        '<div style="margin-top:22px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#6b7280;">Line Items</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:8px;">'
        f'<tr style="background:#f8fafc;">{ths}</tr>{body_loop}</table>'
    )


STD_ITEMS = _table(
    [("Item", "left"), ("Qty", "right"), ("Rate", "right"), ("Amount", "right")],
    '{% for it in doc.items %}'
    '<tr>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;">{{ it.item_code }}'
    '{% if it.item_name and it.item_name != it.item_code %}<div style="color:#94a3b8;font-size:11px;">{{ it.item_name }}</div>{% endif %}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ it.qty }} {{ it.uom or "" }}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ frappe.utils.fmt_money(it.rate, currency=doc.currency) }}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ frappe.utils.fmt_money(it.amount, currency=doc.currency) }}</td>'
    '</tr>'
    '{% endfor %}'
)

PE_REFS = (
    '{% if doc.references %}' +
    _table(
        [("Reference", "left"), ("Document", "left"), ("Allocated", "right")],
        '{% for r in doc.references %}'
        '<tr>'
        '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;">{{ r.reference_doctype }}</td>'
        '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;">{{ r.reference_name }}</td>'
        '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ frappe.utils.fmt_money(r.allocated_amount) }}</td>'
        '</tr>'
        '{% endfor %}'
    ) + '{% endif %}'
)

JE_ACCOUNTS = _table(
    [("Account", "left"), ("Debit", "right"), ("Credit", "right")],
    '{% for a in doc.accounts %}'
    '<tr>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;">{{ a.account }}'
    '{% if a.party %}<div style="color:#94a3b8;font-size:11px;">{{ a.party_type }}: {{ a.party }}</div>{% endif %}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ frappe.utils.fmt_money(a.debit_in_account_currency) }}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ frappe.utils.fmt_money(a.credit_in_account_currency) }}</td>'
    '</tr>'
    '{% endfor %}'
)

CE_ITEMS = _table(
    [("Conversion", "left"), ("Raw Material", "left"), ("Qty", "right"), ("Finished Good", "left"), ("Qty", "right")],
    '{% for it in doc.items %}'
    '<tr>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;">{{ it.conversion_type or "—" }}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;">{{ it.raw_material_1 or "—" }}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ it.qty_rm_1 or 0 }}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;">{{ it.finished_good_1 or "—" }}</td>'
    '<td style="padding:6px 8px;border-bottom:1px solid #f1f5f9;text-align:right;">{{ it.qty_fg_1 or 0 }}</td>'
    '</tr>'
    '{% endfor %}'
)


def _build_html(dt_label, rows_html, items_html):
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:660px;margin:0 auto;color:#1f2933;">'
        '<div style="background:#4f46e5;color:#ffffff;padding:18px 22px;border-radius:8px 8px 0 0;">'
        f'<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.85;">{dt_label} &middot; Submitted</div>'
        '<div style="font-size:22px;font-weight:700;margin-top:4px;">{{ doc.name }}</div>'
        '</div>'
        '<div style="border:1px solid #e5e7eb;border-top:none;padding:22px;border-radius:0 0 8px 8px;background:#ffffff;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:14px;">{rows_html}</table>'
        f'{items_html}'
        '<div style="margin-top:24px;">'
        '<a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}" '
        'style="background:#4f46e5;color:#ffffff;text-decoration:none;padding:11px 20px;border-radius:6px;font-size:14px;font-weight:600;display:inline-block;">'
        f'Open {dt_label} &rarr;</a>'
        '</div>'
        '<div style="margin-top:20px;font-size:12px;color:#9aa5b1;border-top:1px solid #eee;padding-top:12px;">'
        'Reference: <strong>{{ doc.doctype }}</strong> &mdash; <strong>{{ doc.name }}</strong>. '
        'Automated notification sent when the document was submitted.'
        '</div>'
        '</div></div>'
    )


# ---------------------------------------------------------------------------
# Per-doctype config: label, target roles, field rows, line-items block
# ---------------------------------------------------------------------------
_CONFIG = [
    ("Purchase Order", "Purchase Order", ["Jamie Hawk - Consolidated"], [
        ("Supplier", "{{ doc.supplier_name or doc.supplier }}"),
        ("Order Date", "{{ frappe.utils.formatdate(doc.transaction_date) }}"),
        ("Company", "{{ doc.company }}"), ("Total Qty", "{{ doc.total_qty }}"),
        ("Grand Total", "{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}"),
        ("Status", "{{ doc.status }}")], STD_ITEMS),
    ("Purchase Receipt", "Purchase Receipt", ["Jamie Hawk - Consolidated"], [
        ("Supplier", "{{ doc.supplier_name or doc.supplier }}"),
        ("Posting Date", "{{ frappe.utils.formatdate(doc.posting_date) }}"),
        ("Company", "{{ doc.company }}"), ("Total Qty", "{{ doc.total_qty }}"),
        ("Grand Total", "{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}"),
        ("Is Return", "{{ 'Yes' if doc.is_return else 'No' }}")], STD_ITEMS),
    ("Purchase Invoice", "Purchase Invoice", ["Accounts Manager", "Jamie Hawk - Consolidated"], [
        ("Supplier", "{{ doc.supplier_name or doc.supplier }}"),
        ("Posting Date", "{{ frappe.utils.formatdate(doc.posting_date) }}"),
        ("Due Date", "{{ frappe.utils.formatdate(doc.due_date) }}"),
        ("Supplier Invoice No", "{{ doc.bill_no or '—' }}"),
        ("Grand Total", "{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}"),
        ("Outstanding", "{{ frappe.utils.fmt_money(doc.outstanding_amount, currency=doc.currency) }}"),
        ("Status", "{{ doc.status }}")], STD_ITEMS),
    ("Payment Entry", "Payment Entry", ["Accounts Manager"], [
        ("Payment Type", "{{ doc.payment_type }}"),
        ("Party", "{{ doc.party_name or doc.party }} ({{ doc.party_type }})"),
        ("Posting Date", "{{ frappe.utils.formatdate(doc.posting_date) }}"),
        ("Mode of Payment", "{{ doc.mode_of_payment or '—' }}"),
        ("Paid Amount", "{{ frappe.utils.fmt_money(doc.paid_amount) }}"),
        ("Received Amount", "{{ frappe.utils.fmt_money(doc.received_amount) }}"),
        ("Reference No", "{{ doc.reference_no or '—' }}"),
        ("Company", "{{ doc.company }}")], PE_REFS),
    ("Journal Entry", "Journal Entry", ["Accounts Manager"], [
        ("Voucher Type", "{{ doc.voucher_type }}"),
        ("Posting Date", "{{ frappe.utils.formatdate(doc.posting_date) }}"),
        ("Company", "{{ doc.company }}"),
        ("Total Debit", "{{ frappe.utils.fmt_money(doc.total_debit) }}"),
        ("Total Credit", "{{ frappe.utils.fmt_money(doc.total_credit) }}"),
        ("Remark", "{{ doc.user_remark or '—' }}")], JE_ACCOUNTS),
    ("Sales Order", "Sales Order", ["Nikki M - Consolidated"], [
        ("Customer", "{{ doc.customer_name or doc.customer }}"),
        ("Order Date", "{{ frappe.utils.formatdate(doc.transaction_date) }}"),
        ("Delivery Date", "{{ frappe.utils.formatdate(doc.delivery_date) }}"),
        ("Company", "{{ doc.company }}"), ("Total Qty", "{{ doc.total_qty }}"),
        ("Grand Total", "{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}"),
        ("Status", "{{ doc.status }}")], STD_ITEMS),
    ("Delivery Note", "Delivery Note", ["Nikki M - Consolidated"], [
        ("Customer", "{{ doc.customer_name or doc.customer }}"),
        ("Posting Date", "{{ frappe.utils.formatdate(doc.posting_date) }}"),
        ("Company", "{{ doc.company }}"), ("Total Qty", "{{ doc.total_qty }}"),
        ("Grand Total", "{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}")], STD_ITEMS),
    ("Sales Invoice", "Sales Invoice", ["Nikki M - Consolidated"], [
        ("Customer", "{{ doc.customer_name or doc.customer }}"),
        ("Posting Date", "{{ frappe.utils.formatdate(doc.posting_date) }}"),
        ("Due Date", "{{ frappe.utils.formatdate(doc.due_date) }}"),
        ("Grand Total", "{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}"),
        ("Outstanding", "{{ frappe.utils.fmt_money(doc.outstanding_amount, currency=doc.currency) }}"),
        ("Status", "{{ doc.status }}")], STD_ITEMS),
    ("Conversion Entry", "Conversion Entry", ["Nikki M - Consolidated"], [
        ("Customer", "{{ doc.customer or '—' }}"),
        ("Posting Date", "{{ frappe.utils.formatdate(doc.posting_date) }}"),
        ("Company", "{{ doc.company }}"), ("Reason", "{{ doc.reasons or '—' }}"),
        ("Partner", "{{ doc.partners or '—' }}"), ("Sales Order", "{{ doc.sales_order or '—' }}"),
        ("Workstation", "{{ doc.workstation or '—' }}"),
        ("Total Time (min)", "{{ doc.total_time_in_minutes or 0 }}")], CE_ITEMS),
]

# doctype -> {"subject", "message", "roles"}
TEMPLATES = {
    dt: {
        "subject": f"[Submitted] {label}: {{{{ doc.name }}}}",
        "message": _build_html(label, _rows(rows), items),
        "roles": roles,
    }
    for dt, label, roles, rows, items in _CONFIG
}


# ---------------------------------------------------------------------------
# Hook entry point
# ---------------------------------------------------------------------------
def notify_on_submit(doc, method=None):
    """doc_events['*']['on_submit'] — runs on every submit; gated by submitter role."""
    tpl = TEMPLATES.get(doc.doctype)
    if not tpl:
        return

    # ---- THE GATE: submitting user must hold at least one target role ----
    if set(frappe.get_roles(frappe.session.user)).isdisjoint(tpl["roles"]):
        return

    recipients = _emails_for_roles(tpl["roles"])
    cc = [ADMIN_EMAIL]
    if not recipients:  # no role holders -> send to Admin directly
        recipients, cc = cc, []
    if not recipients:
        return

    ctx = {"doc": doc}
    try:
        frappe.sendmail(
            recipients=recipients,
            cc=cc or None,
            subject=frappe.render_template(tpl["subject"], ctx),
            message=frappe.render_template(tpl["message"], ctx),
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"Role-gated submit notify failed for {doc.doctype} {doc.name}",
        )


def _emails_for_roles(roles):
    """Emails of enabled, non-system users holding any of the given roles."""
    users = frappe.get_all(
        "Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent"
    )
    if not users:
        return []
    rows = frappe.get_all(
        "User", filters={"name": ["in", list(set(users))], "enabled": 1},
        fields=["email", "name"],
    )
    return sorted({r.email for r in rows if r.email and r.name not in SYSTEM_USERS})
