"""
Daily Sale Report
Scheduled: Mon–Fri at 4 PM Pacific (23:00 UTC / 3 PM PST Nov–Mar)
Covers: Sales Orders, Sales Invoices, Delivery Notes, Client Payments, Tomorrow's Orders
"""

import frappe
from frappe.utils import nowdate, add_days, fmt_money, flt, format_datetime
from datetime import datetime

CEO_RECIPIENTS = [
    "jamie@motleyterpz.com",       # Jamie Hawk
    "matt@motleyterpz.com",        # Matt Schneider
    "imran@motleyterpz.com",       # Imran
    "mbi@alltechvirtual.com",      # Muhammad (MBI)
    "nikki@motleyterpz.com",       # Nikki M
    "osama.ahmad@alltechvirtual.com",  # Osama (test)
]

COMPANIES = ["Motley Terpz", "TSBC Ranch"]


# ── Entry point (scheduler) ───────────────────────────────────────────────────

def send_daily_report():
    today = nowdate()
    tomorrow = add_days(today, 1)
    try:
        html = _build_email(today, tomorrow)
        date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
        frappe.sendmail(
            recipients=CEO_RECIPIENTS,
            subject=f"Daily Sale Report — {date_label}",
            message=html,
            delayed=False,
        )
        frappe.logger().info(f"[daily_report] sent for {today}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[daily_report] send failed")


# ── Allow manual trigger from desk ───────────────────────────────────────────

@frappe.whitelist()
def send_now(date=None):
    today = date or nowdate()
    tomorrow = add_days(today, 1)
    html = _build_email(today, tomorrow)
    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    frappe.sendmail(
        recipients=CEO_RECIPIENTS,
        subject=f"Daily Sale Report — {date_label}",
        message=html,
        delayed=False,
    )
    return "sent"


# ── Data queries ──────────────────────────────────────────────────────────────

def _get_sales_orders(date):
    rows = frappe.db.sql("""
        SELECT
            so.name,
            so.customer,
            so.grand_total,
            so.company,
            soi.item_group,
            SUM(soi.qty)    AS qty,
            SUM(soi.amount) AS amount
        FROM `tabSales Order` so
        JOIN `tabSales Order Item` soi ON soi.parent = so.name
        WHERE DATE(so.transaction_date) = %s
          AND so.docstatus = 1
        GROUP BY so.name, soi.item_group
        ORDER BY so.customer, soi.item_group
    """, date, as_dict=True)
    return rows


def _get_sales_invoices(date):
    rows = frappe.db.sql("""
        SELECT
            si.name,
            si.customer,
            si.grand_total,
            si.company,
            sii.item_group,
            SUM(sii.qty)    AS qty,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE DATE(si.posting_date) = %s
          AND si.docstatus = 1
        GROUP BY si.name, sii.item_group
        ORDER BY si.customer, sii.item_group
    """, date, as_dict=True)
    return rows


def _get_delivery_notes(date):
    rows = frappe.db.sql("""
        SELECT
            dn.name,
            dn.customer,
            dn.grand_total,
            dn.company,
            dni.item_group,
            SUM(dni.qty)    AS qty,
            SUM(dni.amount) AS amount
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE DATE(dn.posting_date) = %s
          AND dn.docstatus = 1
        GROUP BY dn.name, dni.item_group
        ORDER BY dn.customer, dni.item_group
    """, date, as_dict=True)
    return rows


def _get_payments(date):
    rows = frappe.db.sql("""
        SELECT
            pe.name,
            pe.party       AS customer,
            pe.paid_amount AS amount,
            pe.mode_of_payment,
            pe.company,
            pe.remarks
        FROM `tabPayment Entry` pe
        WHERE DATE(pe.posting_date) = %s
          AND pe.docstatus = 1
          AND pe.payment_type = 'Receive'
        ORDER BY pe.mode_of_payment, pe.party
    """, date, as_dict=True)
    return rows


def _get_tomorrow_orders(tomorrow):
    rows = frappe.db.sql("""
        SELECT
            so.name,
            so.customer,
            so.grand_total,
            so.delivery_date,
            so.company,
            GROUP_CONCAT(DISTINCT soi.item_group ORDER BY soi.item_group SEPARATOR ', ') AS item_groups,
            SUM(soi.qty) AS total_qty
        FROM `tabSales Order` so
        JOIN `tabSales Order Item` soi ON soi.parent = so.name
        WHERE so.delivery_date = %s
          AND so.docstatus = 1
          AND so.status NOT IN ('Completed', 'Cancelled', 'Closed')
        GROUP BY so.name
        ORDER BY so.customer
    """, tomorrow, as_dict=True)
    return rows


# ── Email builder ─────────────────────────────────────────────────────────────

def _build_email(today, tomorrow):
    so_rows = _get_sales_orders(today)
    si_rows = _get_sales_invoices(today)
    dn_rows = _get_delivery_notes(today)
    py_rows = _get_payments(today)
    tm_rows = _get_tomorrow_orders(tomorrow)

    date_label = datetime.strptime(today, "%Y-%m-%d").strftime("%A, %B %-d, %Y")
    tom_label  = datetime.strptime(tomorrow, "%Y-%m-%d").strftime("%A, %B %-d, %Y")

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
  .kpi.accent-blue  .kpi-val {{ color:#2563eb; }}
  .kpi.accent-green .kpi-val {{ color:#059669; }}
  .kpi.accent-violet .kpi-val {{ color:#7c3aed; }}
  .kpi.accent-amber .kpi-val {{ color:#d97706; }}

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
  .mode-bank {{ background:#dbeafe; color:#1d4ed8; }}
  .mode-cash {{ background:#fef3c7; color:#92400e; }}
  .mode-other {{ background:#f1f5f9; color:#475569; }}

  /* ── Tomorrow ── */
  .tmr-hdr {{ background:linear-gradient(135deg,#1e40af,#3b82f6);
              border-radius:12px 12px 0 0; padding:14px 20px;
              display:flex; align-items:center; gap:10px; }}
  .tmr-hdr .card-title {{ color:#fff; }}
  .tmr-hdr .card-count {{ background:rgba(255,255,255,.2); border-color:transparent;
                          color:#fff; }}

  /* ── Empty state ── */
  .empty {{ padding:24px; text-align:center; color:#94a3b8;
            font-size:12px; font-style:italic; }}

  /* ── Footer ── */
  .footer {{ text-align:center; color:#94a3b8; font-size:11px;
             margin-top:8px; padding:0 16px; }}
  .footer a {{ color:#64748b; }}
</style>
</head>
<body>
<div class="wrap">

  <!-- Header -->
  <div class="hdr">
    <div class="hdr-eyebrow">Motley Terpz &amp; TSBC Ranch</div>
    <div class="hdr-title">Daily <span>Sale</span> Report</div>
    <div class="hdr-date">{date_label}</div>
  </div>

{_kpi_bar(so_rows, si_rows, dn_rows, py_rows)}
{_so_section(so_rows)}
{_si_section(si_rows)}
{_dn_section(dn_rows)}
{_payment_section(py_rows)}
{_tomorrow_section(tm_rows, tom_label)}

  <div class="footer">
    Auto-generated by ERPNext &nbsp;·&nbsp; {datetime.now().strftime("%B %-d, %Y %H:%M")} UTC &nbsp;·&nbsp;
    Do not reply to this message.
  </div>

</div>
</body>
</html>"""
    return html


# ── Section builders ──────────────────────────────────────────────────────────

def _kpi_bar(so_rows, si_rows, dn_rows, py_rows):
    so_orders  = len({r.name for r in so_rows})
    so_total   = sum(flt(r.grand_total) for r in {r.name: r for r in so_rows}.values())
    si_invs    = len({r.name for r in si_rows})
    si_total   = sum(flt(r.grand_total) for r in {r.name: r for r in si_rows}.values())
    dn_count   = len({r.name for r in dn_rows})
    dn_total   = sum(flt(r.grand_total) for r in {r.name: r for r in dn_rows}.values())
    py_total   = sum(flt(r.amount) for r in py_rows)
    py_count   = len(py_rows)
    py_suffix  = "s" if py_count != 1 else ""

    return f"""  <div class="kpi-bar">
    <div class="kpi accent-blue">
      <div class="kpi-lbl">Sales Orders</div>
      <div class="kpi-val">{so_orders}</div>
      <div class="kpi-sub">{_fmt(so_total)}</div>
    </div>
    <div class="kpi accent-violet">
      <div class="kpi-lbl">Sales Invoices</div>
      <div class="kpi-val">{si_invs}</div>
      <div class="kpi-sub">{_fmt(si_total)}</div>
    </div>
    <div class="kpi accent-green">
      <div class="kpi-lbl">Deliveries</div>
      <div class="kpi-val">{dn_count}</div>
      <div class="kpi-sub">{_fmt(dn_total)}</div>
    </div>
    <div class="kpi accent-amber">
      <div class="kpi-lbl">Payments In</div>
      <div class="kpi-val">{_fmt(py_total)}</div>
      <div class="kpi-sub">{py_count} transaction{py_suffix}</div>
    </div>
  </div>"""


def _doc_table(rows, doc_type_label):
    """Generic table builder for SO/SI/DN rows grouped by document."""
    if not rows:
        return f'<div class="empty">No {doc_type_label} recorded today.</div>'

    # Group by document name
    docs = {}
    for r in rows:
        if r.name not in docs:
            docs[r.name] = {"name": r.name, "customer": r.customer,
                            "grand_total": r.grand_total, "company": r.company,
                            "items": []}
        docs[r.name]["items"].append(r)

    html = """<table>
      <thead><tr>
        <th>Client</th>
        <th>Entity</th>
        <th>Item Group</th>
        <th class="r">Qty</th>
        <th class="r">Line Amt</th>
        <th class="r">Order Total</th>
      </tr></thead>
      <tbody>"""

    for i, (doc_name, doc) in enumerate(docs.items()):
        ent_cls = "ent-mt" if doc["company"] == "Motley Terpz" else "ent-ts"
        ent_lbl = "Motley" if doc["company"] == "Motley Terpz" else "TSBC"
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

    # Totals row
    total_amt   = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    total_docs  = len(docs)
    html += f"""<tr class="subtotal">
      <td colspan="5">Total — {total_docs} {doc_type_label}{"s" if total_docs != 1 else ""}</td>
      <td class="r">{_fmt(total_amt)}</td>
    </tr>"""

    html += "</tbody></table>"
    return html


def _ig_summary(rows):
    """Item group summary table."""
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
        <th class="r">Total Qty</th>
        <th class="r">Total Amount</th>
      </tr></thead><tbody>"""
    for key, v in sorted(ig.items()):
        html += f"""<tr>
          <td colspan="2">{_esc(key)}</td>
          <td class="r">{_qty(v["qty"])}</td>
          <td class="r">{_fmt(v["amount"])}</td>
        </tr>"""
    html += "</tbody></table>"
    return html


def _card(dot_color, title, count, total, body_html, summary_html=""):
    return f"""  <div class="card">
    <div class="card-hdr">
      <div class="card-dot" style="background:{dot_color}"></div>
      <div class="card-title">{title}</div>
      <div class="card-count">{count}</div>
      <div class="card-total">{total}</div>
    </div>
    {body_html}
    {summary_html}
  </div>"""


def _so_section(rows):
    count = len({r.name for r in rows})
    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    return _card("#2563eb", "Sales Orders — Today", f"{count} order{'s' if count!=1 else ''}",
                 _fmt(total), _doc_table(rows, "Sales Order"), _ig_summary(rows))


def _si_section(rows):
    count = len({r.name for r in rows})
    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    return _card("#7c3aed", "Sales Invoices — Today", f"{count} invoice{'s' if count!=1 else ''}",
                 _fmt(total), _doc_table(rows, "Sales Invoice"), _ig_summary(rows))


def _dn_section(rows):
    count = len({r.name for r in rows})
    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    return _card("#059669", "Delivery Notes — Today", f"{count} delivery{'s' if count!=1 else ''}",
                 _fmt(total), _doc_table(rows, "Delivery Note"), _ig_summary(rows))


def _payment_section(rows):
    if not rows:
        body = '<div class="empty">No client payments received today.</div>'
    else:
        bank_total = sum(flt(r.amount) for r in rows if _mode_type(r.mode_of_payment) == "bank")
        cash_total = sum(flt(r.amount) for r in rows if _mode_type(r.mode_of_payment) == "cash")
        other_total = sum(flt(r.amount) for r in rows if _mode_type(r.mode_of_payment) == "other")

        body = f"""<table>
      <thead><tr>
        <th>Client</th>
        <th>Mode</th>
        <th>Entity</th>
        <th class="r">Amount</th>
        <th>Remarks</th>
      </tr></thead>
      <tbody>"""
        for r in rows:
            mt   = _mode_type(r.mode_of_payment)
            mcls = f"mode-{mt}"
            ent_cls = "ent-mt" if r.company == "Motley Terpz" else "ent-ts"
            ent_lbl = "Motley" if r.company == "Motley Terpz" else "TSBC"
            body += f"""<tr>
          <td class="bold">{_esc(r.customer)}</td>
          <td><span class="mode {mcls}">{_esc(r.mode_of_payment)}</span></td>
          <td><span class="ent {ent_cls}">{ent_lbl}</span></td>
          <td class="r">{_fmt(r.amount)}</td>
          <td class="muted">{_esc(r.remarks or "")[:60]}</td>
        </tr>"""

        body += f"""<tr class="subtotal">
        <td colspan="3">Total</td>
        <td class="r">{_fmt(sum(flt(r.amount) for r in rows))}</td>
        <td></td>
      </tr></tbody></table>"""

        # Bank vs Cash breakdown
        body += f"""<table style="margin-top:0">
      <thead><tr style="background:#fafbff">
        <th colspan="3" style="color:#d97706">Breakdown by Mode</th>
        <th class="r">Total</th>
      </tr></thead>
      <tbody>
        <tr><td colspan="3"><span class="mode mode-bank">Bank / Wire</span></td>
            <td class="r bold">{_fmt(bank_total)}</td></tr>
        <tr><td colspan="3"><span class="mode mode-cash">Cash</span></td>
            <td class="r bold">{_fmt(cash_total)}</td></tr>
        {"<tr><td colspan='3'><span class='mode mode-other'>Other</span></td><td class='r bold'>" + _fmt(other_total) + "</td></tr>" if other_total else ""}
      </tbody></table>"""

    count = len(rows)
    total = sum(flt(r.amount) for r in rows)
    return _card("#d97706", "Payments Received — Today", f"{count} payment{'s' if count!=1 else ''}",
                 _fmt(total), body)


def _tomorrow_section(rows, tom_label):
    if not rows:
        body = '<div class="empty">No orders scheduled for delivery tomorrow.</div>'
    else:
        body = f"""<table>
      <thead><tr>
        <th>Client</th>
        <th>Entity</th>
        <th>Item Groups</th>
        <th class="r">Total Qty</th>
        <th class="r">Order Value</th>
        <th>SO #</th>
      </tr></thead>
      <tbody>"""
        total = 0
        for r in rows:
            ent_cls = "ent-mt" if r.company == "Motley Terpz" else "ent-ts"
            ent_lbl = "Motley" if r.company == "Motley Terpz" else "TSBC"
            total  += flt(r.grand_total)
            body += f"""<tr>
          <td class="bold">{_esc(r.customer)}</td>
          <td><span class="ent {ent_cls}">{ent_lbl}</span></td>
          <td class="muted">{_esc(r.item_groups or "—")}</td>
          <td class="r">{_qty(r.total_qty)}</td>
          <td class="r">{_fmt(r.grand_total)}</td>
          <td class="muted">{r.name}</td>
        </tr>"""
        body += f"""<tr class="subtotal">
        <td colspan="4">Total — {len(rows)} order{'s' if len(rows)!=1 else ''}</td>
        <td class="r">{_fmt(total)}</td>
        <td></td>
      </tr></tbody></table>"""

    count = len(rows)
    return f"""  <div class="card">
    <div class="tmr-hdr">
      <div class="card-dot" style="background:rgba(255,255,255,.6)"></div>
      <div class="card-title">Scheduled for Tomorrow — {tom_label}</div>
      <div class="card-count">{count} order{'s' if count!=1 else ''}</div>
    </div>
    {body}
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
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _mode_type(mode):
    if not mode:
        return "other"
    m = (mode or "").lower()
    if any(k in m for k in ("bank", "wire", "transfer", "ach", "check", "cheque", "zelle", "venmo")):
        return "bank"
    if "cash" in m:
        return "cash"
    return "other"
