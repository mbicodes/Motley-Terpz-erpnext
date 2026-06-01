"""
AR Policy Monitor
Scheduled jobs for AR cap alerts, DSO, CEI, and weekly AR report.

Scheduler hooks (added to hooks.py):
  daily:              check_ar_cap, compute_dso
  monthly:            compute_cei
  cron "0 8 * * 5":  send_weekly_ar_report  (Friday 8 AM UTC)
"""

import frappe
from frappe.utils import flt, nowdate, add_days, getdate
from datetime import datetime

from cannabis_management.api.ar import DEFAULT_RECEIVABLE_ACCOUNTS

FINANCE_RECIPIENTS = [
    "jamie@motleyterpz.com",
    "matt@motleyterpz.com",
    "imran@motleyterpz.com",
    "mbi@alltechvirtual.com",
    "nikki@motleyterpz.com",
    "osama.ahmad@alltechvirtual.com",
]

AR_CAP_HARD     = 400_000.0
AR_CAP_ESCALATE = 350_000.0
AR_CAP_WARN     = 300_000.0
DSO_WARN_DAYS   = 14
DSO_URGENT_DAYS = 30
DSO_PERIOD_DAYS = 30


# ── Shared GL helpers ─────────────────────────────────────────────────────────

def _total_ar(as_of=None):
    """Total receivable balance from GL Entry across all customers."""
    params = {"accounts": tuple(DEFAULT_RECEIVABLE_ACCOUNTS)}
    date_filter = ""
    if as_of:
        date_filter = "AND posting_date <= %(as_of)s"
        params["as_of"] = as_of

    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(debit - credit), 0) AS bal
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND account IN %(accounts)s
          AND is_cancelled = 0
          {date_filter}
        """,
        params,
        as_dict=True,
    )
    return flt(result[0].bal) if result else 0.0


def _credit_sales(from_date, to_date):
    """Total grand_total of submitted Sales Invoices in a date range."""
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(grand_total), 0) AS total
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND posting_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        {"from_date": from_date, "to_date": to_date},
        as_dict=True,
    )
    return flt(result[0].total) if result else 0.0


def _send_email(subject, html):
    try:
        frappe.sendmail(
            recipients=FINANCE_RECIPIENTS,
            subject=subject,
            message=html,
            delayed=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"[ar_monitor] email failed: {subject}")


# ── Job 1: check_ar_cap (daily) ───────────────────────────────────────────────

def check_ar_cap():
    """Daily: read total AR from GL ledger, alert at $300k / $350k / $400k."""
    try:
        total_ar = _total_ar()
        cap_pct  = (total_ar / AR_CAP_HARD) * 100

        frappe.logger().info(
            f"[ar_monitor] AR cap check: ${total_ar:,.2f} ({cap_pct:.1f}%)"
        )

        if total_ar >= AR_CAP_HARD:
            _send_email(
                subject="URGENT: AR Hard Cap $400k Reached — New Invoices Blocked",
                html=_cap_email(total_ar, cap_pct, "HARD CAP REACHED", "#dc2626"),
            )
        elif total_ar >= AR_CAP_ESCALATE:
            frappe.log_error(
                f"AR at ${total_ar:,.2f} ({cap_pct:.1f}%) — approaching hard cap",
                "[ar_monitor] AR $350k Escalation",
            )
            _send_email(
                subject=f"AR Escalation: Outstanding AR at ${total_ar:,.2f} (87.5% of cap)",
                html=_cap_email(total_ar, cap_pct, "ESCALATION — 87.5% of Cap", "#f97316"),
            )
        elif total_ar >= AR_CAP_WARN:
            _send_email(
                subject=f"AR Warning: Outstanding AR at ${total_ar:,.2f} ($300k threshold)",
                html=_cap_email(total_ar, cap_pct, "WARNING — $300k Threshold", "#d97706"),
            )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "[ar_monitor] check_ar_cap failed")


def _cap_email(total_ar, cap_pct, level, color):
    bar = min(cap_pct, 100)
    today = nowdate()
    return f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
            max-width:600px;margin:0 auto;padding:24px;">
  <div style="background:{color};color:#fff;padding:16px 22px;border-radius:10px 10px 0 0;">
    <h2 style="margin:0;font-size:18px">AR Policy Alert — {level}</h2>
  </div>
  <div style="background:#fff;border:1px solid #e2e8f0;padding:22px;border-radius:0 0 10px 10px;">
    <p style="font-size:32px;font-weight:800;color:{color};margin:0 0 4px">${total_ar:,.2f}</p>
    <p style="color:#64748b;margin:0 0 20px;font-size:13px">Total Outstanding AR — GL Ledger as of {today}</p>
    <div style="background:#f1f5f9;border-radius:6px;height:14px;overflow:hidden;margin-bottom:6px">
      <div style="background:{color};height:100%;width:{bar:.1f}%"></div>
    </div>
    <p style="color:#94a3b8;font-size:12px;margin:0 0 20px">{cap_pct:.1f}% of $400,000 policy cap</p>
    <p style="color:#334155;font-size:13px">
      Please log in to ERPNext and review the AR Dashboard to identify
      accounts for immediate collection action.
    </p>
  </div>
</div>"""


# ── Job 2: compute_dso (daily) ────────────────────────────────────────────────

def compute_dso():
    """
    Daily: DSO = (Total AR from GL ÷ Credit Sales in last 30 days) × 30.
    Alert if DSO > 14 days (warning) or > 30 days (urgent).
    """
    try:
        today      = nowdate()
        from_date  = add_days(today, -DSO_PERIOD_DAYS)
        total_ar   = _total_ar()
        sales      = _credit_sales(from_date, today)

        if sales <= 0:
            frappe.logger().info("[ar_monitor] compute_dso: no sales in period, skipping")
            return

        dso = (total_ar / sales) * DSO_PERIOD_DAYS

        frappe.log_error(
            f"DSO={dso:.1f}d | AR=${total_ar:,.2f} | Sales(30d)=${sales:,.2f}",
            "[ar_monitor] Daily DSO",
        )

        if dso > DSO_URGENT_DAYS:
            _send_email(
                subject=f"URGENT: DSO at {dso:.1f} days (>{DSO_URGENT_DAYS}d threshold)",
                html=_dso_email(dso, total_ar, sales, "URGENT", "#dc2626"),
            )
        elif dso > DSO_WARN_DAYS:
            _send_email(
                subject=f"DSO Warning: {dso:.1f} days (>{DSO_WARN_DAYS}d threshold)",
                html=_dso_email(dso, total_ar, sales, "WARNING", "#d97706"),
            )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "[ar_monitor] compute_dso failed")


def _dso_email(dso, ar, sales, level, color):
    today = nowdate()
    return f"""
<div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
  <div style="background:{color};color:#fff;padding:14px 20px;border-radius:8px 8px 0 0;">
    <h3 style="margin:0">DSO {level}: {dso:.1f} days</h3>
  </div>
  <div style="background:#fff;border:1px solid #e2e8f0;padding:20px;border-radius:0 0 8px 8px;">
    <table style="width:100%;font-size:13px;border-collapse:collapse">
      <tr><td style="padding:7px 0;color:#64748b">Total AR (GL Ledger)</td>
          <td style="text-align:right;font-weight:700">${ar:,.2f}</td></tr>
      <tr><td style="padding:7px 0;color:#64748b">Credit Sales (last 30d)</td>
          <td style="text-align:right;font-weight:700">${sales:,.2f}</td></tr>
      <tr style="border-top:2px solid #e2e8f0">
        <td style="padding:10px 0;font-weight:700">DSO</td>
        <td style="text-align:right;font-size:20px;font-weight:800;color:{color}">{dso:.1f} days</td>
      </tr>
    </table>
    <p style="color:#64748b;font-size:11px;margin:12px 0 0">As of {today}</p>
  </div>
</div>"""


# ── Job 3: compute_cei (monthly) ─────────────────────────────────────────────

def compute_cei():
    """
    Monthly: CEI = (BegAR + Sales − EndAR) / (BegAR + Sales − PastDueAR) × 100.
    Runs on the first day of each month, covering the previous calendar month.
    """
    try:
        today             = getdate(nowdate())
        first_this_month  = today.replace(day=1)
        end_date          = add_days(str(first_this_month), -1)   # last day prev month
        start_date        = getdate(end_date).replace(day=1)      # first day prev month

        beg_ar   = _total_ar(add_days(str(start_date), -1))
        end_ar   = _total_ar(str(end_date))
        sales    = _credit_sales(str(start_date), str(end_date))

        pastdue  = frappe.db.sql(
            """
            SELECT COALESCE(SUM(outstanding_amount), 0) AS total
            FROM `tabSales Invoice`
            WHERE docstatus = 1
              AND outstanding_amount > 0
              AND due_date < %(start)s
              AND posting_date <= %(end)s
            """,
            {"start": str(start_date), "end": str(end_date)},
            as_dict=True,
        )
        past_due_ar = flt(pastdue[0].total) if pastdue else 0.0

        denom = beg_ar + sales - past_due_ar
        if denom <= 0:
            frappe.logger().info("[ar_monitor] compute_cei: denominator <=0, skipping")
            return

        cei = min(((beg_ar + sales - end_ar) / denom) * 100.0, 100.0)
        period_label = getdate(str(start_date)).strftime("%B %Y")

        frappe.log_error(
            f"CEI={cei:.2f}% | BegAR=${beg_ar:,.2f} | Sales=${sales:,.2f} | "
            f"EndAR=${end_ar:,.2f} | PastDue=${past_due_ar:,.2f} | {period_label}",
            "[ar_monitor] Monthly CEI",
        )

        _send_email(
            subject=f"Monthly CEI Report: {cei:.1f}% — {period_label}",
            html=_cei_email(cei, beg_ar, sales, end_ar, past_due_ar, period_label),
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "[ar_monitor] compute_cei failed")


def _cei_email(cei, beg_ar, sales, end_ar, past_due, period):
    color = "#059669" if cei >= 90 else ("#d97706" if cei >= 75 else "#dc2626")
    return f"""
<div style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
  <div style="background:#0f172a;color:#fff;padding:16px 22px;border-radius:10px 10px 0 0;">
    <h2 style="margin:0;font-size:17px">Monthly CEI Report — {period}</h2>
  </div>
  <div style="background:#fff;border:1px solid #e2e8f0;padding:22px;border-radius:0 0 10px 10px;">
    <p style="font-size:40px;font-weight:800;color:{color};margin:0">{cei:.1f}%</p>
    <p style="color:#64748b;margin:0 0 20px;font-size:13px">Collections Effectiveness Index</p>
    <table style="width:100%;font-size:13px;border-collapse:collapse;border:1px solid #e2e8f0">
      <tr style="background:#f8fafc">
        <td style="padding:8px 12px">Beginning AR</td>
        <td style="text-align:right;padding:8px 12px">${beg_ar:,.2f}</td>
      </tr>
      <tr>
        <td style="padding:8px 12px">+ Credit Sales</td>
        <td style="text-align:right;padding:8px 12px">${sales:,.2f}</td>
      </tr>
      <tr style="background:#f8fafc">
        <td style="padding:8px 12px">− Ending AR</td>
        <td style="text-align:right;padding:8px 12px">${end_ar:,.2f}</td>
      </tr>
      <tr>
        <td style="padding:8px 12px">Past-Due AR (at period start)</td>
        <td style="text-align:right;padding:8px 12px">${past_due:,.2f}</td>
      </tr>
      <tr style="background:#0f172a;color:#fff">
        <td style="padding:10px 12px;font-weight:700">CEI</td>
        <td style="text-align:right;padding:10px 12px;font-size:18px;font-weight:800;color:{color}">{cei:.1f}%</td>
      </tr>
    </table>
  </div>
</div>"""


# ── Job 4: send_weekly_ar_report (Friday) ────────────────────────────────────

def send_weekly_ar_report():
    """Friday 8 AM UTC: full HTML AR report covering Sections A–D."""
    try:
        today      = nowdate()
        week_start = add_days(today, -6)
        html       = _build_weekly_email(today, week_start)
        date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%B %-d, %Y")
        frappe.sendmail(
            recipients=FINANCE_RECIPIENTS,
            subject=f"Weekly AR Report — {date_label}",
            message=html,
            delayed=False,
        )
        frappe.logger().info(f"[ar_monitor] weekly AR report sent for {today}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[ar_monitor] send_weekly_ar_report failed")


@frappe.whitelist()
def send_weekly_ar_report_now():
    """Manual trigger for testing."""
    send_weekly_ar_report()
    return "sent"


def _build_weekly_email(today, week_start):
    total_ar   = _total_ar()
    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    sec_a = _sec_a_legacy(today)
    sec_b = _sec_b_new_ar(week_start, today)
    sec_c = _sec_c_cod_credit(week_start, today)
    sec_d = _sec_d_red_list()

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#f1f5f9;color:#0f172a;margin:0;padding:0}}
  .wrap{{max-width:780px;margin:0 auto;padding:20px 16px 40px}}
  .hdr{{background:linear-gradient(150deg,#0f172a,#1e3a5f);border-radius:14px;
        padding:30px;margin-bottom:14px;text-align:center}}
  .hdr-title{{font-size:24px;font-weight:800;color:#fff;margin-bottom:6px}}
  .hdr-sub{{color:rgba(255,255,255,.55);font-size:13px}}
  .kpi-row{{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}}
  .kpi{{flex:1;min-width:140px;background:#fff;border-radius:10px;
        border:1px solid #e2e8f0;padding:18px 20px}}
  .kpi-lbl{{font-size:10px;font-weight:700;text-transform:uppercase;
            letter-spacing:.6px;color:#64748b;margin-bottom:6px}}
  .kpi-val{{font-size:22px;font-weight:800}}
  .sec{{background:#fff;border-radius:10px;border:1px solid #e2e8f0;
        margin-bottom:14px;overflow:hidden}}
  .sec-hdr{{padding:11px 16px;border-bottom:1px solid #f1f5f9;
            display:flex;align-items:center;gap:8px}}
  .sec-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
  .sec-title{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}}
  table{{width:100%;border-collapse:collapse;font-size:12px}}
  th{{padding:8px 12px;background:#f8fafc;color:#64748b;font-weight:700;
      font-size:10px;text-transform:uppercase;text-align:left;
      border-bottom:1px solid #e2e8f0;white-space:nowrap}}
  th.r{{text-align:right}}
  td{{padding:8px 12px;border-bottom:1px solid #f8fafc;color:#0f172a}}
  td.r{{text-align:right;font-variant-numeric:tabular-nums}}
  td.m{{color:#94a3b8;font-size:11px}}
  tr:last-child td{{border-bottom:none}}
  tr.sub td{{background:#f8fafc;font-weight:700;border-top:2px solid #e2e8f0}}
  .badge{{display:inline-block;padding:2px 7px;border-radius:4px;
          font-size:10px;font-weight:700;text-transform:uppercase}}
  .b-red{{background:#fee2e2;color:#dc2626}}
  .b-amb{{background:#fef3c7;color:#92400e}}
  .b-grn{{background:#d1fae5;color:#059669}}
  .empty{{padding:20px;text-align:center;color:#94a3b8;font-size:12px;font-style:italic}}
</style></head><body><div class="wrap">
  <div class="hdr">
    <div class="hdr-title">Weekly AR Report</div>
    <div class="hdr-sub">{date_label} &nbsp;·&nbsp; Motley Terpz &amp; TSBC Ranch</div>
  </div>
  <div class="kpi-row">
    <div class="kpi">
      <div class="kpi-lbl">Total AR (GL Ledger)</div>
      <div class="kpi-val" style="color:#dc2626">${total_ar:,.2f}</div>
    </div>
  </div>
  {sec_a}{sec_b}{sec_c}{sec_d}
  <p style="text-align:center;color:#94a3b8;font-size:11px;margin-top:8px">
    Auto-generated by ERPNext &nbsp;·&nbsp;
    {datetime.now().strftime("%B %-d, %Y %H:%M")} UTC
  </p>
</div></body></html>"""


# ── Section A — Legacy debt (90+ days) ───────────────────────────────────────

def _sec_a_legacy(today):
    cutoff = add_days(today, -90)

    # Legacy outstanding per customer from GL Entry
    gl = frappe.db.sql(
        """
        SELECT party AS customer,
               COALESCE(SUM(debit - credit), 0) AS balance
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND account IN %(accounts)s
          AND is_cancelled = 0
          AND posting_date <= %(cutoff)s
          AND party NOT IN (
              SELECT name FROM `tabCustomer`
              WHERE is_internal_customer = 1
                 OR (represents_company IS NOT NULL AND represents_company != '')
          )
        GROUP BY party
        HAVING balance > 0
        ORDER BY balance DESC
        """,
        {"accounts": tuple(DEFAULT_RECEIVABLE_ACCOUNTS), "cutoff": cutoff},
        as_dict=True,
    )

    # Collections this week on those legacy customers
    week_start = add_days(today, -6)
    cust_list = tuple(r.customer for r in gl) if gl else ("__none__",)
    coll = frappe.db.sql(
        """
        SELECT pe.party AS customer,
               SUM(per.allocated_amount) AS collected
        FROM `tabPayment Entry` pe
        JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
        JOIN `tabSales Invoice` si ON si.name = per.reference_name
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.posting_date BETWEEN %(ws)s AND %(today)s
          AND si.posting_date < %(cutoff)s
          AND pe.party IN %(custs)s
        GROUP BY pe.party
        ORDER BY collected DESC
        """,
        {"ws": week_start, "today": today, "cutoff": cutoff, "custs": cust_list},
        as_dict=True,
    )

    legacy_total = sum(flt(r.balance) for r in gl)
    coll_total   = sum(flt(r.collected) for r in coll)

    if not gl:
        body = '<div class="empty">No legacy AR (90+ days old) outstanding.</div>'
    else:
        rows = "".join(
            f'<tr><td>{r.customer}</td>'
            f'<td class="r"><b>${flt(r.balance):,.2f}</b></td></tr>'
            for r in gl
        )
        body = f"""<table>
<thead><tr><th>Customer</th><th class="r">GL Balance</th></tr></thead>
<tbody>{rows}
<tr class="sub"><td>Legacy Total (GL)</td><td class="r">${legacy_total:,.2f}</td></tr>
</tbody></table>"""

    if coll:
        c_rows = "".join(
            f'<tr><td>{r.customer}</td>'
            f'<td class="r">${flt(r.collected):,.2f}</td></tr>'
            for r in coll
        )
        body += f"""<table style="margin-top:0">
<thead><tr style="background:#f0fdf4">
  <th>Collections This Week (on legacy AR)</th><th class="r">Amount</th>
</tr></thead>
<tbody>{c_rows}
<tr class="sub"><td>Total Collected</td><td class="r">${coll_total:,.2f}</td></tr>
</tbody></table>"""

    return f"""<div class="sec">
  <div class="sec-hdr">
    <div class="sec-dot" style="background:#dc2626"></div>
    <div class="sec-title">Section A — Legacy Debt (90+ days) &nbsp;·&nbsp; {len(gl)} accounts</div>
  </div>{body}</div>"""


# ── Section B — New AR this week ──────────────────────────────────────────────

def _sec_b_new_ar(week_start, today):
    rows = frappe.db.sql(
        """
        SELECT si.customer, si.name, si.posting_date,
               si.grand_total, si.outstanding_amount,
               si.payment_terms_template
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(ws)s AND %(today)s
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
          AND si.customer NOT IN (SELECT name FROM `tabCompany`)
        ORDER BY si.posting_date DESC
        """,
        {"ws": week_start, "today": today},
        as_dict=True,
    )

    new_total = sum(flt(r.grand_total) for r in rows)

    if not rows:
        body = '<div class="empty">No new invoices this week.</div>'
    else:
        r_rows = "".join(
            f"""<tr>
              <td>{r.customer}</td>
              <td class="m">{r.name}</td>
              <td class="m">{r.posting_date}</td>
              <td class="r">${flt(r.grand_total):,.2f}</td>
              <td class="r">${flt(r.outstanding_amount):,.2f}</td>
              <td class="m">{r.payment_terms_template or "—"}</td>
            </tr>"""
            for r in rows
        )
        body = f"""<table>
<thead><tr>
  <th>Customer</th><th>Invoice</th><th>Date</th>
  <th class="r">Total</th><th class="r">Outstanding</th><th>Terms</th>
</tr></thead>
<tbody>{r_rows}
<tr class="sub"><td colspan="3">New AR This Week</td>
<td class="r">${new_total:,.2f}</td><td></td><td></td></tr>
</tbody></table>"""

    return f"""<div class="sec">
  <div class="sec-hdr">
    <div class="sec-dot" style="background:#2563eb"></div>
    <div class="sec-title">Section B — New AR This Week &nbsp;·&nbsp; {len(rows)} invoices</div>
  </div>{body}</div>"""


# ── Section C — COD vs Credit ─────────────────────────────────────────────────

def _sec_c_cod_credit(week_start, today):
    rows = frappe.db.sql(
        """
        SELECT
            CASE
                WHEN is_pos = 1 THEN 'COD / POS'
                WHEN (payment_terms_template IS NULL OR payment_terms_template = '') THEN 'COD / No Terms'
                ELSE payment_terms_template
            END AS pay_mode,
            COUNT(*)          AS cnt,
            SUM(grand_total)  AS total
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %(ws)s AND %(today)s
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
          AND si.customer NOT IN (SELECT name FROM `tabCompany`)
        GROUP BY pay_mode
        ORDER BY total DESC
        """,
        {"ws": week_start, "today": today},
        as_dict=True,
    )

    cod_total    = sum(flt(r.total) for r in rows if "COD" in (r.pay_mode or "").upper())
    credit_total = sum(flt(r.total) for r in rows if "COD" not in (r.pay_mode or "").upper())
    grand        = cod_total + credit_total
    cod_pct      = (cod_total / grand * 100) if grand else 0

    if not rows:
        body = '<div class="empty">No invoices this week.</div>'
    else:
        r_rows = "".join(
            f'<tr><td>{r.pay_mode}</td>'
            f'<td class="r">{r.cnt}</td>'
            f'<td class="r">${flt(r.total):,.2f}</td>'
            f'<td class="r">{(flt(r.total)/grand*100 if grand else 0):.1f}%</td></tr>'
            for r in rows
        )
        body = f"""<table>
<thead><tr>
  <th>Payment Mode / Terms</th><th class="r">Count</th>
  <th class="r">Amount</th><th class="r">% of Week</th>
</tr></thead>
<tbody>{r_rows}
<tr class="sub"><td>COD Total</td><td></td><td class="r">${cod_total:,.2f}</td>
  <td class="r">{cod_pct:.1f}%</td></tr>
<tr class="sub"><td>Credit Total</td><td></td><td class="r">${credit_total:,.2f}</td>
  <td class="r">{100-cod_pct:.1f}%</td></tr>
</tbody></table>"""

    return f"""<div class="sec">
  <div class="sec-hdr">
    <div class="sec-dot" style="background:#7c3aed"></div>
    <div class="sec-title">Section C — COD vs Credit Ratio</div>
  </div>{body}</div>"""


# ── Section D — Red List (30+ days past due) ──────────────────────────────────

def _sec_d_red_list():
    rows = frappe.db.sql(
        """
        SELECT
            si.customer,
            COUNT(*)                          AS invoice_count,
            SUM(si.outstanding_amount)        AS overdue_amount,
            MAX(DATEDIFF(CURDATE(), si.due_date)) AS max_days,
            COALESCE(MAX(st.sales_person), '') AS sales_person
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Team` st
               ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.due_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY)
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
          AND si.customer NOT IN (SELECT name FROM `tabCompany`)
        GROUP BY si.customer
        ORDER BY overdue_amount DESC
        """,
        as_dict=True,
    )

    # Cross-check with GL ledger balance for each customer
    if rows:
        cust_tuple = tuple(r.customer for r in rows)
        gl = frappe.db.sql(
            """
            SELECT party AS customer,
                   COALESCE(SUM(debit - credit), 0) AS balance
            FROM `tabGL Entry`
            WHERE party_type = 'Customer'
              AND party IN %(custs)s
              AND account IN %(accounts)s
              AND is_cancelled = 0
            GROUP BY party
            """,
            {"custs": cust_tuple, "accounts": tuple(DEFAULT_RECEIVABLE_ACCOUNTS)},
            as_dict=True,
        )
        gl_map = {r.customer: flt(r.balance) for r in gl}
    else:
        gl_map = {}

    def bucket(days):
        d = int(days or 0)
        if d <= 60:  return "31–60", "b-amb"
        if d <= 90:  return "61–90", "b-red"
        return "90+", "b-red"

    total_overdue = sum(flt(r.overdue_amount) for r in rows)

    if not rows:
        body = '<div class="empty">No Red List accounts. All receivables within 30 days.</div>'
    else:
        r_rows = ""
        for r in rows:
            bkt, bkt_cls = bucket(r.max_days)
            ledger_bal   = gl_map.get(r.customer, 0.0)
            r_rows += f"""<tr>
              <td>{r.customer}</td>
              <td class="r">${flt(r.overdue_amount):,.2f}</td>
              <td class="r" style="color:#2563eb">${ledger_bal:,.2f}</td>
              <td class="r">{int(r.max_days)}d</td>
              <td><span class="badge {bkt_cls}">{bkt}</span></td>
              <td class="r">{int(r.invoice_count)}</td>
              <td class="m">{r.sales_person or "—"}</td>
            </tr>"""
        body = f"""<table>
<thead><tr>
  <th>Customer</th>
  <th class="r">Overdue (SI)</th>
  <th class="r">GL Balance</th>
  <th class="r">Max Days</th>
  <th>Bucket</th>
  <th class="r">Invoices</th>
  <th>Sales Rep</th>
</tr></thead>
<tbody>{r_rows}
<tr class="sub"><td colspan="1">Red List Total</td>
  <td class="r">${total_overdue:,.2f}</td>
  <td colspan="5"></td></tr>
</tbody></table>"""

    return f"""<div class="sec">
  <div class="sec-hdr">
    <div class="sec-dot" style="background:#dc2626"></div>
    <div class="sec-title">Section D — Red List (30+ Days Overdue) &nbsp;·&nbsp; {len(rows)} customers</div>
  </div>{body}</div>"""
