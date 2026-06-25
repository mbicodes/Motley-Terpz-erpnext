"""
DN Gap Report
Scheduled: every day at 8 AM Pacific (15:00 UTC / PDT, 16:00 UTC / PST).
Lists all Sales Orders and Sales Invoices that have no corresponding Delivery Note.
Sent to: Nikki, Matt, Muhammad, Imran, bot@motleyterpz.com
"""

import frappe
from frappe.utils import nowdate, fmt_money
from datetime import datetime

RECIPIENTS = [
    "nikki@motleyterpz.com",
    "matt@motleyterpz.com",
    "mbi@alltechvirtual.com",
    "imran@motleyterpz.com",
    "bot@motleyterpz.com",
]

COMPANIES = ("Motley Terpz", "TSBC Ranch", "Master Touch Manufacturing")


def send_dn_gap_report():
    today = nowdate()

    cache_key = f"dn_gap_report_sent_{today}"
    if frappe.cache().get_value(cache_key):
        frappe.logger().info(f"[dn_gap_report] already sent for {today}, skipping")
        return

    try:
        so_rows = _get_open_sos()
        si_rows = _get_sis_without_dn()

        if not so_rows and not si_rows:
            frappe.logger().info("[dn_gap_report] nothing to report today")
            return

        html = _build_email(today, so_rows, si_rows)
        date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")

        frappe.sendmail(
            recipients=RECIPIENTS,
            subject=f"DN Gap Report — {date_label}",
            message=html,
            delayed=False,
        )

        frappe.cache().set_value(cache_key, True, expires_in_sec=26 * 3600)
        frappe.logger().info(f"[dn_gap_report] sent for {today}: {len(so_rows)} SOs, {len(si_rows)} SIs")

    except Exception:
        frappe.log_error(frappe.get_traceback(), "[dn_gap_report] send failed")


@frappe.whitelist()
def send_now():
    """Manual trigger from desk or console."""
    # Bypass cache guard so it always fires when called manually
    today = nowdate()
    so_rows = _get_open_sos()
    si_rows = _get_sis_without_dn()
    html = _build_email(today, so_rows, si_rows)
    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    frappe.sendmail(
        recipients=RECIPIENTS,
        subject=f"[TEST] DN Gap Report — {date_label}",
        message=html,
        delayed=False,
    )
    return {"so_count": len(so_rows), "si_count": len(si_rows)}


# ── Queries ────────────────────────────────────────────────────────────────────

def _get_open_sos():
    """Sales Orders that still have pending delivery (no full DN)."""
    return frappe.db.sql("""
        SELECT
            so.name,
            so.customer_name,
            so.company,
            so.transaction_date,
            so.grand_total,
            so.status,
            DATEDIFF(CURDATE(), so.transaction_date) AS age_days
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
          AND so.status IN ('To Deliver and Bill', 'To Deliver')
          AND so.company IN %(cos)s
          AND so.customer NOT IN (SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)
        ORDER BY so.transaction_date ASC
    """, {"cos": COMPANIES}, as_dict=True)


def _get_sis_without_dn():
    """Sales Invoices that have no Delivery Note linked to any of their items."""
    return frappe.db.sql("""
        SELECT
            si.name,
            si.customer_name,
            si.company,
            si.posting_date,
            si.grand_total,
            si.outstanding_amount,
            DATEDIFF(CURDATE(), si.posting_date) AS age_days
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.company IN %(cos)s
          AND si.customer NOT IN (SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND NOT EXISTS (
              SELECT 1 FROM `tabDelivery Note Item` dni
              WHERE dni.against_sales_invoice = si.name
          )
        ORDER BY si.posting_date ASC
    """, {"cos": COMPANIES}, as_dict=True)


# ── HTML builder ───────────────────────────────────────────────────────────────

def _age_color(days):
    d = int(days or 0)
    if d > 30:
        return "#dc2626"   # red
    if d > 14:
        return "#d97706"   # amber
    return "#16a34a"       # green


def _build_email(today, so_rows, si_rows):
    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")

    co_colors = {
        "Motley Terpz":             "#d97706",
        "TSBC Ranch":               "#059669",
        "Master Touch Manufacturing": "#7c3aed",
    }

    def co_badge(company):
        color = co_colors.get(company, "#64748b")
        return (
            f'<span style="display:inline-block;padding:1px 8px;border-radius:4px;'
            f'font-size:11px;font-weight:600;background:{color}22;color:{color};">'
            f'{company}</span>'
        )

    # ── SO table ──────────────────────────────────────────────────────────────
    so_html = ""
    if so_rows:
        rows_html = ""
        for r in so_rows:
            age_c = _age_color(r.age_days)
            rows_html += f"""
            <tr style="border-bottom:1px solid #f1f5f9;">
              <td style="padding:8px 12px;font-size:12px;">
                <a href="https://erp.alltechvirtual.com/app/sales-order/{r.name}"
                   style="color:#2563eb;font-weight:600;text-decoration:none;">{r.name}</a>
              </td>
              <td style="padding:8px 12px;font-size:12px;">{r.customer_name or "—"}</td>
              <td style="padding:8px 12px;">{co_badge(r.company)}</td>
              <td style="padding:8px 12px;font-size:12px;">{r.transaction_date}</td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;font-weight:600;">
                {fmt_money(r.grand_total or 0, currency="USD")}</td>
              <td style="padding:8px 12px;font-size:12px;">
                <span style="padding:2px 8px;border-radius:4px;background:#fef3c7;color:#92400e;font-size:11px;font-weight:600;">
                  {r.status}</span></td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;font-weight:700;color:{age_c};">
                {int(r.age_days or 0)}d</td>
            </tr>"""

        so_html = f"""
        <h3 style="margin:24px 0 8px;font-size:14px;font-weight:700;color:#1e293b;
                   border-bottom:2px solid #e2e8f0;padding-bottom:6px;">
          Sales Orders Without Delivery Note
          <span style="font-size:12px;font-weight:600;color:#e11d48;
                       background:#fee2e2;padding:2px 10px;border-radius:12px;margin-left:8px;">
            {len(so_rows)}</span>
        </h3>
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-family:Inter,Arial,sans-serif;">
          <thead>
            <tr style="background:#f8fafc;font-size:10px;font-weight:700;color:#94a3b8;
                       text-transform:uppercase;letter-spacing:0.07em;">
              <th style="padding:8px 12px;text-align:left;">SO #</th>
              <th style="padding:8px 12px;text-align:left;">Customer</th>
              <th style="padding:8px 12px;text-align:left;">Company</th>
              <th style="padding:8px 12px;text-align:left;">Date</th>
              <th style="padding:8px 12px;text-align:right;">Amount</th>
              <th style="padding:8px 12px;text-align:left;">Status</th>
              <th style="padding:8px 12px;text-align:right;">Age</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""

    # ── SI table ──────────────────────────────────────────────────────────────
    si_html = ""
    if si_rows:
        rows_html = ""
        for r in si_rows:
            age_c = _age_color(r.age_days)
            rows_html += f"""
            <tr style="border-bottom:1px solid #f1f5f9;">
              <td style="padding:8px 12px;font-size:12px;">
                <a href="https://erp.alltechvirtual.com/app/sales-invoice/{r.name}"
                   style="color:#2563eb;font-weight:600;text-decoration:none;">{r.name}</a>
              </td>
              <td style="padding:8px 12px;font-size:12px;">{r.customer_name or "—"}</td>
              <td style="padding:8px 12px;">{co_badge(r.company)}</td>
              <td style="padding:8px 12px;font-size:12px;">{r.posting_date}</td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;font-weight:600;">
                {fmt_money(r.grand_total or 0, currency="USD")}</td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;
                         color:#e11d48;font-weight:700;">
                {fmt_money(r.outstanding_amount or 0, currency="USD")}</td>
              <td style="padding:8px 12px;font-size:12px;text-align:right;font-weight:700;color:{age_c};">
                {int(r.age_days or 0)}d</td>
            </tr>"""

        si_html = f"""
        <h3 style="margin:24px 0 8px;font-size:14px;font-weight:700;color:#1e293b;
                   border-bottom:2px solid #e2e8f0;padding-bottom:6px;">
          Sales Invoices Without Delivery Note
          <span style="font-size:12px;font-weight:600;color:#e11d48;
                       background:#fee2e2;padding:2px 10px;border-radius:12px;margin-left:8px;">
            {len(si_rows)}</span>
        </h3>
        <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-family:Inter,Arial,sans-serif;">
          <thead>
            <tr style="background:#f8fafc;font-size:10px;font-weight:700;color:#94a3b8;
                       text-transform:uppercase;letter-spacing:0.07em;">
              <th style="padding:8px 12px;text-align:left;">Invoice #</th>
              <th style="padding:8px 12px;text-align:left;">Customer</th>
              <th style="padding:8px 12px;text-align:left;">Company</th>
              <th style="padding:8px 12px;text-align:left;">Date</th>
              <th style="padding:8px 12px;text-align:right;">Total</th>
              <th style="padding:8px 12px;text-align:right;">Outstanding</th>
              <th style="padding:8px 12px;text-align:right;">Age</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table></div>"""

    return f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:960px;margin:0 auto;
                background:#ffffff;padding:24px 32px;">

      <div style="display:flex;align-items:center;justify-content:space-between;
                  border-bottom:3px solid #1e293b;padding-bottom:16px;margin-bottom:20px;">
        <div>
          <h1 style="margin:0;font-size:20px;font-weight:800;color:#1e293b;">
            DN Gap Report</h1>
          <p style="margin:4px 0 0;font-size:12px;color:#64748b;">{date_label}</p>
        </div>
        <div style="text-align:right;">
          <div style="font-size:24px;font-weight:800;color:#e11d48;">
            {len(so_rows) + len(si_rows)}</div>
          <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;
                      letter-spacing:0.06em;">items need attention</div>
        </div>
      </div>

      <div style="display:flex;gap:16px;margin-bottom:20px;">
        <div style="flex:1;padding:14px 18px;border-radius:8px;
                    background:#fef2f2;border:1px solid #fecaca;">
          <div style="font-size:22px;font-weight:800;color:#e11d48;">{len(so_rows)}</div>
          <div style="font-size:11px;font-weight:600;color:#991b1b;
                      text-transform:uppercase;letter-spacing:0.05em;">
            Sales Orders — No DN</div>
        </div>
        <div style="flex:1;padding:14px 18px;border-radius:8px;
                    background:#fff7ed;border:1px solid #fed7aa;">
          <div style="font-size:22px;font-weight:800;color:#ea580c;">{len(si_rows)}</div>
          <div style="font-size:11px;font-weight:600;color:#9a3412;
                      text-transform:uppercase;letter-spacing:0.05em;">
            Sales Invoices — No DN</div>
        </div>
      </div>

      {so_html}
      {si_html}

      <p style="margin-top:32px;font-size:11px;color:#94a3b8;border-top:1px solid #e2e8f0;
                padding-top:12px;">
        Sent daily at 8 AM Pacific •
        <a href="https://erp.alltechvirtual.com" style="color:#2563eb;">erp.alltechvirtual.com</a>
      </p>
    </div>"""
