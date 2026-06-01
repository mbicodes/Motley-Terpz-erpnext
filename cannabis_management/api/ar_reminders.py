"""
AR Due Date Reminder Emails
Runs daily — checks all outstanding invoices and sends reminders to
Osama and Muhammad at specific day-before-due checkpoints.

Reminder schedules (days before due date):
  30-day terms (NET30 / 50% down NET30):  20, 15, 10, 5, 3, 2, 1
  15-day terms (NET15 / 50% down NET15):  10, 5, 3, 2, 1
   7-day terms (NET7):                     5, 3, 2, 1
  Unknown / other:                        10, 5, 3, 2, 1

Emails continue each checkpoint until the invoice is fully paid.
"""

import frappe
from frappe.utils import flt, getdate, nowdate, add_days

RECIPIENTS = ["osama.ahmad@alltechvirtual.com", "mbi@alltechvirtual.com"]

# days-before-due → reminder schedule based on payment terms category
SCHEDULES = {
    "net30": [20, 15, 10, 5, 3, 2, 1],
    "net15": [10, 5, 3, 2, 1],
    "net7":  [5, 3, 2, 1],
    "other": [10, 5, 3, 2, 1],
}


def _classify_terms(template_name, credit_days=None):
    """Return schedule key based on payment terms template name or credit days."""
    if template_name:
        tl = template_name.lower()
        if "30" in tl:
            return "net30"
        if "15" in tl:
            return "net15"
        if "7" in tl:
            return "net7"
    if credit_days is not None:
        if credit_days >= 25:
            return "net30"
        if credit_days >= 12:
            return "net15"
        if credit_days >= 5:
            return "net7"
    return "other"


def send_ar_reminders():
    """
    Daily scheduled entry point.
    Checks all outstanding Sales Invoices and sends reminders on the right days.
    """
    today = getdate(nowdate())

    # Fetch all outstanding invoices with their payment schedule due dates
    invoices = frappe.db.sql("""
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.grand_total,
            si.outstanding_amount,
            si.due_date,
            si.posting_date,
            si.payment_terms_template,
            COALESCE(cl.custom_account_owner, '') AS account_owner
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCRM Lead` cl ON cl.custom_erp_customer = si.customer
        LEFT JOIN `tabCustomer` c  ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND si.due_date IS NOT NULL
          AND si.customer NOT IN (SELECT name FROM `tabCompany`)
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
        ORDER BY si.due_date ASC
    """, as_dict=True)

    # Also pull payment schedule rows (for split-term invoices)
    schedule_rows = frappe.db.sql("""
        SELECT ps.parent AS invoice_name, ps.due_date, ps.outstanding AS outstanding_amount,
               ps.payment_amount
        FROM `tabPayment Schedule` ps
        JOIN `tabSales Invoice` si ON si.name = ps.parent
        WHERE si.docstatus = 1
          AND ps.outstanding > 0.01
          AND ps.due_date IS NOT NULL
        ORDER BY ps.due_date ASC
    """, as_dict=True)

    # Map invoice name → payment schedule rows
    ps_map = {}
    for r in schedule_rows:
        ps_map.setdefault(r.invoice_name, []).append(r)

    reminders = []  # collect all due reminders

    for inv in invoices:
        # Determine which due dates to check for this invoice
        due_dates_to_check = []

        if inv.name in ps_map:
            # Use per-installment due dates
            for ps in ps_map[inv.name]:
                due_dates_to_check.append({
                    "due_date": getdate(str(ps.due_date)),
                    "outstanding": flt(ps.outstanding_amount),
                })
        else:
            # Single due date
            due_dates_to_check.append({
                "due_date": getdate(str(inv.due_date)),
                "outstanding": flt(inv.outstanding_amount),
            })

        # Determine reminder schedule from payment terms
        schedule_key = _classify_terms(inv.payment_terms_template)
        remind_days  = SCHEDULES[schedule_key]

        for due_entry in due_dates_to_check:
            if due_entry["outstanding"] <= 0:
                continue
            due_date    = due_entry["due_date"]
            days_until  = (due_date - today).days

            if days_until < 0:
                # Already overdue — send daily for 1–7 days past due only
                days_overdue = abs(days_until)
                if days_overdue <= 7:
                    reminders.append({
                        "invoice":    inv.name,
                        "customer":   inv.customer_name or inv.customer,
                        "owner":      inv.account_owner,
                        "due_date":   due_date,
                        "outstanding":due_entry["outstanding"],
                        "grand_total":flt(inv.grand_total),
                        "days":       days_until,   # negative = overdue
                        "schedule":   schedule_key,
                    })
            elif days_until in remind_days:
                reminders.append({
                    "invoice":    inv.name,
                    "customer":   inv.customer_name or inv.customer,
                    "owner":      inv.account_owner,
                    "due_date":   due_date,
                    "outstanding":due_entry["outstanding"],
                    "grand_total":flt(inv.grand_total),
                    "days":       days_until,
                    "schedule":   schedule_key,
                })

    if not reminders:
        return "No reminders due today."

    _send_reminder_email(reminders, today)
    return f"Sent {len(reminders)} reminder(s) to {', '.join(RECIPIENTS)}"


@frappe.whitelist()
def send_now():
    """Manual trigger from console or button."""
    return send_ar_reminders()


def _send_reminder_email(reminders, today):
    overdue  = [r for r in reminders if r["days"] < 0]
    upcoming = [r for r in reminders if r["days"] >= 0]

    html = _build_email_html(upcoming, overdue, today)

    frappe.sendmail(
        recipients=RECIPIENTS,
        subject=f"AR Due Date Reminders — {today}",
        message=html,
        delayed=False,
    )


def _build_email_html(upcoming, overdue, today):
    def _fmt(v):
        return "$ {:,.2f}".format(flt(v))

    def _badge(days):
        if days < 0:
            return f'<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">OVERDUE {abs(days)}d</span>'
        if days <= 2:
            return f'<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{days} day{"s" if days!=1 else ""} left</span>'
        if days <= 5:
            return f'<span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{days} days left</span>'
        return f'<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{days} days left</span>'

    def _row(r):
        owner_str = r["owner"] if r["owner"] else "—"
        owner_name = owner_str.split("@")[0].title() if "@" in owner_str else owner_str
        return f"""<tr>
          <td style="padding:8px 12px;font-weight:600;border-bottom:1px solid #f1f5f9;">{r["customer"]}</td>
          <td style="padding:8px 12px;font-family:monospace;font-size:11px;color:#64748b;border-bottom:1px solid #f1f5f9;">{r["invoice"]}</td>
          <td style="padding:8px 12px;color:#64748b;font-size:12px;border-bottom:1px solid #f1f5f9;">{owner_name}</td>
          <td style="padding:8px 12px;text-align:right;font-weight:700;color:#dc2626;border-bottom:1px solid #f1f5f9;">{_fmt(r["outstanding"])}</td>
          <td style="padding:8px 12px;text-align:center;border-bottom:1px solid #f1f5f9;">{r["due_date"]}</td>
          <td style="padding:8px 12px;text-align:center;border-bottom:1px solid #f1f5f9;">{_badge(r["days"])}</td>
        </tr>"""

    def _table(rows, title, color):
        if not rows:
            return ""
        rows_html = "".join(_row(r) for r in rows)
        return f"""
        <div style="margin-bottom:20px;">
          <h3 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:{color};margin-bottom:8px;">{title} ({len(rows)})</h3>
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

    total_outstanding = sum(r["outstanding"] for r in upcoming + overdue)

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;color:#0f172a;margin:0;padding:20px;">
<div style="max-width:760px;margin:0 auto;">

  <div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;padding:28px 32px;margin-bottom:18px;text-align:center;">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:rgba(255,255,255,.4);margin-bottom:8px;">Motley Terpz & TSBC Ranch</div>
    <div style="font-size:22px;font-weight:800;color:#fff;margin-bottom:8px;">AR Due Date Reminders</div>
    <div style="display:inline-block;background:rgba(255,255,255,.1);border-radius:20px;padding:5px 16px;color:rgba(255,255,255,.8);font-size:13px;">{today}</div>
  </div>

  <div style="display:flex;gap:12px;margin-bottom:18px;">
    <div style="flex:1;background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #e2e8f0;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Total Outstanding</div>
      <div style="font-size:20px;font-weight:800;color:#dc2626;">{_fmt(total_outstanding)}</div>
      <div style="font-size:11px;color:#94a3b8;">{len(upcoming + overdue)} invoice(s) requiring attention</div>
    </div>
    <div style="flex:1;background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #e2e8f0;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Overdue</div>
      <div style="font-size:20px;font-weight:800;color:#dc2626;">{len(overdue)}</div>
      <div style="font-size:11px;color:#94a3b8;">past due date</div>
    </div>
    <div style="flex:1;background:#fff;border-radius:10px;padding:14px 16px;border:1px solid #e2e8f0;">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:#64748b;margin-bottom:4px;">Due This Week</div>
      <div style="font-size:20px;font-weight:800;color:#d97706;">{len([r for r in upcoming if r["days"] <= 7])}</div>
      <div style="font-size:11px;color:#94a3b8;">within 7 days</div>
    </div>
  </div>

  {_table(overdue,  "⚠ Overdue", "#dc2626")}
  {_table(upcoming, "Upcoming Due Dates", "#2563eb")}

  <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:12px;">
    Auto-generated by ERPNext · {today} · Do not reply to this message.
  </div>
</div>
</body></html>"""
