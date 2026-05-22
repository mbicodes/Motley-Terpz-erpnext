"""
Weekly Sale Report
Scheduled: Monday 8 AM UTC — covers the previous Mon–Sun week.
Sections:
  A. Sales Orders for the week
  B. Weekly AR Gathered  — invoices created this week, payment NOT yet received
  C. Weekly AR Collected — invoices created this week, payment received
  D. AR Legacy Collected — invoices created BEFORE this week, paid THIS week
"""

import frappe
from frappe.utils import flt, nowdate, getdate
from datetime import datetime, timedelta


RECIPIENTS = [
    "jamie@motleyterpz.com",
    "matt@motleyterpz.com",
    "imran@motleyterpz.com",
    "mbi@alltechvirtual.com",
    "nikki@motleyterpz.com",
    "osama.ahmad@alltechvirtual.com",
]

SIGNOFF_TO = ["muhammad@motleyterpz.com", "bot@motleyterpz.com"]
SIGNOFF_CC = ["matt@motleyterpz.com", "imran@motleyterpz.com"]

COMPANIES = ["Motley Terpz", "TSBC Ranch"]


# ── Week helpers ──────────────────────────────────────────────────────────────

def _week_range(anchor=None):
    """
    Return (week_start, week_end) as 'YYYY-MM-DD' strings.
    anchor = a date string; defaults to last completed Mon–Sun week.
    When called on Monday with no anchor, returns the previous Mon–Sun.
    """
    if anchor:
        ref = getdate(anchor)
    else:
        today = getdate(nowdate())
        # day_of_week: Mon=0 … Sun=6
        ref = today - timedelta(days=today.weekday() + 7)   # last Monday

    # Snap ref to the Monday of its week
    monday = ref - timedelta(days=ref.weekday())
    sunday = monday + timedelta(days=6)
    return str(monday), str(sunday)


def _week_label(week_start, week_end):
    s = datetime.strptime(week_start, "%Y-%m-%d").strftime("%b %-d")
    e = datetime.strptime(week_end,   "%Y-%m-%d").strftime("%b %-d, %Y")
    return f"{s} – {e}"


# ── Scheduler entry point ─────────────────────────────────────────────────────

def send_weekly_report():
    week_start, week_end = _week_range()
    cache_key = f"weekly_report_sent_{week_start}"
    if frappe.cache().get_value(cache_key):
        frappe.logger().info(f"[weekly_report] already sent for {week_start}, skipping")
        return
    try:
        html = _build_email(week_start, week_end)
        label = _week_label(week_start, week_end)
        frappe.sendmail(
            recipients=RECIPIENTS,
            subject=f"Weekly Sale Report — {label}",
            message=html,
            delayed=False,
        )
        _send_week_closure_email(week_start, week_end)
        frappe.cache().set_value(cache_key, True, expires_in_sec=8 * 24 * 3600)
        frappe.logger().info(f"[weekly_report] sent for {week_start}–{week_end}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[weekly_report] send failed")


# ── Manual trigger ────────────────────────────────────────────────────────────

@frappe.whitelist()
def send_now_2(week_start=None, week_end=None):
    if not week_start:
        week_start, week_end = _week_range()
    if not week_end:
        week_end = str(getdate(week_start) + timedelta(days=6))
    html  = _build_email(week_start, week_end)
    label = _week_label(week_start, week_end)
    frappe.sendmail(
        recipients=["mbi@alltechvirtual.com", "osama.ahmad@alltechvirtual.com"],
        subject=f"Weekly Sale Report — {label}",
        message=html,
        delayed=False,
    )
    return "sent"


@frappe.whitelist()
def send_now(week_start=None, week_end=None):
    if not week_start:
        week_start, week_end = _week_range()
    if not week_end:
        week_end = str(getdate(week_start) + timedelta(days=6))
    html  = _build_email(week_start, week_end)
    label = _week_label(week_start, week_end)
    frappe.sendmail(
        recipients=RECIPIENTS,
        subject=f"Weekly Sale Report — {label}",
        message=html,
        delayed=False,
    )
    _send_week_closure_email(week_start, week_end)
    return "sent"


# ── Data queries ──────────────────────────────────────────────────────────────

def _get_weekly_sales_orders(week_start, week_end):
    return frappe.db.sql("""
        SELECT
            so.name, so.customer, so.grand_total, so.company,
            soi.item_group,
            SUM(soi.qty)    AS qty,
            SUM(soi.amount) AS amount
        FROM `tabSales Order` so
        JOIN `tabSales Order Item` soi ON soi.parent = so.name
        WHERE so.transaction_date BETWEEN %s AND %s
          AND so.docstatus = 1
        GROUP BY so.name, soi.item_group
        ORDER BY so.customer, soi.item_group
    """, (week_start, week_end), as_dict=True)


def _get_ar_gathered(week_start, week_end):
    """Invoices created this week with NO payment received (outstanding = grand_total)."""
    return frappe.db.sql("""
        SELECT
            si.name, si.customer, si.grand_total,
            si.outstanding_amount, si.posting_date, si.company,
            sii.item_group,
            SUM(sii.qty)    AS qty,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.posting_date BETWEEN %s AND %s
          AND si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND si.outstanding_amount >= (si.grand_total - 0.01)
        GROUP BY si.name, sii.item_group
        ORDER BY si.customer, sii.item_group
    """, (week_start, week_end), as_dict=True)


def _get_ar_collected(week_start, week_end):
    """Invoices created this week with payment received (outstanding = 0)."""
    return frappe.db.sql("""
        SELECT
            si.name, si.customer, si.grand_total,
            si.outstanding_amount, si.posting_date, si.company,
            sii.item_group,
            SUM(sii.qty)    AS qty,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.posting_date BETWEEN %s AND %s
          AND si.docstatus = 1
          AND si.outstanding_amount <= 0.01
        GROUP BY si.name, sii.item_group
        ORDER BY si.customer, sii.item_group
    """, (week_start, week_end), as_dict=True)


def _get_ar_legacy_collected(week_start, week_end):
    """
    Payment Entries posted THIS week that are linked to invoices created
    BEFORE this week.  Returns one row per payment+invoice allocation.
    """
    return frappe.db.sql("""
        SELECT
            pe.name          AS payment_name,
            pe.party         AS customer,
            pe.posting_date  AS payment_date,
            pe.mode_of_payment,
            pe.company,
            si.name          AS invoice,
            si.posting_date  AS invoice_date,
            si.grand_total   AS invoice_total,
            per.allocated_amount AS collected_amount
        FROM `tabPayment Entry` pe
        JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
        JOIN `tabSales Invoice` si ON si.name = per.reference_name
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.posting_date BETWEEN %s AND %s
          AND si.posting_date < %s
          AND per.reference_doctype = 'Sales Invoice'
        ORDER BY pe.party, pe.posting_date, si.posting_date
    """, (week_start, week_end, week_start), as_dict=True)


# ── Email builder ─────────────────────────────────────────────────────────────

def _build_email(week_start, week_end):
    so_rows      = _get_weekly_sales_orders(week_start, week_end)
    gathered     = _get_ar_gathered(week_start, week_end)
    collected    = _get_ar_collected(week_start, week_end)
    legacy       = _get_ar_legacy_collected(week_start, week_end)
    label        = _week_label(week_start, week_end)

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
          background:#f1f5f9; color:#0f172a; }}
  .wrap {{ max-width:780px; margin:0 auto; background:#f1f5f9; padding:20px 16px 40px; }}

  /* ── Header ── */
  .hdr {{ background:linear-gradient(150deg,#0f172a 0%,#1e3a5f 60%,#0f2942 100%);
          border-radius:16px; padding:36px 36px 30px; margin-bottom:14px;
          text-align:center; }}
  .hdr-eyebrow {{ font-size:10px; font-weight:700; text-transform:uppercase;
                  letter-spacing:2.5px; color:rgba(255,255,255,.4);
                  margin-bottom:12px; }}
  .hdr-title {{ font-size:28px; font-weight:800; color:#fff;
                letter-spacing:.2px; line-height:1.1; margin-bottom:14px; }}
  .hdr-title span {{ color:#38bdf8; }}
  .hdr-date {{ display:inline-block; background:rgba(255,255,255,.1);
               border:1px solid rgba(255,255,255,.15); border-radius:20px;
               padding:7px 20px; color:rgba(255,255,255,.85); font-size:13px;
               font-weight:600; }}

  /* ── KPI bar ── */
  .kpi-bar {{ display:flex; gap:14px; margin-bottom:20px; flex-wrap:wrap; }}
  .kpi {{ flex:1; min-width:150px; background:#fff; border-radius:12px;
          border:1px solid #e2e8f0; padding:20px 22px;
          box-shadow:0 1px 4px rgba(0,0,0,.07); }}
  .kpi-lbl {{ font-size:10px; font-weight:700; text-transform:uppercase;
              letter-spacing:.6px; color:#64748b; margin-bottom:8px; }}
  .kpi-val {{ font-size:22px; font-weight:800; color:#0f172a; line-height:1; }}
  .kpi-sub {{ font-size:12px; color:#94a3b8; margin-top:6px; }}
  .kpi.accent-blue   .kpi-val {{ color:#2563eb; }}
  .kpi.accent-green  .kpi-val {{ color:#059669; }}
  .kpi.accent-violet .kpi-val {{ color:#7c3aed; }}
  .kpi.accent-amber  .kpi-val {{ color:#d97706; }}
  .kpi.accent-red    .kpi-val {{ color:#dc2626; }}

  /* ── Section cards ── */
  .card {{ background:#fff; border-radius:12px; border:1px solid #e2e8f0;
           box-shadow:0 1px 3px rgba(0,0,0,.06); margin-bottom:20px;
           overflow:hidden; }}
  .card-hdr {{ padding:14px 20px; display:flex; align-items:center; gap:10px;
               border-bottom:1px solid #f1f5f9; }}
  .card-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .card-title {{ font-size:13px; font-weight:700; color:#0f172a;
                 text-transform:uppercase; letter-spacing:.4px; }}
  .card-count {{ margin-left:auto; background:#f8fafc; border:1px solid #e2e8f0;
                 border-radius:20px; padding:2px 10px; font-size:11px;
                 font-weight:600; color:#64748b; }}
  .card-total {{ font-size:13px; font-weight:700; color:#059669; margin-left:8px; }}

  /* ── Tables ── */
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  th {{ padding:9px 14px; background:#f8fafc; color:#64748b; font-weight:700;
        font-size:10px; text-transform:uppercase; letter-spacing:.4px;
        text-align:left; border-bottom:1px solid #e2e8f0; white-space:nowrap; }}
  th.r {{ text-align:right; }}
  td {{ padding:9px 14px; border-bottom:1px solid #f1f5f9; color:#0f172a;
        vertical-align:top; }}
  td.r {{ text-align:right; font-variant-numeric:tabular-nums; }}
  td.muted {{ color:#94a3b8; font-size:11px; }}
  td.bold  {{ font-weight:700; }}
  tr:last-child td {{ border-bottom:none; }}
  tr.subtotal td {{ background:#f8fafc; font-weight:700; border-top:2px solid #e2e8f0; }}
  tr.group-hdr td {{ background:#f1f5f9; font-weight:700; color:#374151;
                     font-size:11px; padding:6px 14px; }}

  /* ── Entity badge ── */
  .ent {{ display:inline-block; padding:1px 7px; border-radius:20px;
          font-size:9px; font-weight:700; text-transform:uppercase; }}
  .ent-mt {{ background:#ede9fe; color:#6d28d9; }}
  .ent-ts {{ background:#d1fae5; color:#065f46; }}

  /* ── Mode badge ── */
  .mode {{ display:inline-block; padding:2px 8px; border-radius:6px;
           font-size:10px; font-weight:700; }}
  .mode-bank  {{ background:#dbeafe; color:#1d4ed8; }}
  .mode-cash  {{ background:#fef3c7; color:#92400e; }}
  .mode-other {{ background:#f1f5f9; color:#475569; }}

  /* ── Status badge ── */
  .badge-unpaid  {{ display:inline-block; padding:2px 8px; border-radius:6px;
                    font-size:10px; font-weight:700;
                    background:#fee2e2; color:#991b1b; }}
  .badge-paid    {{ display:inline-block; padding:2px 8px; border-radius:6px;
                    font-size:10px; font-weight:700;
                    background:#d1fae5; color:#065f46; }}

  /* ── Empty state ── */
  .empty {{ padding:24px; text-align:center; color:#94a3b8;
            font-size:12px; font-style:italic; }}

  /* ── Footer ── */
  .footer {{ text-align:center; color:#94a3b8; font-size:11px;
             margin-top:8px; padding:0 16px; }}
</style>
</head>
<body>
<div class="wrap">

  <!-- Header -->
  <div class="hdr">
    <div class="hdr-eyebrow">Motley Terpz &amp; TSBC Ranch</div>
    <div class="hdr-title">Weekly <span>Sale</span> Report</div>
    <div class="hdr-date">{label}</div>
  </div>

{_kpi_bar(so_rows, gathered, collected, legacy)}
{_so_section(so_rows)}
{_gathered_section(gathered)}
{_collected_section(collected)}
{_legacy_section(legacy)}
{_signoff_section(gathered, collected, legacy, label)}

  <div class="footer">
    Auto-generated by ERPNext &nbsp;·&nbsp; {datetime.now().strftime("%B %-d, %Y %H:%M")} UTC &nbsp;·&nbsp;
    Do not reply to this message.
  </div>

</div>
</body>
</html>"""
    return html


# ── KPI bar ───────────────────────────────────────────────────────────────────

def _kpi_bar(so_rows, gathered, collected, legacy):
    so_count     = len({r.name for r in so_rows})
    so_total     = sum(flt(r.grand_total) for r in {r.name: r for r in so_rows}.values())

    g_count      = len({r.name for r in gathered})
    g_total      = sum(flt(r.grand_total) for r in {r.name: r for r in gathered}.values())

    c_count      = len({r.name for r in collected})
    c_total      = sum(flt(r.grand_total) for r in {r.name: r for r in collected}.values())

    leg_total    = sum(flt(r.collected_amount) for r in legacy)
    leg_count    = len({r.payment_name for r in legacy})

    return f"""  <div class="kpi-bar">
    <div class="kpi accent-blue">
      <div class="kpi-lbl">Sales Orders</div>
      <div class="kpi-val">{so_count}</div>
      <div class="kpi-sub">{_fmt(so_total)}</div>
    </div>
    <div class="kpi accent-red">
      <div class="kpi-lbl">AR Gathered</div>
      <div class="kpi-val">{_fmt(g_total)}</div>
      <div class="kpi-sub">{g_count} invoice{'s' if g_count != 1 else ''} unpaid</div>
    </div>
    <div class="kpi accent-green">
      <div class="kpi-lbl">AR Collected</div>
      <div class="kpi-val">{_fmt(c_total)}</div>
      <div class="kpi-sub">{c_count} invoice{'s' if c_count != 1 else ''} paid</div>
    </div>
    <div class="kpi accent-violet">
      <div class="kpi-lbl">Legacy Collected</div>
      <div class="kpi-val">{_fmt(leg_total)}</div>
      <div class="kpi-sub">{leg_count} payment{'s' if leg_count != 1 else ''}</div>
    </div>
  </div>"""


# ── Section: Sales Orders ─────────────────────────────────────────────────────

def _so_section(rows):
    count = len({r.name for r in rows})
    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    body  = _doc_table(rows, "Sales Order") + _ig_summary(rows)
    return _card("#2563eb", "Sales Orders — This Week",
                 f"{count} order{'s' if count != 1 else ''}", _fmt(total), body)


# ── Section: AR Gathered ──────────────────────────────────────────────────────

def _gathered_section(rows):
    count = len({r.name for r in rows})
    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    if not rows:
        body = '<div class="empty">No unpaid invoices created this week.</div>'
    else:
        body = _ar_invoice_table(rows, show_outstanding=True) + _ig_summary(rows)
    return _card("#dc2626", "AR Gathered — Invoices Created, Not Yet Paid",
                 f"{count} invoice{'s' if count != 1 else ''}", _fmt(total), body)


# ── Section: AR Collected ─────────────────────────────────────────────────────

def _collected_section(rows):
    count = len({r.name for r in rows})
    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    if not rows:
        body = '<div class="empty">No invoices from this week have been fully collected.</div>'
    else:
        body = _ar_invoice_table(rows, show_outstanding=False) + _ig_summary(rows)
    return _card("#059669", "AR Collected — Invoices Created &amp; Paid This Week",
                 f"{count} invoice{'s' if count != 1 else ''}", _fmt(total), body)


# ── Section: Legacy Collected ─────────────────────────────────────────────────

def _legacy_section(rows):
    total     = sum(flt(r.collected_amount) for r in rows)
    pay_count = len({r.payment_name for r in rows})
    if not rows:
        body = '<div class="empty">No legacy invoice payments received this week.</div>'
    else:
        body = _legacy_table(rows)
    return _card("#7c3aed", "AR Legacy Collected — Old Invoices Paid This Week",
                 f"{pay_count} payment{'s' if pay_count != 1 else ''}", _fmt(total), body)


# ── Table builders ────────────────────────────────────────────────────────────

def _doc_table(rows, doc_type_label):
    if not rows:
        return f'<div class="empty">No {doc_type_label}s this week.</div>'

    docs = {}
    for r in rows:
        if r.name not in docs:
            docs[r.name] = {"name": r.name, "customer": r.customer,
                            "grand_total": r.grand_total, "company": r.company,
                            "items": []}
        docs[r.name]["items"].append(r)

    html = """<table>
      <thead><tr>
        <th>Client</th><th>Entity</th><th>Item Group</th>
        <th class="r">Qty</th><th class="r">Line Amt</th><th class="r">Order Total</th>
      </tr></thead><tbody>"""

    for doc_name, doc in docs.items():
        ent_cls = "ent-mt" if doc["company"] == "Motley Terpz" else "ent-ts"
        ent_lbl = "Motley"  if doc["company"] == "Motley Terpz" else "TSBC"
        items = doc["items"]
        for j, item in enumerate(items):
            first = j == 0
            last  = j == len(items) - 1
            html += f"""<tr>
              <td class="bold">{_esc(doc["customer"]) if first else ""}</td>
              <td>{"<span class='ent " + ent_cls + "'>" + ent_lbl + "</span>" if first else ""}</td>
              <td>{_esc(item.item_group or "—")}</td>
              <td class="r">{_qty(item.qty)}</td>
              <td class="r">{_fmt(item.amount)}</td>
              <td class="r bold">{"" if not last else _fmt(doc["grand_total"])}</td>
            </tr>"""

    total_amt  = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    total_docs = len(docs)
    html += f"""<tr class="subtotal">
      <td colspan="5">Total — {total_docs} {doc_type_label}{"s" if total_docs != 1 else ""}</td>
      <td class="r">{_fmt(total_amt)}</td>
    </tr></tbody></table>"""
    return html


def _ar_invoice_table(rows, show_outstanding=True):
    """Table for AR Gathered / AR Collected — invoice rows with item group detail."""
    docs = {}
    for r in rows:
        if r.name not in docs:
            docs[r.name] = {"name": r.name, "customer": r.customer,
                            "grand_total": r.grand_total,
                            "outstanding_amount": r.outstanding_amount,
                            "posting_date": r.posting_date,
                            "company": r.company, "items": []}
        docs[r.name]["items"].append(r)

    status_col = "<th>Status</th>" if show_outstanding else "<th>Status</th>"
    html = f"""<table>
      <thead><tr>
        <th>Client</th><th>Entity</th><th>Invoice Date</th>
        <th>Item Group</th><th class="r">Qty</th><th class="r">Line Amt</th>
        <th class="r">Invoice Total</th>{status_col}
      </tr></thead><tbody>"""

    for doc_name, doc in docs.items():
        ent_cls = "ent-mt" if doc["company"] == "Motley Terpz" else "ent-ts"
        ent_lbl = "Motley"  if doc["company"] == "Motley Terpz" else "TSBC"
        items = doc["items"]
        outstanding = flt(doc["outstanding_amount"])
        status_html = (
            f'<span class="badge-unpaid">Unpaid {_fmt(outstanding)}</span>'
            if show_outstanding
            else '<span class="badge-paid">Collected</span>'
        )
        for j, item in enumerate(items):
            first = j == 0
            last  = j == len(items) - 1
            inv_date = str(doc["posting_date"])[:10] if first else ""
            html += f"""<tr>
              <td class="bold">{_esc(doc["customer"]) if first else ""}</td>
              <td>{"<span class='ent " + ent_cls + "'>" + ent_lbl + "</span>" if first else ""}</td>
              <td class="muted">{inv_date}</td>
              <td>{_esc(item.item_group or "—")}</td>
              <td class="r">{_qty(item.qty)}</td>
              <td class="r">{_fmt(item.amount)}</td>
              <td class="r bold">{"" if not last else _fmt(doc["grand_total"])}</td>
              <td>{status_html if last else ""}</td>
            </tr>"""

    total_amt  = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    total_docs = len(docs)
    html += f"""<tr class="subtotal">
      <td colspan="6">Total — {total_docs} invoice{"s" if total_docs != 1 else ""}</td>
      <td class="r">{_fmt(total_amt)}</td><td></td>
    </tr></tbody></table>"""
    return html


def _legacy_table(rows):
    """Table for Legacy Collected — payment rows linked to old invoices."""
    html = """<table>
      <thead><tr>
        <th>Client</th><th>Entity</th><th>Payment Date</th>
        <th>Mode</th><th>Invoice</th><th class="r">Inv. Date</th>
        <th class="r">Inv. Total</th><th class="r">Collected</th>
      </tr></thead><tbody>"""

    # Group by payment
    payments = {}
    for r in rows:
        if r.payment_name not in payments:
            payments[r.payment_name] = []
        payments[r.payment_name].append(r)

    for pay_name, pay_rows in payments.items():
        for j, r in enumerate(pay_rows):
            first = j == 0
            ent_cls = "ent-mt" if r.company == "Motley Terpz" else "ent-ts"
            ent_lbl = "Motley"  if r.company == "Motley Terpz" else "TSBC"
            mt      = _mode_type(r.mode_of_payment)
            mcls    = f"mode-{mt}"
            html += f"""<tr>
              <td class="bold">{_esc(r.customer) if first else ""}</td>
              <td>{"<span class='ent " + ent_cls + "'>" + ent_lbl + "</span>" if first else ""}</td>
              <td class="muted">{str(r.payment_date)[:10] if first else ""}</td>
              <td>{"<span class='mode " + mcls + "'>" + _esc(r.mode_of_payment) + "</span>" if first else ""}</td>
              <td class="muted">{r.invoice}</td>
              <td class="r muted">{str(r.invoice_date)[:10]}</td>
              <td class="r">{_fmt(r.invoice_total)}</td>
              <td class="r bold">{_fmt(r.collected_amount)}</td>
            </tr>"""

    leg_total = sum(flt(r.collected_amount) for r in rows)
    html += f"""<tr class="subtotal">
      <td colspan="7">Total Collected</td>
      <td class="r">{_fmt(leg_total)}</td>
    </tr></tbody></table>"""
    return html


def _ig_summary(rows):
    if not rows:
        return ""
    ig = {}
    for r in rows:
        key = r.item_group or "Other"
        if key not in ig:
            ig[key] = {"qty": 0, "amount": 0}
        ig[key]["qty"]    += flt(r.qty)
        ig[key]["amount"] += flt(r.amount)

    html = """<table style="margin-top:0">
      <thead><tr style="background:#fafbff">
        <th colspan="2" style="color:#7c3aed;letter-spacing:.3px">Item Group Summary</th>
        <th class="r">Total Qty</th><th class="r">Total Amount</th>
      </tr></thead><tbody>"""
    for key, v in sorted(ig.items()):
        html += f"""<tr>
          <td colspan="2">{_esc(key)}</td>
          <td class="r">{_qty(v["qty"])}</td>
          <td class="r">{_fmt(v["amount"])}</td>
        </tr>"""
    html += "</tbody></table>"
    return html


def _signoff_section(gathered, collected, legacy, label):
    """Bottom card: week closure status — clean or action required."""
    g_count   = len({r.name for r in gathered})
    g_total   = sum(flt(r.grand_total) for r in {r.name: r for r in gathered}.values())
    c_total   = sum(flt(r.grand_total) for r in {r.name: r for r in collected}.values())
    leg_total = sum(flt(r.collected_amount) for r in legacy)

    has_problem = g_count > 0
    dot_color   = "#dc2626" if has_problem else "#059669"

    if has_problem:
        status_badge = '<span class="badge-unpaid">Action Required</span>'
        note = (
            f"{g_count} invoice{'s' if g_count != 1 else ''} created this week "
            f"remain unpaid — <strong>{_fmt(g_total)}</strong> outstanding. "
            "Please review and reconcile before closing the week."
        )
    else:
        status_badge = '<span class="badge-paid">Clean Week</span>'
        note = "All invoices created this week have been collected. Week is clear for closure."

    return f"""  <div class="card">
    <div class="card-hdr">
      <div class="card-dot" style="background:{dot_color}"></div>
      <div class="card-title">Week Sign-Off &mdash; {label}</div>
      <div class="card-count">{status_badge}</div>
    </div>
    <div style="padding:18px 20px 20px">
      <p style="font-size:13px;color:#374151;margin-bottom:14px">{note}</p>
      <table style="font-size:12px;border-collapse:collapse;width:auto">
        <tr>
          <td style="padding:3px 20px 3px 0;color:#64748b;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.4px">Collected This Week</td>
          <td style="font-weight:800;color:#059669;font-size:14px">{_fmt(c_total)}</td>
          <td style="padding:3px 20px 3px 24px;color:#64748b;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.4px">Legacy Collected</td>
          <td style="font-weight:800;color:#7c3aed;font-size:14px">{_fmt(leg_total)}</td>
        </tr>
        <tr>
          <td style="padding:3px 20px 3px 0;color:#64748b;font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.4px">Outstanding AR</td>
          <td style="font-weight:800;color:#dc2626;font-size:14px">{_fmt(g_total)}</td>
          <td colspan="2"></td>
        </tr>
      </table>
      <p style="margin-top:14px;font-size:11px;color:#94a3b8">
        Sign-off notification sent to Muhammad &amp; bot &mdash; CC: Matt, Imran
      </p>
    </div>
  </div>"""


def _send_week_closure_email(week_start, week_end):
    """
    Separate closure/adjustment email to Muhammad and bot, CC Matt and Imran.
    Clean week → subject 'Week Closed'.
    Outstanding AR → subject 'Adjustments Required'.
    """
    try:
        label     = _week_label(week_start, week_end)
        gathered  = _get_ar_gathered(week_start, week_end)
        collected = _get_ar_collected(week_start, week_end)
        legacy    = _get_ar_legacy_collected(week_start, week_end)

        g_count   = len({r.name for r in gathered})
        g_total   = sum(flt(r.grand_total) for r in {r.name: r for r in gathered}.values())
        c_total   = sum(flt(r.grand_total) for r in {r.name: r for r in collected}.values())
        leg_total = sum(flt(r.collected_amount) for r in legacy)
        has_problem = g_count > 0

        if has_problem:
            subject      = f"Weekly Adjustments Required — {label}"
            status_color = "#dc2626"
            status_text  = "Action Required"
            status_bg    = "#fee2e2"
            body_note    = (
                f"<p style='color:#dc2626;font-weight:700;margin-bottom:10px'>"
                f"{g_count} invoice{'s' if g_count != 1 else ''} created this week "
                f"remain unpaid — {_fmt(g_total)} outstanding.</p>"
                "<p style='color:#374151'>Please review and reconcile before closing the week.</p>"
            )
        else:
            subject      = f"Week Closed — {label}"
            status_color = "#059669"
            status_text  = "Clean Week"
            status_bg    = "#d1fae5"
            body_note    = (
                "<p style='color:#059669;font-weight:700;margin-bottom:10px'>"
                "All invoices from this week have been collected. No outstanding AR.</p>"
                "<p style='color:#374151'>Week is clear for closure.</p>"
            )

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
          background:#f1f5f9; color:#0f172a; }}
  .wrap  {{ max-width:580px; margin:20px auto; background:#fff;
            border-radius:14px; overflow:hidden;
            box-shadow:0 2px 10px rgba(0,0,0,.08); }}
  .hdr   {{ background:linear-gradient(150deg,#0f172a 0%,#1e3a5f 100%);
            padding:28px 32px; text-align:center; }}
  .hdr-t {{ font-size:20px; font-weight:800; color:#fff; margin-bottom:6px; }}
  .hdr-d {{ color:rgba(255,255,255,.7); font-size:13px; }}
  .body  {{ padding:28px 32px; }}
  .badge {{ display:inline-block; padding:6px 18px; border-radius:20px;
            font-weight:700; font-size:13px; margin-bottom:18px;
            background:{status_bg}; color:{status_color}; }}
  .stats {{ display:flex; gap:14px; margin-top:18px; flex-wrap:wrap; }}
  .stat  {{ flex:1; min-width:140px; padding:14px 18px; background:#f8fafc;
            border-radius:10px; border:1px solid #e2e8f0; }}
  .stat-lbl {{ font-size:10px; font-weight:700; text-transform:uppercase;
               letter-spacing:.5px; color:#64748b; margin-bottom:6px; }}
  .stat-val {{ font-size:18px; font-weight:800; }}
  .footer {{ padding:14px 32px; background:#f8fafc;
             border-top:1px solid #e2e8f0;
             font-size:11px; color:#94a3b8; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-t">Weekly Sign-Off</div>
    <div class="hdr-d">{label}</div>
  </div>
  <div class="body">
    <div class="badge">{status_text}</div>
    {body_note}
    <div class="stats">
      <div class="stat">
        <div class="stat-lbl">Collected This Week</div>
        <div class="stat-val" style="color:#059669">{_fmt(c_total)}</div>
      </div>
      <div class="stat">
        <div class="stat-lbl">Legacy Collected</div>
        <div class="stat-val" style="color:#7c3aed">{_fmt(leg_total)}</div>
      </div>
      <div class="stat">
        <div class="stat-lbl">Outstanding AR</div>
        <div class="stat-val" style="color:#dc2626">{_fmt(g_total)}</div>
      </div>
    </div>
  </div>
  <div class="footer">
    Auto-generated by ERPNext &nbsp;&middot;&nbsp; Do not reply to this message.
  </div>
</div>
</body>
</html>"""

        frappe.sendmail(
            recipients=SIGNOFF_TO,
            cc=SIGNOFF_CC,
            subject=subject,
            message=html,
            delayed=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[weekly_report] sign-off email failed")


def _card(dot_color, title, count, total, body_html):
    return f"""  <div class="card">
    <div class="card-hdr">
      <div class="card-dot" style="background:{dot_color}"></div>
      <div class="card-title">{title}</div>
      <div class="card-count">{count}</div>
      <div class="card-total">{total}</div>
    </div>
    {body_html}
  </div>"""


# ── Utilities ─────────────────────────────────────────────────────────────────

def _fmt(v):
    if not v:
        return "$ 0.00"
    return "$ " + "{:,.2f}".format(flt(v))


def _qty(v):
    if not v:
        return "—"
    v = flt(v)
    return "{:,.2f}".format(v) if v != int(v) else "{:,}".format(int(v))


def _esc(s):
    if not s:
        return ""
    return (str(s)
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _mode_type(mode):
    if not mode:
        return "other"
    m = (mode or "").lower()
    if any(k in m for k in ("bank", "wire", "transfer", "ach", "check", "cheque", "zelle", "venmo")):
        return "bank"
    if "cash" in m:
        return "cash"
    return "other"
