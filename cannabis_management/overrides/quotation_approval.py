"""
Quotation Approval — discount-threshold routing.

Mirrors the Sales Order approval pattern (custom_approval_status + doc hooks)
rather than the rigid native Workflow doctype, and extends it to tiered routing.

Routing (effective overall discount off list price):
    < 10%   → auto-approved (rep can submit/send)
  10–20%   → Sales Manager approval
   ≥ 20%   → Finance approval (Finance Manager / Accounts Manager)

COD customers and customers past terms (oldest unpaid invoice > 30 days) route
to Finance regardless of discount depth.

Approver eligibility:
  • Sales Manager tier — Sales Manager, Finance Manager, Accounts Manager,
    Super Admin, Administrator.
  • Finance tier — Finance Manager, Accounts Manager, Super Admin, Administrator.

Notifications: approver group (email + Slack) when a quote enters approval;
creator (email) on approve/reject; rejection reason is also posted to the linked
CRM Deal timeline.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

# ── Thresholds & roles ──────────────────────────────────────────────────────
AUTO_APPROVE_BELOW = 10.0      # < 10%  → no approval needed
FINANCE_AT_OR_ABOVE = 20.0     # ≥ 20%  → Finance; [10, 20) → Sales Manager
PAST_DUE_DAYS = 30             # oldest unpaid invoice older than this → Finance

LEVEL_MANAGER = "Sales Manager"
LEVEL_FINANCE = "Finance"

MANAGER_APPROVER_ROLES = {"Sales Manager", "Finance Manager", "Accounts Manager"}
FINANCE_APPROVER_ROLES = {"Finance Manager", "Accounts Manager"}
SUPER_ROLES = {"Super Admin"}

SLACK_CHANNEL = "#quotation-approvals"


# ── Document hooks ──────────────────────────────────────────────────────────

def validate(doc, method=None):
    """Compute discount, decide required approval level, set status."""
    eff = _effective_discount_pct(doc)
    doc.custom_discount_pct_effective = eff
    level = _required_level(doc, eff)
    doc.custom_required_approval_level = level or ""

    if not level:
        # No approval needed — auto-approve so the rep can submit/send.
        doc.custom_approval_status = "Approved"
        return

    status = doc.custom_approval_status

    if status == "Approved":
        # Guard against a rep deepening the discount after approval.
        approved_disc = flt(doc.get("custom_approved_discount"))
        deepened = eff > approved_disc + 0.01
        escalated = _level_rank(level) > _level_rank(doc.get("custom_approved_level"))
        if deepened or escalated:
            doc.custom_approval_status = "Pending Approval"
            doc._notify_approvers = True
        return

    # Blank, Pending or Rejected → (re)enter the approval queue.
    if status != "Pending Approval":
        doc.custom_approval_status = "Pending Approval"
        doc.custom_rejection_reason = None
        doc._notify_approvers = True


def on_update(doc, method=None):
    if getattr(doc, "_notify_approvers", False):
        _notify_approvers(doc)


def before_submit(doc, method=None):
    """Block submission until approved. An eligible approver who submits the
    quote directly is treated as giving approval (mirrors the SO/HOO pattern)."""
    eff = _effective_discount_pct(doc)
    level = _required_level(doc, eff)
    if not level:
        return
    if doc.custom_approval_status == "Approved":
        return
    if _can_approve(level):
        _stamp_approved(doc, eff, level)
        return
    frappe.throw(
        _("This quotation needs <b>{0}</b> approval before it can be submitted.").format(level),
        title=_("Approval Required"),
    )


# ── Approve / Reject endpoints (called from the Quotation form buttons) ──────

@frappe.whitelist()
def approve_quotation(name):
    doc = frappe.get_doc("Quotation", name)
    level = doc.custom_required_approval_level or _required_level(doc, _effective_discount_pct(doc))
    if not _can_approve(level):
        frappe.throw(_("You are not permitted to approve this quotation."), frappe.PermissionError)

    eff = flt(doc.custom_discount_pct_effective)
    doc.db_set("custom_approval_status", "Approved", update_modified=True)
    doc.db_set("custom_approved_discount", eff, update_modified=False)
    doc.db_set("custom_approved_level", level, update_modified=False)
    doc.db_set("custom_approved_by", frappe.session.user, update_modified=False)
    doc.db_set("custom_approved_on", now_datetime(), update_modified=False)
    doc.db_set("custom_rejection_reason", None, update_modified=False)
    _notify_creator(doc, approved=True)
    return "approved"


@frappe.whitelist()
def reject_quotation(name, reason=None):
    if not reason or not str(reason).strip():
        frappe.throw(_("A rejection reason is required."))
    reason = str(reason).strip()

    doc = frappe.get_doc("Quotation", name)
    level = doc.custom_required_approval_level or _required_level(doc, _effective_discount_pct(doc))
    if not _can_approve(level):
        frappe.throw(_("You are not permitted to reject this quotation."), frappe.PermissionError)

    doc.db_set("custom_approval_status", "Rejected", update_modified=True)
    doc.db_set("custom_rejection_reason", reason, update_modified=False)
    doc.db_set("custom_approved_by", frappe.session.user, update_modified=False)
    doc.db_set("custom_approved_on", now_datetime(), update_modified=False)
    _notify_creator(doc, approved=False, reason=reason)
    _post_to_deal_timeline(doc, reason)
    return "rejected"


@frappe.whitelist()
def get_deal_quotations(deal):
    """Quotations linked to a CRM Deal, with approval state and whether the
    current user may approve each one. Used by the CRM Deal page panel."""
    if not deal or not frappe.db.exists("CRM Deal", deal):
        return []
    if not frappe.has_permission("CRM Deal", "read", deal):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    rows = frappe.get_all(
        "Quotation",
        filters={"crm_deal": deal},
        fields=[
            "name", "status", "docstatus", "grand_total", "currency", "transaction_date",
            "custom_approval_status", "custom_required_approval_level",
            "custom_discount_pct_effective", "custom_rejection_reason",
            "custom_approved_by", "custom_approved_on",
        ],
        order_by="modified desc",
    )
    for r in rows:
        r["can_approve"] = bool(
            r.get("custom_approval_status") == "Pending Approval"
            and _can_approve(r.get("custom_required_approval_level"))
        )
    return rows


@frappe.whitelist()
def get_my_pending_approvals():
    """Quotations awaiting approval that the current user is allowed to approve.
    Powers the CRM 'Approvals' queue page."""
    rows = frappe.get_all(
        "Quotation",
        filters={"custom_approval_status": "Pending Approval", "docstatus": 0},
        fields=[
            "name", "party_name", "customer_name", "grand_total", "currency",
            "transaction_date", "crm_deal", "owner",
            "custom_required_approval_level", "custom_discount_pct_effective",
        ],
        order_by="modified desc",
    )
    out = []
    for r in rows:
        if _can_approve(r.get("custom_required_approval_level")):
            r["owner_fullname"] = frappe.utils.get_fullname(r.get("owner"))
            out.append(r)
    return out


# ── Core logic ──────────────────────────────────────────────────────────────

def _effective_discount_pct(doc):
    """Overall discount off list price, capturing per-item AND header discounts.

    base   = Σ(price_list_rate × qty)      (undiscounted list value)
    final  = net_total                     (after item + additional discount, pre-tax)
    """
    base = 0.0
    for it in (doc.items or []):
        plr = flt(it.price_list_rate)
        if plr <= 0:
            plr = flt(it.rate)  # no price list → can't see line discount, degrade safely
        base += plr * flt(it.qty)
    if base <= 0:
        return 0.0
    final = flt(doc.net_total) if doc.net_total else flt(doc.total)
    pct = (base - final) / base * 100.0
    return round(max(pct, 0.0), 2)


def _required_level(doc, eff):
    customer = _resolve_customer(doc)
    if customer and _is_high_risk_customer(customer):
        return LEVEL_FINANCE
    if eff >= FINANCE_AT_OR_ABOVE:
        return LEVEL_FINANCE
    if eff >= AUTO_APPROVE_BELOW:
        return LEVEL_MANAGER
    return ""


def _level_rank(level):
    return {"": 0, None: 0, LEVEL_MANAGER: 1, LEVEL_FINANCE: 2}.get(level, 0)


def _can_approve(level, user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    if roles & SUPER_ROLES:
        return True
    if level == LEVEL_FINANCE:
        return bool(roles & FINANCE_APPROVER_ROLES)
    if level == LEVEL_MANAGER:
        return bool(roles & MANAGER_APPROVER_ROLES)
    return False


def _stamp_approved(doc, eff, level):
    doc.custom_approval_status = "Approved"
    doc.custom_approved_discount = eff
    doc.custom_approved_level = level
    doc.custom_approved_by = frappe.session.user
    doc.custom_approved_on = now_datetime()


def _resolve_customer(doc):
    if doc.get("quotation_to") == "Customer" and doc.get("party_name"):
        return doc.party_name
    if doc.get("customer"):
        return doc.customer
    deal = doc.get("crm_deal")
    if deal and frappe.db.exists("CRM Deal", deal):
        if frappe.db.has_column("CRM Deal", "customer"):
            return frappe.db.get_value("CRM Deal", deal, "customer")
    return None


def _is_high_risk_customer(customer):
    """COD flag or past terms (oldest unpaid invoice older than PAST_DUE_DAYS)."""
    pt = frappe.db.get_value("Customer", customer, "payment_terms") or ""
    if "cod" in pt.lower() or "cash on delivery" in pt.lower():
        return True
    if frappe.db.exists("DocType", "CRM Lead") and frappe.db.has_column("CRM Lead", "custom_erp_customer"):
        cod = frappe.db.get_value("CRM Lead", {"custom_erp_customer": customer}, "custom_cod_flag")
        if cod:
            return True
    row = frappe.db.sql(
        """
        SELECT COALESCE(MAX(DATEDIFF(CURDATE(), due_date)), 0) AS aging
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0.01
        """,
        customer,
        as_dict=True,
    )
    if row and int(row[0].aging or 0) > PAST_DUE_DAYS:
        return True
    return False


# ── Notifications ────────────────────────────────────────────────────────────

def _approver_users(level):
    """Enabled users who may approve the given tier (excludes Administrator)."""
    roles = (FINANCE_APPROVER_ROLES if level == LEVEL_FINANCE else MANAGER_APPROVER_ROLES) | SUPER_ROLES
    users = frappe.get_all(
        "Has Role",
        filters={"parenttype": "User", "role": ["in", list(roles)]},
        pluck="parent",
        distinct=True,
    )
    enabled = []
    for u in users:
        if u in ("Administrator", "Guest"):
            continue
        if frappe.db.get_value("User", u, "enabled"):
            enabled.append(u)
    return sorted(set(enabled))


def _approver_emails(level):
    emails = []
    for u in _approver_users(level):
        email = frappe.db.get_value("User", u, "email")
        if email:
            emails.append(email)
    return sorted(set(emails))


def _notify_inapp(users, subject, doc):
    """Create desk in-app notifications (the bell) for the given users."""
    for u in users:
        try:
            frappe.get_doc({
                "doctype": "Notification Log",
                "for_user": u,
                "type": "Alert",
                "document_type": "Quotation",
                "document_name": doc.name,
                "subject": subject,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "[quotation_approval] in-app notification failed")


def _quote_url(name):
    return f"{frappe.utils.get_url()}/app/quotation/{name}"


def _notify_approvers(doc):
    level = doc.custom_required_approval_level
    if not level:
        return
    users = _approver_users(level)
    emails = _approver_emails(level)
    eff = flt(doc.custom_discount_pct_effective)
    url = _quote_url(doc.name)
    creator = frappe.utils.get_fullname(doc.owner)

    _notify_inapp(
        users,
        _("Quotation {0} needs your approval ({1}, {2:.0f}% off)").format(doc.name, level, eff),
        doc,
    )

    if emails:
        try:
            frappe.sendmail(
                recipients=emails,
                subject=_("Quotation {0} needs {1} approval").format(doc.name, level),
                message=f"""
                    <p>Quotation <strong>{doc.name}</strong> for
                    <strong>{doc.get('customer_name') or doc.get('party_name') or ''}</strong>
                    was submitted by <strong>{creator}</strong> and needs <strong>{level}</strong> approval.</p>
                    <p>Effective discount: <strong>{eff:.2f}%</strong> ·
                    Grand total: <strong>{frappe.format(doc.grand_total, {'fieldtype': 'Currency'})}</strong></p>
                    <p><a href="{url}">Open the quotation to approve or reject</a></p>
                """,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "[quotation_approval] approver email failed")

    # Slack alert disabled for now — live site_config points slack_webhook_url at
    # the conversions-motley webhook, so this was posting to the wrong channel.
    # Re-enable once a dedicated webhook/channel is configured.
    # _send_slack(
    #     header="🧾 Quotation Pending Approval",
    #     fields=[
    #         ("Quotation", f"<{url}|{doc.name}>"),
    #         ("Customer", doc.get("customer_name") or doc.get("party_name") or "—"),
    #         ("Discount", f"{eff:.2f}%"),
    #         ("Needs", f"{level} approval"),
    #         ("Submitted by", creator),
    #     ],
    #     context="Open the quotation and click Approve or Reject.",
    # )


def _notify_creator(doc, approved, reason=None):
    creator_email = frappe.db.get_value("User", doc.owner, "email")
    if not creator_email:
        return
    actor = frappe.utils.get_fullname(frappe.session.user)
    url = _quote_url(doc.name)
    if approved:
        subject = _("Quotation {0} — Approved").format(doc.name)
        body = f"""<p>Your quotation <strong>{doc.name}</strong> was
            <strong>approved</strong> by {actor}. You can now send it / convert it to an order.</p>
            <p><a href="{url}">Open quotation</a></p>"""
    else:
        subject = _("Quotation {0} — Rejected").format(doc.name)
        body = f"""<p>Your quotation <strong>{doc.name}</strong> was
            <strong>rejected</strong> by {actor}.</p>
            <p><strong>Reason:</strong> {frappe.utils.escape_html(reason or '')}</p>
            <p><a href="{url}">Open quotation</a></p>"""
    try:
        frappe.sendmail(recipients=[creator_email], subject=subject, message=body)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[quotation_approval] creator email failed")

    verb = "approved" if approved else "rejected"
    _notify_inapp([doc.owner], _("Quotation {0} was {1}").format(doc.name, verb), doc)


def _post_to_deal_timeline(doc, reason):
    deal = doc.get("crm_deal")
    if not deal or not frappe.db.exists("CRM Deal", deal):
        return
    actor = frappe.utils.get_fullname(frappe.session.user)
    try:
        frappe.get_doc("CRM Deal", deal).add_comment(
            "Comment",
            text=_("Quotation {0} rejected by {1}. Reason: {2}").format(doc.name, actor, reason),
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[quotation_approval] deal timeline comment failed")


def _send_slack(header, fields, context=None):
    try:
        import json
        import urllib.request

        webhook = frappe.conf.get("slack_webhook_url")
        if not webhook:
            return
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*{k}:*\n{v}"} for k, v in fields
            ]},
        ]
        if context:
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": context}]})
        channel = frappe.conf.get("slack_channel") or SLACK_CHANNEL
        payload = json.dumps({"channel": channel, "blocks": blocks}).encode("utf-8")
        req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[quotation_approval] Slack notification failed")


# ── Custom field installer (idempotent) ──────────────────────────────────────

def install_quotation_approval_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    anchor = "crm_deal" if frappe.db.has_column("Quotation", "crm_deal") else "customer_name"
    fields = {
        "Quotation": [
            {"fieldname": "custom_approval_section", "fieldtype": "Section Break",
             "label": "Quote Approval", "insert_after": anchor},
            {"fieldname": "custom_approval_status", "fieldtype": "Select",
             "label": "Approval Status", "options": "\nPending Approval\nApproved\nRejected",
             "read_only": 1, "in_list_view": 1, "in_standard_filter": 1, "allow_on_submit": 1,
             "insert_after": "custom_approval_section"},
            {"fieldname": "custom_required_approval_level", "fieldtype": "Select",
             "label": "Required Approval", "options": "\nSales Manager\nFinance",
             "read_only": 1, "insert_after": "custom_approval_status"},
            {"fieldname": "custom_discount_pct_effective", "fieldtype": "Percent",
             "label": "Effective Discount %", "read_only": 1,
             "insert_after": "custom_required_approval_level"},
            {"fieldname": "custom_rejection_reason", "fieldtype": "Small Text",
             "label": "Rejection Reason", "read_only": 1, "allow_on_submit": 1,
             "insert_after": "custom_discount_pct_effective"},
            {"fieldname": "custom_col_break_approval", "fieldtype": "Column Break",
             "insert_after": "custom_rejection_reason"},
            {"fieldname": "custom_approved_by", "fieldtype": "Link", "options": "User",
             "label": "Approved / Rejected By", "read_only": 1, "allow_on_submit": 1,
             "insert_after": "custom_col_break_approval"},
            {"fieldname": "custom_approved_on", "fieldtype": "Datetime",
             "label": "Approved / Rejected On", "read_only": 1, "allow_on_submit": 1,
             "insert_after": "custom_approved_by"},
            # Internal bookkeeping (hidden)
            {"fieldname": "custom_approved_discount", "fieldtype": "Float",
             "label": "Approved Discount", "read_only": 1, "hidden": 1, "allow_on_submit": 1,
             "insert_after": "custom_approved_on"},
            {"fieldname": "custom_approved_level", "fieldtype": "Data",
             "label": "Approved Level", "read_only": 1, "hidden": 1, "allow_on_submit": 1,
             "insert_after": "custom_approved_discount"},
        ]
    }
    create_custom_fields(fields, ignore_validate=True)
    frappe.db.commit()
