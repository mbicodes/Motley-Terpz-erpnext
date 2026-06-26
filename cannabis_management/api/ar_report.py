"""
Friday AR Report
Scheduled: daily at 8 AM Pacific (15:00 UTC / PDT, 16:00 UTC / PST).
Two sections:
  1. New AR (June 1, 2026+) — invoices coming up on terms or recently due
  2. Old AR (before June 1, 2026) — legacy outstanding invoices
Sent to: Nikki, Matt, Muhammad, Imran, bot@motleyterpz.com
"""

import frappe
from frappe.utils import nowdate, fmt_money
from datetime import datetime

NEW_AR_START  = "2026-06-01"
LEGACY_CUTOFF = "2026-05-31"

RECIPIENTS = [
    "nikki@motleyterpz.com",
    "matt@motleyterpz.com",
    "mbi@alltechvirtual.com",
    "imran@motleyterpz.com",
    "bot@motleyterpz.com",
]

COMPANIES = ("Motley Terpz", "TSBC Ranch", "Master Touch Manufacturing")

_NOT_INTERNAL = "(SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)"


def send_ar_report():
    today = nowdate()

    cache_key = f"ar_report_sent_{today}"
    if frappe.cache().get_value(cache_key):
        frappe.logger().info(f"[ar_report] already sent for {today}, skipping")
        return

    try:
        new_rows = _get_new_ar()
        old_rows = _get_old_ar()

        if not new_rows and not old_rows:
            frappe.logger().info("[ar_report] nothing to report today")
            return

        html = _build_email(today, new_rows, old_rows)
        date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")

        frappe.sendmail(
            recipients=RECIPIENTS,
            subject=f"AR Report — {date_label}",
            message=html,
            delayed=False,
        )

        frappe.cache().set_value(cache_key, True, expires_in_sec=26 * 3600)
        frappe.logger().info(f"[ar_report] sent for {today}: {len(new_rows)} new AR, {len(old_rows)} old AR")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "[ar_report] send failed")


@frappe.whitelist()
def execute():
    """Exec from console: frappe.call('cannabis_management.api.ar_report.execute')"""
    return send_now()


def bench_exec():
    """
    bench --site erp.alltechvirtual.com execute cannabis_management.api.ar_report.bench_exec
    Prints row counts and sends the report email.
    """
    new_rows = _get_new_ar()
    old_rows = _get_old_ar()
    print(f"New AR rows : {len(new_rows)}")
    print(f"Old AR rows : {len(old_rows)}")
    today = nowdate()
    html = _build_email(today, new_rows, old_rows)
    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    frappe.sendmail(
        recipients=RECIPIENTS,
        subject=f"[TEST] AR Report — {date_label}",
        message=html,
        delayed=False,
    )
    print("Email queued.")


@frappe.whitelist()
def send_now():
    """Manual trigger from desk or console."""
    today = nowdate()
    new_rows = _get_new_ar()
    old_rows = _get_old_ar()
    html = _build_email(today, new_rows, old_rows)
    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    frappe.sendmail(
        recipients=RECIPIENTS,
        subject=f"[TEST] AR Report — {date_label}",
        message=html,
        delayed=False,
    )
    return {"new_count": len(new_rows), "old_count": len(old_rows)}


# ── Queries ────────────────────────────────────────────────────────────────────

def _get_new_ar():
    """New AR: invoices from June 1 2026 onwards with outstanding balance."""
    return frappe.db.sql(f"""
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.company,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) AS days_overdue
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.company IN %(cos)s
          AND si.posting_date >= %(start)s
          AND si.outstanding_amount > 0.01
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND si.customer NOT IN {_NOT_INTERNAL}
        ORDER BY si.due_date ASC, si.posting_date ASC
    """, {"cos": COMPANIES, "start": NEW_AR_START}, as_dict=True)


def _get_old_ar():
    """Old AR: invoices before June 1 2026 with outstanding balance."""
    return frappe.db.sql(f"""
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.company,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            DATEDIFF(CURDATE(), si.posting_date) AS age_days,
            DATEDIFF(CURDATE(), COALESCE(si.due_date, si.posting_date)) AS days_overdue
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.company IN %(cos)s
          AND si.posting_date <= %(cutoff)s
          AND si.outstanding_amount > 0.01
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND si.customer NOT IN {_NOT_INTERNAL}
        ORDER BY si.posting_date ASC
    """, {"cos": COMPANIES, "cutoff": LEGACY_CUTOFF}, as_dict=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

_CO_COLORS = {
    "Motley Terpz":               "#d97706",
    "TSBC Ranch":                 "#059669",
    "Master Touch Manufacturing": "#7c3aed",
}


def _co_badge(company):
    color = _CO_COLORS.get(company, "#64748b")
    return (
        f'<span style="display:inline-block;padding:1px 8px;border-radius:4px;'
        f'font-size:11px;font-weight:600;background:{color}22;color:{color};">'
        f'{company}</span>'
    )


def _new_ar_status(days_overdue):
    d = int(days_overdue or 0)
    if d < 0:
        # not yet due
        due_in = abs(d)
        if due_in <= 7:
            return ('#b45309', '#fef3c7', f'Due in {due_in}d')
        return ('#15803d', '#dcfce7', f'Due in {due_in}d')
    if d == 0:
        return ('#1d4ed8', '#dbeafe', 'Due today')
    if d <= 14:
        return ('#b45309', '#fef3c7', f'Overdue {d}d')
    if d <= 30:
        return ('#c2410c', '#ffedd5', f'Overdue {d}d')
    return ('#dc2626', '#fee2e2', f'Overdue {d}d')


def _old_ar_age_color(days_overdue):
    d = int(days_overdue or 0)
    if d > 60:
        return "#dc2626"
    if d > 30:
        return "#ea580c"
    return "#d97706"


def _money(val):
    return fmt_money(val or 0, currency="USD")


def _sum_outstanding(rows):
    return sum(float(r.outstanding_amount or 0) for r in rows)


# ── Email builder ──────────────────────────────────────────────────────────────

def _build_email(today, new_rows, old_rows):
    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")

    new_total = _sum_outstanding(new_rows)
    old_total = _sum_outstanding(old_rows)
    grand_total = new_total + old_total

    # ── New AR table ──────────────────────────────────────────────────────────
    new_html = ""
    if new_rows:
        rows_html = ""
        for r in new_rows:
            tc, bc, label = _new_ar_status(r.days_overdue)
            due_str = str(r.due_date) if r.due_date else "—"
            rows_html += f"""
            <tr style="border-bottom:1px solid #f1f5f9;">
              <td style="padding:7px 10px;font-size:12px;">
                <a href="https://erp.alltechvirtual.com/app/sales-invoice/{r.name}"
                   style="color:#2563eb;font-weight:600;text-decoration:none;">{r.name}</a>
              </td>
              <td style="padding:7px 10px;font-size:12px;">{r.customer_name or "—"}</td>
              <td style="padding:7px 10px;">{_co_badge(r.company)}</td>
              <td style="padding:7px 10px;font-size:12px;color:#64748b;">{r.posting_date}</td>
              <td style="padding:7px 10px;font-size:12px;color:#64748b;">{due_str}</td>
              <td style="padding:7px 10px;font-size:12px;text-align:right;">{_money(r.grand_total)}</td>
              <td style="padding:7px 10px;font-size:12px;text-align:right;font-weight:700;color:#1e293b;">
                {_money(r.outstanding_amount)}</td>
              <td style="padding:7px 10px;font-size:12px;text-align:center;">
                <span style="padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;
                             background:{bc};color:{tc};">{label}</span>
              </td>
            </tr>"""

        new_html = f"""
        <h3 style="margin:24px 0 6px;font-size:14px;font-weight:700;color:#1e293b;
                   border-bottom:2px solid #e2e8f0;padding-bottom:6px;">
          New AR — June 1, 2026 onwards
          <span style="font-size:11px;font-weight:600;color:#2563eb;
                       background:#dbeafe;padding:2px 10px;border-radius:12px;margin-left:8px;">
            {len(new_rows)} invoice(s)</span>
        </h3>
        <p style="margin:0 0 8px;font-size:11px;color:#64748b;font-style:italic;">
          Here is what is coming up on terms</p>
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-family:Inter,Arial,sans-serif;">
          <thead>
            <tr style="background:#f0f9ff;font-size:10px;font-weight:700;color:#94a3b8;
                       text-transform:uppercase;letter-spacing:0.07em;">
              <th style="padding:7px 10px;text-align:left;">Invoice #</th>
              <th style="padding:7px 10px;text-align:left;">Customer</th>
              <th style="padding:7px 10px;text-align:left;">Company</th>
              <th style="padding:7px 10px;text-align:left;">Posted</th>
              <th style="padding:7px 10px;text-align:left;">Due Date</th>
              <th style="padding:7px 10px;text-align:right;">Total</th>
              <th style="padding:7px 10px;text-align:right;">Outstanding</th>
              <th style="padding:7px 10px;text-align:center;">Status</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""

    # ── Old AR table ──────────────────────────────────────────────────────────
    old_html = ""
    if old_rows:
        rows_html = ""
        for r in old_rows:
            age_c = _old_ar_age_color(r.days_overdue)
            due_str = str(r.due_date) if r.due_date else "—"
            rows_html += f"""
            <tr style="border-bottom:1px solid #f1f5f9;">
              <td style="padding:7px 10px;font-size:12px;">
                <a href="https://erp.alltechvirtual.com/app/sales-invoice/{r.name}"
                   style="color:#2563eb;font-weight:600;text-decoration:none;">{r.name}</a>
              </td>
              <td style="padding:7px 10px;font-size:12px;">{r.customer_name or "—"}</td>
              <td style="padding:7px 10px;">{_co_badge(r.company)}</td>
              <td style="padding:7px 10px;font-size:12px;color:#64748b;">{r.posting_date}</td>
              <td style="padding:7px 10px;font-size:12px;color:#64748b;">{due_str}</td>
              <td style="padding:7px 10px;font-size:12px;text-align:right;">{_money(r.grand_total)}</td>
              <td style="padding:7px 10px;font-size:12px;text-align:right;font-weight:700;color:#1e293b;">
                {_money(r.outstanding_amount)}</td>
              <td style="padding:7px 10px;font-size:12px;text-align:right;font-weight:700;color:{age_c};">
                {int(r.age_days or 0)}d old</td>
            </tr>"""

        old_html = f"""
        <h3 style="margin:28px 0 6px;font-size:14px;font-weight:700;color:#1e293b;
                   border-bottom:2px solid #e2e8f0;padding-bottom:6px;">
          Old AR — Before June 1, 2026
          <span style="font-size:11px;font-weight:600;color:#e11d48;
                       background:#fee2e2;padding:2px 10px;border-radius:12px;margin-left:8px;">
            {len(old_rows)} invoice(s)</span>
        </h3>
        <p style="margin:0 0 8px;font-size:11px;color:#64748b;font-style:italic;">
          Legacy outstanding — requires follow-up</p>
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-family:Inter,Arial,sans-serif;">
          <thead>
            <tr style="background:#fef2f2;font-size:10px;font-weight:700;color:#94a3b8;
                       text-transform:uppercase;letter-spacing:0.07em;">
              <th style="padding:7px 10px;text-align:left;">Invoice #</th>
              <th style="padding:7px 10px;text-align:left;">Customer</th>
              <th style="padding:7px 10px;text-align:left;">Company</th>
              <th style="padding:7px 10px;text-align:left;">Posted</th>
              <th style="padding:7px 10px;text-align:left;">Due Date</th>
              <th style="padding:7px 10px;text-align:right;">Total</th>
              <th style="padding:7px 10px;text-align:right;">Outstanding</th>
              <th style="padding:7px 10px;text-align:right;">Age</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""

    return f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:1000px;margin:0 auto;
                background:#ffffff;padding:24px 32px;">

      <div style="display:flex;align-items:center;justify-content:space-between;
                  border-bottom:3px solid #1e293b;padding-bottom:16px;margin-bottom:20px;">
        <div>
          <h1 style="margin:0;font-size:20px;font-weight:800;color:#1e293b;">
            AR Report</h1>
          <p style="margin:4px 0 0;font-size:12px;color:#64748b;">{date_label}</p>
        </div>
        <div style="text-align:right;">
          <div style="font-size:24px;font-weight:800;color:#1e293b;">
            {_money(grand_total)}</div>
          <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;
                      letter-spacing:0.06em;">Total Outstanding</div>
        </div>
      </div>

      <div style="display:flex;gap:16px;margin-bottom:8px;">
        <div style="flex:1;padding:14px 18px;border-radius:8px;
                    background:#eff6ff;border:1px solid #bfdbfe;">
          <div style="font-size:20px;font-weight:800;color:#1d4ed8;">{_money(new_total)}</div>
          <div style="font-size:11px;font-weight:600;color:#1e40af;
                      text-transform:uppercase;letter-spacing:0.05em;">
            New AR — {len(new_rows)} invoice(s)</div>
          <div style="font-size:10px;color:#3b82f6;margin-top:2px;">June 1, 2026 onwards</div>
        </div>
        <div style="flex:1;padding:14px 18px;border-radius:8px;
                    background:#fef2f2;border:1px solid #fecaca;">
          <div style="font-size:20px;font-weight:800;color:#dc2626;">{_money(old_total)}</div>
          <div style="font-size:11px;font-weight:600;color:#991b1b;
                      text-transform:uppercase;letter-spacing:0.05em;">
            Old AR — {len(old_rows)} invoice(s)</div>
          <div style="font-size:10px;color:#ef4444;margin-top:2px;">Before June 1, 2026</div>
        </div>
      </div>

      {new_html}
      {old_html}

      <p style="margin-top:32px;font-size:11px;color:#94a3b8;border-top:1px solid #e2e8f0;
                padding-top:12px;">
        Sent daily at 8 AM Pacific •
        <a href="https://erp.alltechvirtual.com" style="color:#2563eb;">erp.alltechvirtual.com</a>
      </p>
    </div>"""
