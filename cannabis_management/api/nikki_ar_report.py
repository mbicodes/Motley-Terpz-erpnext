"""
Nikki's Weekly AR Accountability Report
Scheduled: Monday 8 AM UTC alongside the weekly sale report.

Columns: Account | Tier | Outstanding AR | Oldest Invoice | Last Payment |
         New Orders This Week | COD Flag

Requires CRM Lead custom fields to be populated (custom_erp_customer,
custom_relationship_tier, custom_cod_only).
"""

import frappe
from frappe.utils import flt, nowdate, getdate
from datetime import datetime, timedelta


RECIPIENTS = ["nikki@motleyterpz.com"]
CC         = ["matt@motleyterpz.com", "imran@motleyterpz.com"]

LEGACY_CUTOFF      = "2026-05-15"   # invoices before this date = Legacy AR
LEGACY_AR_TARGET   = 2_000_000.0   # estimated total legacy balance to collect
LEGACY_MONTHLY_PACE = 400_000.0    # required monthly pace to clear by harvest


# ── Entry points ──────────────────────────────────────────────────────────────

def send_nikki_ar_report():
    """Scheduled entry point."""
    if not frappe.db.exists("DocType", "CRM Lead"):
        return
    try:
        today      = getdate(nowdate())
        week_start = str(today - timedelta(days=today.weekday() + 7))
        week_end   = str(today - timedelta(days=today.weekday() + 1))
        _send(week_start, week_end, RECIPIENTS, cc=CC)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[nikki_ar_report] send failed")


@frappe.whitelist()
def send_now(week_start=None, week_end=None, recipients=None):
    """Manual trigger from desk."""
    if not frappe.db.exists("DocType", "CRM Lead"):
        frappe.throw("Frappe CRM is not installed.")
    today = getdate(nowdate())
    if not week_start:
        week_start = str(today - timedelta(days=today.weekday() + 7))
    if not week_end:
        week_end = str(today - timedelta(days=today.weekday() + 1))
    to = [recipients] if isinstance(recipients, str) else (recipients or RECIPIENTS)
    _send(week_start, week_end, to, cc=CC)
    return "sent"


def _send(week_start, week_end, recipients, cc=None):
    rows         = _get_ar_data(week_start, week_end)
    legacy_stats = _get_legacy_ar_stats()
    label        = _week_label(week_start, week_end)
    html         = _build_html(rows, label, week_start, legacy_stats)
    frappe.sendmail(
        recipients=recipients,
        cc=cc or [],
        subject=f"AR Accountability Report — {label}",
        message=html,
        delayed=False,
    )


# ── Data ─────────────────────────────────────────────────────────────────────

def _get_ar_data(week_start, week_end):
    """One row per customer with outstanding AR > 0, plus Legacy/Current split."""
    return frappe.db.sql("""
        SELECT
            si.customer,
            MAX(cl.custom_relationship_tier)          AS tier,
            MAX(cl.custom_cod_only)                   AS cod_only,
            MAX(cl.custom_company)                    AS company,
            MAX(cl.custom_revenue_size)               AS revenue_size,
            COALESCE(SUM(si.outstanding_amount), 0)   AS outstanding_ar,
            COALESCE(SUM(CASE WHEN si.posting_date < %(cutoff)s
                              THEN si.outstanding_amount ELSE 0 END), 0) AS legacy_ar,
            COALESCE(SUM(CASE WHEN si.posting_date >= %(cutoff)s
                              THEN si.outstanding_amount ELSE 0 END), 0) AS current_ar,
            MIN(CASE WHEN si.outstanding_amount > 0.01
                     THEN si.due_date ELSE NULL END)  AS oldest_due,
            (SELECT MAX(pe.posting_date)
             FROM `tabPayment Entry` pe
             WHERE pe.party = si.customer
               AND pe.party_type = 'Customer'
               AND pe.docstatus = 1
               AND pe.payment_type = 'Receive') AS last_payment,
            (SELECT COUNT(DISTINCT so.name)
             FROM `tabSales Order` so
             WHERE so.customer = si.customer
               AND so.docstatus = 1
               AND so.transaction_date BETWEEN %(ws)s AND %(we)s
            )                                         AS new_orders
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCRM Lead` cl
               ON cl.custom_erp_customer = si.customer
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
        GROUP BY si.customer
        ORDER BY legacy_ar DESC, outstanding_ar DESC
    """, {"ws": week_start, "we": week_end, "cutoff": LEGACY_CUTOFF}, as_dict=True)


def _get_legacy_ar_stats():
    """Legacy AR balance + collections this month (applied against legacy invoices)."""
    from frappe.utils import get_first_day
    today = getdate(nowdate())
    month_start = str(get_first_day(today))

    bal = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0) AS balance
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0.01
          AND posting_date < %(cutoff)s
    """, {"cutoff": LEGACY_CUTOFF}, as_dict=True)
    legacy_balance = flt(bal[0].balance) if bal else 0.0

    collected = frappe.db.sql("""
        SELECT COALESCE(SUM(per.allocated_amount), 0) AS collected
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe ON pe.name = per.parent
        JOIN `tabSales Invoice` si ON si.name = per.reference_name
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.posting_date >= %(ms)s
          AND si.posting_date < %(cutoff)s
    """, {"ms": month_start, "cutoff": LEGACY_CUTOFF}, as_dict=True)
    legacy_collected_mtd = flt(collected[0].collected) if collected else 0.0

    pct_of_target  = min((legacy_collected_mtd / LEGACY_MONTHLY_PACE * 100) if LEGACY_MONTHLY_PACE else 0, 999)
    pct_remaining  = (legacy_balance / LEGACY_AR_TARGET * 100) if LEGACY_AR_TARGET else 0

    return {
        "legacy_balance":       legacy_balance,
        "legacy_collected_mtd": legacy_collected_mtd,
        "monthly_pace_target":  LEGACY_MONTHLY_PACE,
        "pct_of_pace":          pct_of_target,
        "pct_remaining":        pct_remaining,
        "month_start":          month_start,
    }


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(rows, label, week_start, legacy_stats=None):
    total_ar    = sum(flt(r.outstanding_ar) for r in rows)
    acct_count  = len(rows)
    cod_count   = sum(1 for r in rows if r.cod_only)
    overdue_cnt = sum(1 for r in rows if r.oldest_due and getdate(r.oldest_due) < getdate(nowdate()))
    ls          = legacy_stats or {}

    has_issues = overdue_cnt > 0 or cod_count > 0

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#f1f5f9;color:#0f172a;}}
  .wrap{{max-width:820px;margin:0 auto;background:#f1f5f9;padding:20px 16px 40px;}}

  .hdr{{background:linear-gradient(150deg,#0f172a 0%,#1e3a5f 60%,#0f2942 100%);
        border-radius:16px;padding:32px 36px 28px;margin-bottom:14px;text-align:center;}}
  .hdr-ey{{font-size:10px;font-weight:700;text-transform:uppercase;
           letter-spacing:2.5px;color:rgba(255,255,255,.4);margin-bottom:10px;}}
  .hdr-tt{{font-size:26px;font-weight:800;color:#fff;margin-bottom:12px;}}
  .hdr-tt span{{color:#38bdf8;}}
  .hdr-dt{{display:inline-block;background:rgba(255,255,255,.1);
           border:1px solid rgba(255,255,255,.15);border-radius:20px;
           padding:6px 18px;color:rgba(255,255,255,.85);font-size:13px;font-weight:600;}}

  .kpi-bar{{display:flex;gap:12px;margin-bottom:14px;flex-wrap:wrap;}}
  .kpi{{flex:1;min-width:140px;background:#fff;border-radius:12px;
        border:1px solid #e2e8f0;padding:16px 18px;
        box-shadow:0 1px 4px rgba(0,0,0,.07);}}
  .kpi-l{{font-size:10px;font-weight:700;text-transform:uppercase;
          letter-spacing:.6px;color:#64748b;margin-bottom:7px;}}
  .kpi-v{{font-size:20px;font-weight:800;line-height:1;}}
  .kpi-s{{font-size:11px;color:#94a3b8;margin-top:4px;}}
  .red{{color:#dc2626;}} .amber{{color:#d97706;}}
  .blue{{color:#2563eb;}} .green{{color:#059669;}}

  .card{{background:#fff;border-radius:12px;border:1px solid #e2e8f0;
         box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:16px;overflow:hidden;}}
  .card-hdr{{padding:12px 18px;display:flex;align-items:center;gap:10px;
             border-bottom:1px solid #f1f5f9;}}
  .card-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0;}}
  .card-title{{font-size:12px;font-weight:700;text-transform:uppercase;
               letter-spacing:.4px;color:#0f172a;}}
  .card-meta{{margin-left:auto;font-size:11px;color:#64748b;font-weight:600;}}

  table{{width:100%;border-collapse:collapse;font-size:12px;}}
  th{{padding:8px 12px;background:#f8fafc;color:#64748b;font-weight:700;
      font-size:10px;text-transform:uppercase;letter-spacing:.4px;
      text-align:left;border-bottom:1px solid #e2e8f0;white-space:nowrap;}}
  th.r{{text-align:right;}}
  td{{padding:8px 12px;border-bottom:1px solid #f8fafc;vertical-align:middle;}}
  td.r{{text-align:right;font-variant-numeric:tabular-nums;}}
  td.m{{color:#94a3b8;font-size:11px;}}
  tr:last-child td{{border-bottom:none;}}
  tr.sub td{{background:#f8fafc;font-weight:700;border-top:2px solid #e2e8f0;}}
  tr.hi td{{background:#fff7ed;}}

  .tier{{display:inline-block;padding:2px 8px;border-radius:10px;
         font-size:9px;font-weight:700;text-transform:uppercase;}}
  .tier-aaa{{background:#fef3c7;color:#92400e;}}
  .tier-aa{{background:#dbeafe;color:#1d4ed8;}}
  .tier-a{{background:#dcfce7;color:#166534;}}
  .tier-ff{{background:#f3e8ff;color:#6d28d9;}}
  .tier-wip{{background:#f1f5f9;color:#475569;}}
  .tier-lead{{background:#f1f5f9;color:#94a3b8;}}

  .cod{{display:inline-block;padding:2px 7px;border-radius:4px;
        font-size:9px;font-weight:700;background:#fef3c7;color:#92400e;}}
  .overdue{{display:inline-block;padding:2px 7px;border-radius:4px;
            font-size:9px;font-weight:700;background:#fee2e2;color:#991b1b;}}
  .ok{{display:inline-block;padding:2px 7px;border-radius:4px;
       font-size:9px;font-weight:700;background:#d1fae5;color:#065f46;}}

  .empty{{padding:20px;text-align:center;color:#94a3b8;font-style:italic;font-size:12px;}}
  .footer{{text-align:center;color:#94a3b8;font-size:11px;margin-top:8px;}}
</style>
</head>
<body>
<div class="wrap">

  <div class="hdr">
    <div class="hdr-ey">Motley Terpz &amp; TSBC Ranch — Accounts Receivable</div>
    <div class="hdr-tt">AR <span>Accountability</span> Report</div>
    <div class="hdr-dt">{label}</div>
  </div>

  <div class="kpi-bar">
    <div class="kpi">
      <div class="kpi-l">Total Outstanding AR</div>
      <div class="kpi-v" style="color:#94a3b8;text-decoration:line-through;font-size:16px">{_fmt(total_ar)}</div>
      <div class="kpi-s">{acct_count} account{'s' if acct_count != 1 else ''} · see breakdown below</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">Legacy AR (pre-May 15)</div>
      <div class="kpi-v red">{_fmt(ls.get('legacy_balance', 0))}</div>
      <div class="kpi-s">old debt — must collect before harvest</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">Overdue Accounts</div>
      <div class="kpi-v amber">{overdue_cnt}</div>
      <div class="kpi-s">past due date</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">COD Accounts w/ AR</div>
      <div class="kpi-v amber">{cod_count}</div>
      <div class="kpi-s">need attention</div>
    </div>
  </div>

  {_legacy_tracker(ls)}

  <div class="card">
    <div class="card-hdr">
      <div class="card-dot" style="background:#dc2626"></div>
      <div class="card-title">Outstanding AR by Account</div>
      <div class="card-meta">{acct_count} accounts &nbsp;·&nbsp; {_fmt(total_ar)} total</div>
    </div>
    {_ar_table(rows)}
  </div>

  <div class="footer">
    Auto-generated by ERPNext &nbsp;·&nbsp; {datetime.now().strftime("%B %-d, %Y %H:%M")} UTC
    &nbsp;·&nbsp; Do not reply to this message.
  </div>

</div>
</body></html>"""


def _legacy_tracker(ls):
    """Card showing Legacy AR balance vs monthly collection pace."""
    if not ls:
        return ""
    balance   = flt(ls.get("legacy_balance", 0))
    collected = flt(ls.get("legacy_collected_mtd", 0))
    pace      = flt(ls.get("monthly_pace_target", 400_000))
    pct       = min(flt(ls.get("pct_of_pace", 0)), 100)
    bar_color = "#059669" if pct >= 100 else "#d97706" if pct >= 50 else "#dc2626"

    return f"""
  <div class="card" style="margin-bottom:14px;">
    <div class="card-hdr">
      <div class="card-dot" style="background:#dc2626"></div>
      <div class="card-title">Legacy AR Collection Tracker — May 15 Fresh Start</div>
      <div class="card-meta">Target: {_fmt(pace)}/month to clear by harvest</div>
    </div>
    <div style="padding:14px 18px;">
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px;">
        <div style="flex:1;min-width:140px;">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#64748b;margin-bottom:4px;">Legacy AR Remaining</div>
          <div style="font-size:22px;font-weight:800;color:#dc2626;">{_fmt(balance)}</div>
          <div style="font-size:11px;color:#94a3b8;">invoices before May 15 · target $0</div>
        </div>
        <div style="flex:1;min-width:140px;">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#64748b;margin-bottom:4px;">Collected This Month (Legacy)</div>
          <div style="font-size:22px;font-weight:800;color:#059669;">{_fmt(collected)}</div>
          <div style="font-size:11px;color:#94a3b8;">pace target: {_fmt(pace)}/month</div>
        </div>
        <div style="flex:1;min-width:140px;">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#64748b;margin-bottom:4px;">Monthly Pace Progress</div>
          <div style="font-size:22px;font-weight:800;color:{bar_color};">{pct:.0f}%</div>
          <div style="font-size:11px;color:#94a3b8;">of ${pace/1000:.0f}k/month target</div>
        </div>
      </div>
      <div style="background:#f1f5f9;border-radius:6px;height:8px;overflow:hidden;">
        <div style="background:{bar_color};height:100%;width:{pct:.1f}%;transition:width .3s;"></div>
      </div>
      <div style="font-size:11px;color:#94a3b8;margin-top:6px;">
        At current pace: requires {_fmt(pace)}/month · current balance needs ~{int(balance/pace) if pace else '?'} months to clear
      </div>
    </div>
  </div>"""


def _ar_table(rows):
    if not rows:
        return '<div class="empty">No outstanding AR this week.</div>'

    today = getdate(nowdate())

    html = """<table><thead><tr>
      <th>Account</th><th>Company</th><th>Tier</th><th>Rev. Size</th>
      <th class="r">Legacy AR</th>
      <th class="r">Current AR</th>
      <th class="r">Total AR</th>
      <th>Oldest Due</th>
      <th>Last Payment</th>
      <th class="r">New Orders</th>
      <th>COD</th>
    </tr></thead><tbody>"""

    for r in rows:
        is_overdue = r.oldest_due and getdate(r.oldest_due) < today
        is_cod     = int(r.cod_only or 0)
        has_legacy = flt(r.legacy_ar) > 0
        row_cls    = ' class="hi"' if is_overdue or is_cod else ""

        oldest_str = str(r.oldest_due)[:10] if r.oldest_due else "—"
        oldest_html = (
            f'<span class="overdue">{oldest_str}</span>'
            if is_overdue else
            f'<span class="ok">{oldest_str}</span>' if r.oldest_due else "—"
        )

        last_pay = str(r.last_payment)[:10] if r.last_payment else '<span class="overdue">Never</span>'
        cod_html = '<span class="cod">COD</span>' if is_cod else "—"

        tier  = (r.tier or "").strip()
        t_key = tier.lower().replace(" & ", "").replace("/", "").replace(" ", "")
        tier_map = {"aaa": "tier-aaa", "aa": "tier-aa", "a": "tier-a",
                    "friendsfamily": "tier-ff", "wip": "tier-wip", "lead": "tier-lead"}
        tier_cls  = tier_map.get(t_key, "tier-lead")
        tier_html = f'<span class="tier {tier_cls}">{_esc(tier)}</span>' if tier else "—"

        legacy_fmt  = f'<span style="color:#dc2626;font-weight:700">{_fmt(r.legacy_ar)}</span>' if has_legacy else '<span style="color:#94a3b8">—</span>'
        current_fmt = _fmt(r.current_ar) if flt(r.current_ar) > 0 else "—"

        html += f"""<tr{row_cls}>
          <td style="font-weight:700">{_esc(r.customer)}</td>
          <td class="m">{_esc(r.company or "—")}</td>
          <td>{tier_html}</td>
          <td class="m" style="font-size:11px">{_esc(r.revenue_size or "—")}</td>
          <td class="r">{legacy_fmt}</td>
          <td class="r">{current_fmt}</td>
          <td class="r" style="font-weight:700;color:#dc2626">{_fmt(r.outstanding_ar)}</td>
          <td>{oldest_html}</td>
          <td class="m">{last_pay}</td>
          <td class="r">{int(r.new_orders or 0)}</td>
          <td>{cod_html}</td>
        </tr>"""

    total_legacy  = sum(flt(r.legacy_ar)  for r in rows)
    total_current = sum(flt(r.current_ar) for r in rows)
    total_all     = sum(flt(r.outstanding_ar) for r in rows)
    html += f"""<tr class="sub">
      <td colspan="4">Total</td>
      <td class="r" style="color:#dc2626">{_fmt(total_legacy)}</td>
      <td class="r">{_fmt(total_current)}</td>
      <td class="r">{_fmt(total_all)}</td>
      <td colspan="4"></td>
    </tr></tbody></table>"""
    return html


# ── Utilities ─────────────────────────────────────────────────────────────────

def _week_label(week_start, week_end):
    s = datetime.strptime(week_start, "%Y-%m-%d").strftime("%b %-d")
    e = datetime.strptime(week_end,   "%Y-%m-%d").strftime("%b %-d, %Y")
    return f"{s} – {e}"


def _fmt(v):
    if not v:
        return "$ 0.00"
    return "$ " + "{:,.2f}".format(flt(v))


def _esc(s):
    if not s:
        return ""
    return (str(s)
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
