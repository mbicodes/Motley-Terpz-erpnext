"""
AR Due Date Reminder Emails
Runs daily at 7 AM UTC.

Logic:
  1. For each payment terms template, fetch all outstanding invoices assigned to it.
  2. Calculate days until due date for each invoice / payment schedule row.
  3. If today's days-until-due matches the template's reminder schedule → include in email.
  4. Send one consolidated email to Osama + Muhammad with all triggered reminders.

Reminder schedules (days before due):
  NET30 / 50% down NET30   →  20, 15, 10, 5, 3, 2, 1
  NET15 / 50% down NET15   →  10, 5, 3, 2, 1
  NET7                     →   5, 3, 2, 1
  (any other / no terms)   →  10, 5, 3, 2, 1

Overdue invoices: if past due by 1–7 days, also included regardless of terms.
"""

import frappe
from frappe.utils import flt, getdate, nowdate

RECIPIENTS = ["osama.ahmad@alltechvirtual.com", "mbi@alltechvirtual.com"]

# ── Exact template name → reminder days before due ────────────────────────────
TERMS_SCHEDULE = {
    "NET30":          [20, 15, 10, 5, 3, 2, 1],
    "50% down NET30": [20, 15, 10, 5, 3, 2, 1],
    "NET15":          [10, 5, 3, 2, 1],
    "50% down NET15": [10, 5, 3, 2, 1],
    "NET7":           [5, 3, 2, 1],
}
# Invoices with no template or an unrecognised template are NOT reminded


# ── Invoice query (shared) ─────────────────────────────────────────────────────

_INVOICE_SELECT = """
    SELECT
        si.name,
        si.customer,
        si.customer_name,
        si.grand_total,
        si.outstanding_amount,
        si.due_date,
        si.posting_date,
        {terms_col}                                 AS terms,
        COALESCE(cl.custom_account_owner, '')       AS account_owner
    FROM `tabSales Invoice` si
    LEFT JOIN (
        SELECT
            custom_erp_customer,
            MAX(CASE WHEN custom_account_owner IS NOT NULL AND custom_account_owner != ''
                     THEN custom_account_owner END) AS custom_account_owner
        FROM `tabCRM Lead`
        WHERE custom_erp_customer IS NOT NULL AND custom_erp_customer != ''
        GROUP BY custom_erp_customer
    ) cl ON cl.custom_erp_customer = si.customer
    LEFT JOIN `tabCustomer` c ON c.name = si.customer
    WHERE si.docstatus = 1
      AND si.outstanding_amount > 0.01
      AND si.due_date IS NOT NULL
      {extra_where}
      AND si.customer NOT IN %(exc)s
      AND COALESCE(c.is_internal_customer, 0) = 0
      AND (c.represents_company IS NULL OR c.represents_company = '')
      AND si.customer NOT IN (SELECT name FROM `tabCompany`)
    ORDER BY si.due_date ASC
"""


def _fetch_invoices(excluded, require_terms=False, limit=None):
    terms_col = "COALESCE(si.payment_terms_template, '')"
    extra_where = ""
    if require_terms:
        extra_where = (
            "AND si.payment_terms_template IS NOT NULL "
            "AND si.payment_terms_template != ''"
        )
    sql = _INVOICE_SELECT.format(terms_col=terms_col, extra_where=extra_where)
    if limit:
        sql += f" LIMIT {int(limit)}"
    return frappe.db.sql(sql, {"exc": excluded}, as_dict=True)


# ── Payment schedule helper ────────────────────────────────────────────────────

def _build_ps_map(invoices):
    """
    Return {invoice_name: [{due_date, outstanding}, ...]} using FIFO allocation
    against si.outstanding_amount so that already-paid installments are excluded.

    ERPNext does not reliably update tabPayment Schedule.outstanding when payments
    are applied, so we recalculate: sort installments by due_date ASC, subtract
    the total amount paid (grand_total - outstanding_amount) from earliest first.
    """
    if not invoices:
        return {}

    inv_by_name = {inv.name: inv for inv in invoices}
    names = tuple(inv_by_name.keys()) or ("__none__",)

    ps_rows = frappe.db.sql("""
        SELECT ps.parent AS invoice_name, ps.due_date, ps.payment_amount
        FROM `tabPayment Schedule` ps
        WHERE ps.parenttype = 'Sales Invoice'
          AND ps.parent IN %(names)s
          AND ps.due_date IS NOT NULL
          AND ps.payment_amount > 0
        ORDER BY ps.parent, ps.due_date ASC
    """, {"names": names}, as_dict=True)

    # Group by invoice
    raw = {}
    for r in ps_rows:
        raw.setdefault(r.invoice_name, []).append(r)

    result = {}
    for inv_name, rows in raw.items():
        inv = inv_by_name.get(inv_name)
        if not inv:
            continue
        paid = max(flt(inv.grand_total) - flt(inv.outstanding_amount), 0)

        entries = []
        for row in sorted(rows, key=lambda r: getdate(str(r.due_date))):
            amt = flt(row.payment_amount)
            if paid >= amt:
                paid -= amt          # installment fully paid — skip
            elif paid > 0:
                entries.append({     # partially paid installment
                    "due_date":    getdate(str(row.due_date)),
                    "outstanding": amt - paid,
                })
                paid = 0
            else:
                entries.append({     # unpaid installment
                    "due_date":    getdate(str(row.due_date)),
                    "outstanding": amt,
                })

        if entries:
            result[inv_name] = entries

    return result


# ── Entry points ───────────────────────────────────────────────────────────────

def send_ar_reminders():
    """Scheduled entry point — called daily at 7 AM UTC."""
    today    = getdate(nowdate())
    triggers = _collect_triggers(today)

    if not triggers:
        return "No reminders due today."

    # Always send full picture to default recipients (management oversight)
    _send_email(triggers, today, RECIPIENTS)

    # Additionally send each Sales Person only their assigned invoices
    sp_count = _send_sp_emails(triggers, today)

    count = sum(len(v) for v in triggers.values())
    return (f"Sent reminders: {count} invoice(s) across {len(triggers)} term group(s) "
            f"to {RECIPIENTS}; {sp_count} personalised SP email(s) sent")


@frappe.whitelist()
def send_now():
    """Manual trigger from the ERPNext console."""
    return send_ar_reminders()


@frappe.whitelist()
def send_test():
    """
    Force-send a test reminder email with ALL outstanding invoices that have
    a payment terms template — ignores the day-schedule check.
    Useful for previewing the email format.
    """
    today    = getdate(nowdate())
    excluded = _excluded_customers()
    invoices = _fetch_invoices(excluded, require_terms=True, limit=50)

    if not invoices:
        return "No invoices with payment terms found to test with."

    ps_map = _build_ps_map(invoices)

    triggers = {}
    for inv in invoices:
        terms    = inv.terms
        schedule = TERMS_SCHEDULE.get(terms)
        if not schedule:
            continue

        due_entries = ps_map.get(inv.name) or [{
            "due_date":    getdate(str(inv.due_date)),
            "outstanding": flt(inv.outstanding_amount),
        }]

        for entry in due_entries:
            days_until = (entry["due_date"] - today).days
            triggers.setdefault(terms, []).append({
                "invoice":     inv.name,
                "customer":    inv.customer_name or inv.customer,
                "owner":       inv.account_owner or "",
                "terms":       terms,
                "due_date":    entry["due_date"],
                "outstanding": entry["outstanding"],
                "grand_total": float(inv.grand_total),
                "days":        days_until,
            })

    if not triggers:
        return "No invoices match a recognised payment terms schedule (NET7/NET15/NET30/50% variants)."

    # Default recipients always get full picture
    _send_email(triggers, today, RECIPIENTS)

    # Per-SP personalised emails (only their assigned invoices)
    sp_count = _send_sp_emails(triggers, today)

    count = sum(len(v) for v in triggers.values())
    return f"Test email sent: {count} invoice(s) to {RECIPIENTS}; {sp_count} SP email(s) sent"


# ── Core logic ─────────────────────────────────────────────────────────────────

def _collect_triggers(today):
    """
    Returns dict keyed by payment_terms_template →
    list of reminder dicts for invoices whose days-until-due matches the schedule.
    """
    excluded = _excluded_customers()
    invoices = _fetch_invoices(excluded)
    ps_map   = _build_ps_map(invoices)

    triggers = {}

    for inv in invoices:
        terms = inv.terms
        if not terms or terms not in TERMS_SCHEDULE:
            continue
        schedule = TERMS_SCHEDULE[terms]

        due_entries = ps_map.get(inv.name) or [{
            "due_date":    getdate(str(inv.due_date)),
            "outstanding": flt(inv.outstanding_amount),
        }]

        for entry in due_entries:
            days_until = (entry["due_date"] - today).days

            is_reminder_day = (days_until >= 0 and days_until in schedule)
            is_overdue      = (days_until < 0)

            if not (is_reminder_day or is_overdue):
                continue

            triggers.setdefault(terms, []).append({
                "invoice":     inv.name,
                "customer":    inv.customer_name or inv.customer,
                "owner":       inv.account_owner or "",
                "terms":       terms,
                "due_date":    entry["due_date"],
                "outstanding": entry["outstanding"],
                "grand_total": flt(inv.grand_total),
                "days":        days_until,
            })

    return triggers


def _excluded_customers():
    company_names = frappe.db.sql_list("SELECT name FROM `tabCompany`")
    internal = frappe.db.sql_list("""
        SELECT name FROM `tabCustomer`
        WHERE is_internal_customer = 1
           OR (represents_company IS NOT NULL AND represents_company != '')
    """)
    excluded = set(company_names) | set(internal)
    return tuple(excluded) if excluded else ("__none__",)


# ── Email builder ──────────────────────────────────────────────────────────────

def _get_sp_email_set():
    """Return set of lowercase emails registered on the Sales Person list."""
    rows = frappe.db.sql("""
        SELECT custom_email FROM `tabSales Person`
        WHERE custom_email IS NOT NULL AND custom_email != ''
    """, as_list=True)
    return {r[0].strip().lower() for r in rows}


def _send_sp_emails(triggers, today):
    """
    For each Sales Person whose email appears as an invoice owner in triggers,
    send them a personalised email containing only their assigned invoices.
    Returns count of SP emails sent.
    """
    sp_set = _get_sp_email_set()
    if not sp_set:
        return 0

    sp_buckets = {}
    for terms, rows in triggers.items():
        for row in rows:
            owner = (row.get("owner") or "").strip().lower()
            if owner and owner in sp_set:
                sp_buckets.setdefault(owner, {}).setdefault(terms, []).append(row)

    for sp_email, sp_triggers in sp_buckets.items():
        _send_email(sp_triggers, today, [sp_email])

    return len(sp_buckets)


def _send_email(triggers, today, recipients=None):
    if recipients is None:
        recipients = RECIPIENTS
    html = _build_html(triggers, today)
    frappe.sendmail(
        recipients=recipients,
        subject=f"AR Due Date Reminders — {today}",
        message=html,
        delayed=False,
    )


def _fmt(v):
    return "$ {:,.2f}".format(flt(v))


def _badge(days):
    if days < 0:
        n = abs(days)
        return (f'<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;'
                f'border-radius:8px;font-size:11px;font-weight:700;">'
                f'OVERDUE {n}d</span>')
    if days <= 2:
        return (f'<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;'
                f'border-radius:8px;font-size:11px;font-weight:700;">{days}d left</span>')
    if days <= 5:
        return (f'<span style="background:#fef3c7;color:#92400e;padding:2px 8px;'
                f'border-radius:8px;font-size:11px;font-weight:700;">{days}d left</span>')
    return (f'<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;'
            f'border-radius:8px;font-size:11px;font-weight:700;">{days}d left</span>')


def _build_html(triggers, today):
    total_invoices = sum(len(v) for v in triggers.values())
    total_amount   = sum(r["outstanding"] for rows in triggers.values() for r in rows)

    sections_html = ""
    for terms_label in sorted(triggers.keys()):
        rows  = triggers[terms_label]
        sched = TERMS_SCHEDULE.get(terms_label)
        sched_str = ", ".join(str(d) for d in sched) + " days" if sched else "10, 5, 3, 2, 1 days"
        display   = terms_label if terms_label != "__none__" else "No Payment Terms"

        rows_html = ""
        for r in sorted(rows, key=lambda x: x["due_date"]):
            rows_html += f"""<tr>
              <td style="padding:8px 12px;font-weight:600;border-bottom:1px solid #f1f5f9;">{r["customer"]}</td>
              <td style="padding:8px 12px;font-size:11px;color:#64748b;font-family:monospace;border-bottom:1px solid #f1f5f9;">{r["invoice"]}</td>
              <td style="padding:8px 12px;text-align:right;font-weight:700;color:#dc2626;border-bottom:1px solid #f1f5f9;">{_fmt(r["outstanding"])}</td>
              <td style="padding:8px 12px;text-align:center;border-bottom:1px solid #f1f5f9;">{r["due_date"]}</td>
              <td style="padding:8px 12px;text-align:center;border-bottom:1px solid #f1f5f9;">{_badge(r["days"])}</td>
            </tr>"""

        sections_html += f"""
        <div style="margin-bottom:22px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
            <span style="font-size:13px;font-weight:800;color:#1e293b;">{display}</span>
            <span style="font-size:11px;color:#64748b;background:#f1f5f9;padding:2px 8px;border-radius:6px;">
              Reminds at: {sched_str}
            </span>
            <span style="font-size:11px;color:#7c3aed;font-weight:700;margin-left:auto;">
              {len(rows)} invoice(s)
            </span>
          </div>
          <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;border:1px solid #e2e8f0;">
            <thead>
              <tr style="background:#f8fafc;">
                <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Customer</th>
                <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Invoice</th>
                <th style="padding:8px 12px;text-align:right;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Outstanding</th>
                <th style="padding:8px 12px;text-align:center;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Due Date</th>
                <th style="padding:8px 12px;text-align:center;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Status</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;color:#0f172a;margin:0;padding:20px;">
<div style="max-width:780px;margin:0 auto;">

  <div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;padding:28px 32px;margin-bottom:18px;text-align:center;">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:rgba(255,255,255,.4);margin-bottom:8px;">Motley Terpz &amp; TSBC Ranch</div>
    <div style="font-size:22px;font-weight:800;color:#fff;margin-bottom:8px;">AR Due Date Reminders</div>
    <div style="display:inline-block;background:rgba(255,255,255,.1);border-radius:20px;padding:5px 16px;color:rgba(255,255,255,.8);font-size:13px;">{today}</div>
  </div>

  <div style="display:flex;gap:12px;margin-bottom:18px;">
    <div style="flex:1;background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #e2e8f0;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Total Outstanding</div>
      <div style="font-size:20px;font-weight:800;color:#dc2626;">{_fmt(total_amount)}</div>
      <div style="font-size:11px;color:#94a3b8;">{total_invoices} invoice(s)</div>
    </div>
    <div style="flex:1;background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #e2e8f0;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Payment Term Groups</div>
      <div style="font-size:20px;font-weight:800;color:#7c3aed;">{len(triggers)}</div>
      <div style="font-size:11px;color:#94a3b8;">distinct term types triggered today</div>
    </div>
    <div style="flex:1;background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #e2e8f0;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Overdue</div>
      <div style="font-size:20px;font-weight:800;color:#dc2626;">{sum(1 for rows in triggers.values() for r in rows if r["days"] < 0)}</div>
      <div style="font-size:11px;color:#94a3b8;">past due · daily until paid</div>
    </div>
  </div>

  {sections_html}

  <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:16px;">
    Auto-generated daily by ERPNext · {today} · Do not reply.
  </div>
</div>
</body></html>"""
