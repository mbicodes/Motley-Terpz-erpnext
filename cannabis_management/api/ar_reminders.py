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
DEFAULT_SCHEDULE = [10, 5, 3, 2, 1]   # invoices with no / unrecognised payment terms


# ── Entry points ───────────────────────────────────────────────────────────────

def send_ar_reminders():
    """Scheduled entry point — called daily at 7 AM UTC."""
    today    = getdate(nowdate())
    triggers = _collect_triggers(today)

    if not triggers:
        return "No reminders due today."

    _send_email(triggers, today)
    count = sum(len(v) for v in triggers.values())
    return f"Sent reminders: {count} invoice(s) across {len(triggers)} term group(s) to {RECIPIENTS}"


@frappe.whitelist()
def send_now():
    """Manual trigger from the ERPNext console."""
    return send_ar_reminders()


# ── Core logic ─────────────────────────────────────────────────────────────────

def _collect_triggers(today):
    """
    Returns dict keyed by payment_terms_template (or '__none__') →
    list of reminder dicts for invoices whose days-until-due matches the schedule.
    """
    excluded = _excluded_customers()

    # Fetch all outstanding invoices
    invoices = frappe.db.sql("""
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.grand_total,
            si.outstanding_amount,
            si.due_date,
            si.posting_date,
            COALESCE(si.payment_terms_template, '') AS terms,
            COALESCE(cl.custom_account_owner, '')   AS account_owner
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCRM Lead` cl ON cl.custom_erp_customer = si.customer
        LEFT JOIN `tabCustomer` c  ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND si.due_date IS NOT NULL
          AND si.customer NOT IN %(exc)s
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
          AND si.customer NOT IN (SELECT name FROM `tabCompany`)
        ORDER BY si.due_date ASC
    """, {"exc": excluded}, as_dict=True)

    # Fetch payment schedule rows for split-term invoices
    ps_rows = frappe.db.sql("""
        SELECT ps.parent AS invoice_name, ps.due_date, ps.outstanding
        FROM `tabPayment Schedule` ps
        JOIN `tabSales Invoice` si ON si.name = ps.parent
        WHERE si.docstatus = 1 AND ps.outstanding > 0.01 AND ps.due_date IS NOT NULL
    """, as_dict=True)
    ps_map = {}
    for r in ps_rows:
        ps_map.setdefault(r.invoice_name, []).append(r)

    # Build triggers grouped by terms template
    triggers = {}   # {terms_label: [reminder_dict, ...]}

    for inv in invoices:
        terms     = inv.terms or "__none__"
        schedule  = TERMS_SCHEDULE.get(inv.terms) or DEFAULT_SCHEDULE

        # Determine due dates to evaluate
        due_entries = []
        if inv.name in ps_map:
            for ps in ps_map[inv.name]:
                if flt(ps.outstanding) > 0:
                    due_entries.append({
                        "due_date":    getdate(str(ps.due_date)),
                        "outstanding": flt(ps.outstanding),
                    })
        if not due_entries:
            due_entries.append({
                "due_date":    getdate(str(inv.due_date)),
                "outstanding": flt(inv.outstanding_amount),
            })

        for entry in due_entries:
            days_until = (entry["due_date"] - today).days

            # Check: either matches reminder schedule, or is 1-7 days overdue
            is_reminder_day = (days_until >= 0 and days_until in schedule)
            is_overdue      = (days_until < 0 and abs(days_until) <= 7)

            if not (is_reminder_day or is_overdue):
                continue

            owner = inv.account_owner or ""
            triggers.setdefault(terms, []).append({
                "invoice":     inv.name,
                "customer":    inv.customer_name or inv.customer,
                "owner":       owner,
                "terms":       inv.terms or "No Terms",
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

def _send_email(triggers, today):
    html = _build_html(triggers, today)
    frappe.sendmail(
        recipients=RECIPIENTS,
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
            owner_label = r["owner"].split("@")[0].title() if "@" in r["owner"] else (r["owner"] or "—")
            rows_html += f"""<tr>
              <td style="padding:8px 12px;font-weight:600;border-bottom:1px solid #f1f5f9;">{r["customer"]}</td>
              <td style="padding:8px 12px;font-size:11px;color:#64748b;font-family:monospace;border-bottom:1px solid #f1f5f9;">{r["invoice"]}</td>
              <td style="padding:8px 12px;font-size:12px;color:#64748b;border-bottom:1px solid #f1f5f9;">{owner_label}</td>
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
                <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;">Rep</th>
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
      <div style="font-size:11px;color:#94a3b8;">past due date</div>
    </div>
  </div>

  {sections_html}

  <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:16px;">
    Auto-generated daily by ERPNext · {today} · Do not reply.
  </div>
</div>
</body></html>"""
