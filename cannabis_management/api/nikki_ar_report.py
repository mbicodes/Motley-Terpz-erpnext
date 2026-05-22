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
    rows  = _get_ar_data(week_start, week_end)
    label = _week_label(week_start, week_end)
    html  = _build_html(rows, label, week_start)
    frappe.sendmail(
        recipients=recipients,
        cc=cc or [],
        subject=f"AR Accountability Report — {label}",
        message=html,
        delayed=False,
    )


# ── Data ─────────────────────────────────────────────────────────────────────

def _get_ar_data(week_start, week_end):
    """
    One row per customer that has outstanding AR > 0.
    Pulls tier + COD flag from CRM Lead if linked.
    """
    return frappe.db.sql("""
        SELECT
            si.customer,
            MAX(cl.custom_relationship_tier)          AS tier,
            MAX(cl.custom_cod_only)                   AS cod_only,
            COALESCE(SUM(si.outstanding_amount), 0)   AS outstanding_ar,
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
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0.01
        GROUP BY si.customer
        ORDER BY outstanding_ar DESC
    """, {"ws": week_start, "we": week_end}, as_dict=True)


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(rows, label, week_start):
    total_ar    = sum(flt(r.outstanding_ar) for r in rows)
    acct_count  = len(rows)
    cod_count   = sum(1 for r in rows if r.cod_only)
    overdue_cnt = sum(1 for r in rows if r.oldest_due and getdate(r.oldest_due) < getdate(nowdate()))

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
      <div class="kpi-v red">{_fmt(total_ar)}</div>
      <div class="kpi-s">{acct_count} account{'s' if acct_count != 1 else ''}</div>
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


def _ar_table(rows):
    if not rows:
        return '<div class="empty">No outstanding AR this week.</div>'

    today = getdate(nowdate())

    html = """<table><thead><tr>
      <th>Account</th><th>Tier</th>
      <th class="r">Outstanding AR</th>
      <th>Oldest Due Date</th>
      <th>Last Payment</th>
      <th class="r">New Orders</th>
      <th>COD</th>
    </tr></thead><tbody>"""

    for r in rows:
        is_overdue = r.oldest_due and getdate(r.oldest_due) < today
        is_cod     = int(r.cod_only or 0)
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
        tier_cls = tier_map.get(t_key, "tier-lead")
        tier_html = f'<span class="tier {tier_cls}">{_esc(tier)}</span>' if tier else "—"

        html += f"""<tr{row_cls}>
          <td style="font-weight:700">{_esc(r.customer)}</td>
          <td>{tier_html}</td>
          <td class="r" style="font-weight:700;color:#dc2626">{_fmt(r.outstanding_ar)}</td>
          <td>{oldest_html}</td>
          <td class="m">{last_pay}</td>
          <td class="r">{int(r.new_orders or 0)}</td>
          <td>{cod_html}</td>
        </tr>"""

    total = sum(flt(r.outstanding_ar) for r in rows)
    html += f"""<tr class="sub">
      <td colspan="2">Total</td>
      <td class="r">{_fmt(total)}</td>
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
