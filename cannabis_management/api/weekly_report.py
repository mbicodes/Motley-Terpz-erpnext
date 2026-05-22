"""
Weekly Sale Report
Scheduled: Monday 8 AM UTC — covers the previous Mon–Sun week.

Email body: summary KPIs + sign-off only.
PDF attachment: full detail — Sales Orders, Sales Invoices, Delivery Notes,
                AR Gathered, AR Collected, Legacy Collected.
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
    ref = getdate(anchor) if anchor else getdate(nowdate())
    monday = ref - timedelta(days=ref.weekday())
    friday = monday + timedelta(days=4)
    return str(monday), str(friday)


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
        _do_send(week_start, week_end, RECIPIENTS)
        _send_week_closure_email(week_start, week_end)
        frappe.cache().set_value(cache_key, True, expires_in_sec=8 * 24 * 3600)
        frappe.logger().info(f"[weekly_report] sent for {week_start}–{week_end}")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[weekly_report] send failed")


# ── Manual triggers ───────────────────────────────────────────────────────────

@frappe.whitelist()
def send_now_2(week_start=None, week_end=None):
    if not week_start:
        week_start, week_end = _week_range()
    if not week_end:
        week_end = str(getdate(week_start) + timedelta(days=4))
    _do_send(week_start, week_end, ["mbi@alltechvirtual.com", "osama.ahmad@alltechvirtual.com"])
    return "sent"


@frappe.whitelist()
def send_now(week_start=None, week_end=None):
    if not week_start:
        week_start, week_end = _week_range()
    if not week_end:
        week_end = str(getdate(week_start) + timedelta(days=4))
    _do_send(week_start, week_end, RECIPIENTS)
    _send_week_closure_email(week_start, week_end)
    return "sent"


def _do_send(week_start, week_end, recipients):
    data      = _fetch_all_data(week_start, week_end)
    label     = _week_label(week_start, week_end)
    body      = _build_email_body(data, label)
    pdf_bytes = _make_pdf(_build_pdf_html(data, label))

    attachments = []
    if pdf_bytes:
        attachments = [{"fname": f"Weekly_Report_{week_start}.pdf", "fcontent": pdf_bytes}]

    frappe.sendmail(
        recipients=recipients,
        subject=f"Weekly Sale Report — {label}",
        message=body,
        attachments=attachments,
        delayed=False,
    )


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_all_data(week_start, week_end):
    return {
        "so_rows":   _get_weekly_sales_orders(week_start, week_end),
        "si_rows":   _get_weekly_sales_invoices(week_start, week_end),
        "dn_rows":   _get_weekly_delivery_notes(week_start, week_end),
        "gathered":  _get_ar_gathered(week_start, week_end),
        "collected": _get_ar_collected(week_start, week_end),
        "legacy":    _get_ar_legacy_collected(week_start, week_end),
    }


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
        LEFT JOIN `tabCustomer` c ON c.name = so.customer
        WHERE so.transaction_date BETWEEN %s AND %s
          AND so.docstatus = 1
          AND (c.is_internal_customer = 0 OR c.is_internal_customer IS NULL)
        GROUP BY so.name, soi.item_group
        ORDER BY so.customer, soi.item_group
    """, (week_start, week_end), as_dict=True)


def _get_weekly_sales_invoices(week_start, week_end):
    return frappe.db.sql("""
        SELECT
            si.name, si.customer, si.grand_total,
            si.outstanding_amount, si.posting_date, si.company,
            sii.item_group,
            SUM(sii.qty)    AS qty,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.posting_date BETWEEN %s AND %s
          AND si.docstatus = 1
          AND (c.is_internal_customer = 0 OR c.is_internal_customer IS NULL)
        GROUP BY si.name, sii.item_group
        ORDER BY si.customer, sii.item_group
    """, (week_start, week_end), as_dict=True)


def _get_weekly_delivery_notes(week_start, week_end):
    return frappe.db.sql("""
        SELECT
            dn.name, dn.customer, dn.grand_total,
            dn.posting_date, dn.company,
            dni.item_group,
            SUM(dni.qty)    AS qty,
            SUM(dni.amount) AS amount
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        LEFT JOIN `tabCustomer` c ON c.name = dn.customer
        WHERE dn.posting_date BETWEEN %s AND %s
          AND dn.docstatus = 1
          AND (c.is_internal_customer = 0 OR c.is_internal_customer IS NULL)
        GROUP BY dn.name, dni.item_group
        ORDER BY dn.customer, dni.item_group
    """, (week_start, week_end), as_dict=True)


def _get_ar_gathered(week_start, week_end):
    return frappe.db.sql("""
        SELECT
            si.name, si.customer, si.grand_total,
            si.outstanding_amount, si.posting_date, si.company,
            sii.item_group,
            SUM(sii.qty)    AS qty,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.posting_date BETWEEN %s AND %s
          AND si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND si.outstanding_amount >= (si.grand_total - 0.01)
          AND (c.is_internal_customer = 0 OR c.is_internal_customer IS NULL)
        GROUP BY si.name, sii.item_group
        ORDER BY si.customer, sii.item_group
    """, (week_start, week_end), as_dict=True)


def _get_ar_collected(week_start, week_end):
    return frappe.db.sql("""
        SELECT
            si.name, si.customer, si.grand_total,
            si.outstanding_amount, si.posting_date, si.company,
            sii.item_group,
            SUM(sii.qty)    AS qty,
            SUM(sii.amount) AS amount
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.posting_date BETWEEN %s AND %s
          AND si.docstatus = 1
          AND si.outstanding_amount <= 0.01
          AND (c.is_internal_customer = 0 OR c.is_internal_customer IS NULL)
        GROUP BY si.name, sii.item_group
        ORDER BY si.customer, sii.item_group
    """, (week_start, week_end), as_dict=True)


def _get_ar_legacy_collected(week_start, week_end):
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
        LEFT JOIN `tabCustomer` c ON c.name = pe.party
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.party_type = 'Customer'
          AND pe.posting_date BETWEEN %s AND %s
          AND si.posting_date < %s
          AND per.reference_doctype = 'Sales Invoice'
          AND (c.is_internal_customer = 0 OR c.is_internal_customer IS NULL)
        ORDER BY pe.party, pe.posting_date, si.posting_date
    """, (week_start, week_end, week_start), as_dict=True)


# ── Email body (summary only) ─────────────────────────────────────────────────

def _build_email_body(data, label):
    so_rows   = data["so_rows"]
    si_rows   = data["si_rows"]
    dn_rows   = data["dn_rows"]
    gathered  = data["gathered"]
    collected = data["collected"]
    legacy    = data["legacy"]

    so_count  = len({r.name for r in so_rows})
    so_total  = sum(flt(r.grand_total) for r in {r.name: r for r in so_rows}.values())
    si_count  = len({r.name for r in si_rows})
    si_total  = sum(flt(r.grand_total) for r in {r.name: r for r in si_rows}.values())
    dn_count  = len({r.name for r in dn_rows})
    dn_total  = sum(flt(r.grand_total) for r in {r.name: r for r in dn_rows}.values())
    g_count   = len({r.name for r in gathered})
    g_total   = sum(flt(r.grand_total) for r in {r.name: r for r in gathered}.values())
    c_count   = len({r.name for r in collected})
    c_total   = sum(flt(r.grand_total) for r in {r.name: r for r in collected}.values())
    leg_total = sum(flt(r.collected_amount) for r in legacy)
    leg_count = len({r.payment_name for r in legacy})

    has_problem = g_count > 0
    sf_color    = "#dc2626" if has_problem else "#059669"
    sf_bg       = "#fee2e2" if has_problem else "#d1fae5"
    sf_status   = "Action Required" if has_problem else "Clean Week"
    sf_note     = (
        f"{g_count} invoice{'s' if g_count != 1 else ''} unpaid — "
        f"<strong>{_fmt(g_total)}</strong> outstanding. Adjustments required."
        if has_problem else
        "All invoices from this week collected. Week is clear for closure."
    )

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#f1f5f9;color:#0f172a;}}
  .wrap{{max-width:660px;margin:0 auto;background:#f1f5f9;padding:20px 16px 40px;}}
  .hdr{{background:linear-gradient(150deg,#0f172a 0%,#1e3a5f 60%,#0f2942 100%);
       border-radius:16px;padding:36px 36px 30px;margin-bottom:14px;text-align:center;}}
  .hdr-ey{{font-size:10px;font-weight:700;text-transform:uppercase;
           letter-spacing:2.5px;color:rgba(255,255,255,.4);margin-bottom:12px;}}
  .hdr-tt{{font-size:28px;font-weight:800;color:#fff;letter-spacing:.2px;
           line-height:1.1;margin-bottom:14px;}}
  .hdr-tt span{{color:#38bdf8;}}
  .hdr-dt{{display:inline-block;background:rgba(255,255,255,.1);
           border:1px solid rgba(255,255,255,.15);border-radius:20px;
           padding:7px 20px;color:rgba(255,255,255,.85);font-size:13px;font-weight:600;}}
  .note{{background:#fff;border-radius:10px;border:1px solid #e2e8f0;
         padding:12px 20px;margin-bottom:14px;text-align:center;
         font-size:13px;color:#475569;line-height:1.6;}}
  .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;}}
  .kpi{{background:#fff;border-radius:12px;border:1px solid #e2e8f0;
        padding:16px 18px;box-shadow:0 1px 4px rgba(0,0,0,.07);}}
  .kpi-l{{font-size:10px;font-weight:700;text-transform:uppercase;
          letter-spacing:.6px;color:#64748b;margin-bottom:8px;}}
  .kpi-v{{font-size:20px;font-weight:800;line-height:1;}}
  .kpi-s{{font-size:11px;color:#94a3b8;margin-top:5px;}}
  .blue{{color:#2563eb;}} .indigo{{color:#4f46e5;}} .teal{{color:#0d9488;}}
  .red{{color:#dc2626;}}  .green{{color:#059669;}} .violet{{color:#7c3aed;}}
  .sf{{background:#fff;border-radius:12px;border:1px solid #e2e8f0;
       padding:18px 22px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.07);}}
  .sf-row{{display:flex;align-items:center;gap:10px;margin-bottom:12px;}}
  .sf-dot{{width:10px;height:10px;border-radius:50%;background:{sf_color};flex-shrink:0;}}
  .sf-tit{{font-size:12px;font-weight:700;text-transform:uppercase;
           letter-spacing:.4px;color:#0f172a;}}
  .sf-bdg{{margin-left:auto;display:inline-block;padding:3px 12px;
           border-radius:20px;font-size:11px;font-weight:700;
           background:{sf_bg};color:{sf_color};}}
  .sf-note{{font-size:13px;color:#374151;margin-bottom:14px;line-height:1.6;}}
  .sf-stats{{display:flex;gap:16px;flex-wrap:wrap;}}
  .sf-st{{flex:1;min-width:100px;}}
  .sf-sl{{font-size:10px;font-weight:700;text-transform:uppercase;
          letter-spacing:.4px;color:#64748b;margin-bottom:4px;}}
  .sf-sv{{font-size:16px;font-weight:800;}}
  .sf-foot{{margin-top:14px;font-size:11px;color:#94a3b8;}}
  .footer{{text-align:center;color:#94a3b8;font-size:11px;margin-top:8px;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-ey">Motley Terpz &amp; TSBC Ranch</div>
    <div class="hdr-tt">Weekly <span>Sale</span> Report</div>
    <div class="hdr-dt">{label}</div>
  </div>
  <div class="note">
    <strong>Full detail is in the attached PDF.</strong><br>
    Sales Orders &bull; Sales Invoices &bull; Delivery Notes &bull;
    AR Gathered &bull; AR Collected &bull; Legacy Collected
  </div>
  <div class="grid">
    <div class="kpi">
      <div class="kpi-l">Sales Orders</div>
      <div class="kpi-v blue">{so_count}</div>
      <div class="kpi-s">{_fmt(so_total)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">Sales Invoices</div>
      <div class="kpi-v indigo">{si_count}</div>
      <div class="kpi-s">{_fmt(si_total)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">Delivery Notes</div>
      <div class="kpi-v teal">{dn_count}</div>
      <div class="kpi-s">{_fmt(dn_total)}</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">AR Gathered</div>
      <div class="kpi-v red">{_fmt(g_total)}</div>
      <div class="kpi-s">{g_count} invoice{'s' if g_count != 1 else ''} unpaid</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">AR Collected</div>
      <div class="kpi-v green">{_fmt(c_total)}</div>
      <div class="kpi-s">{c_count} invoice{'s' if c_count != 1 else ''} paid</div>
    </div>
    <div class="kpi">
      <div class="kpi-l">Legacy Collected</div>
      <div class="kpi-v violet">{_fmt(leg_total)}</div>
      <div class="kpi-s">{leg_count} payment{'s' if leg_count != 1 else ''}</div>
    </div>
  </div>
  <div class="sf">
    <div class="sf-row">
      <div class="sf-dot"></div>
      <div class="sf-tit">Week Sign-Off &mdash; {label}</div>
      <div class="sf-bdg">{sf_status}</div>
    </div>
    <p class="sf-note">{sf_note}</p>
    <div class="sf-stats">
      <div class="sf-st">
        <div class="sf-sl">Collected This Week</div>
        <div class="sf-sv green">{_fmt(c_total)}</div>
      </div>
      <div class="sf-st">
        <div class="sf-sl">Legacy Collected</div>
        <div class="sf-sv violet">{_fmt(leg_total)}</div>
      </div>
      <div class="sf-st">
        <div class="sf-sl">Outstanding AR</div>
        <div class="sf-sv red">{_fmt(g_total)}</div>
      </div>
    </div>
    <p class="sf-foot">Sign-off notification sent to Muhammad &amp; bot — CC: Matt, Imran</p>
  </div>
  <div class="footer">
    Auto-generated by ERPNext &nbsp;·&nbsp; {datetime.now().strftime("%B %-d, %Y %H:%M")} UTC
    &nbsp;·&nbsp; Do not reply to this message.
  </div>
</div>
</body></html>"""


# ── PDF HTML (full detail) ────────────────────────────────────────────────────

_PDF_CSS = """
@page { size:A4; margin:12mm 14mm 14mm; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial,Helvetica,sans-serif; font-size:10px; color:#0f172a; background:#fff; }

.pdf-hdr { background:#0f172a; color:#fff; padding:16px 20px; border-radius:6px; margin-bottom:14px; }
.pdf-hdr-co { font-size:9px; color:rgba(255,255,255,.45); text-transform:uppercase;
              letter-spacing:2px; margin-bottom:3px; }
.pdf-hdr-title { font-size:18px; font-weight:700; }
.pdf-hdr-title span { color:#38bdf8; }
.pdf-hdr-date { font-size:11px; color:rgba(255,255,255,.65); margin-top:4px; }

.sec { margin-bottom:18px; page-break-inside:avoid; }
.sec-hdr { padding:6px 10px; margin-bottom:4px; border-radius:4px; }
.sec-title { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.3px; color:#fff; }
.sec-meta { font-size:9px; color:rgba(255,255,255,.7); margin-top:2px; }

table { width:100%; border-collapse:collapse; font-size:9px; }
th { padding:5px 7px; background:#f1f5f9; color:#475569; font-weight:700;
     font-size:8px; text-transform:uppercase; letter-spacing:.3px;
     text-align:left; border-bottom:2px solid #cbd5e1; white-space:nowrap; }
th.r { text-align:right; }
td { padding:4px 7px; border-bottom:1px solid #f1f5f9; vertical-align:top; }
td.r { text-align:right; font-variant-numeric:tabular-nums; }
td.m { color:#94a3b8; font-size:8px; }
td.b { font-weight:700; }
tr.sub td { background:#f8fafc; font-weight:700; border-top:2px solid #e2e8f0; font-size:9px; }
tr.igh td { background:#f1f5f9; font-weight:700; color:#374151; font-size:9px; padding:4px 7px; }

.ent { padding:1px 5px; border-radius:8px; font-size:7px; font-weight:700; text-transform:uppercase; }
.ent-mt { background:#ede9fe; color:#6d28d9; }
.ent-ts { background:#d1fae5; color:#065f46; }

.bu { padding:1px 5px; border-radius:3px; font-size:8px; font-weight:700;
      background:#fee2e2; color:#991b1b; }
.bp { padding:1px 5px; border-radius:3px; font-size:8px; font-weight:700;
      background:#d1fae5; color:#065f46; }

.mb { padding:1px 5px; border-radius:3px; font-size:8px; font-weight:700;
      background:#dbeafe; color:#1d4ed8; }
.mc { padding:1px 5px; border-radius:3px; font-size:8px; font-weight:700;
      background:#fef3c7; color:#92400e; }
.mo { padding:1px 5px; border-radius:3px; font-size:8px; font-weight:700;
      background:#f1f5f9; color:#475569; }

.empty { padding:10px; text-align:center; color:#94a3b8; font-style:italic; font-size:9px; }

.ig-tbl { margin-top:0; border-top:1px dashed #cbd5e1; }
.ig-tbl th { background:#fafbff; color:#7c3aed; }

.sf-box { border-radius:6px; padding:12px 16px; margin-top:14px; }
.sf-box.clean  { border:2px solid #059669; background:#f0fdf4; }
.sf-box.action { border:2px solid #dc2626; background:#fef2f2; }
.sf-title { font-size:11px; font-weight:700; margin-bottom:6px; }
.sf-note  { font-size:10px; color:#374151; margin-bottom:8px; }
.sf-row   { display:flex; gap:20px; flex-wrap:wrap; }
.sf-cell  { flex:1; min-width:100px; }
.sf-lbl   { font-size:8px; font-weight:700; text-transform:uppercase;
            letter-spacing:.3px; color:#64748b; margin-bottom:2px; }
.sf-val   { font-size:13px; font-weight:800; }

.pdf-footer { text-align:center; font-size:8px; color:#94a3b8;
              border-top:1px solid #e2e8f0; padding-top:6px; margin-top:12px; }
"""


def _build_pdf_html(data, label):
    so_rows   = data["so_rows"]
    si_rows   = data["si_rows"]
    dn_rows   = data["dn_rows"]
    gathered  = data["gathered"]
    collected = data["collected"]
    legacy    = data["legacy"]

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>{_PDF_CSS}</style>
</head><body>

<div class="pdf-hdr">
  <div class="pdf-hdr-co">Motley Terpz &amp; TSBC Ranch</div>
  <div class="pdf-hdr-title">Weekly <span>Sale</span> Report</div>
  <div class="pdf-hdr-date">{label} &nbsp;&middot;&nbsp; Generated {datetime.now().strftime("%B %-d, %Y")}</div>
</div>

{_pdf_so_section(so_rows)}
{_pdf_si_section(si_rows)}
{_pdf_dn_section(dn_rows)}
{_pdf_gathered_section(gathered)}
{_pdf_collected_section(collected)}
{_pdf_legacy_section(legacy)}
{_pdf_signoff(gathered, collected, legacy, label)}

<div style="margin-top:14px;padding:12px 16px;border:1px solid #e2e8f0;border-radius:6px;
            background:#f8fafc;font-size:10px;color:#374151;line-height:1.7">
  <p>Please reply this email to muhammad@motleyterpz.com and bot@motleyterpz.com
  and cc Matt and Imran to sign off the week for closure.</p>
  <p style="margin-top:8px">If there is a problem, reply to muhammad@motleyterpz.com
  and bot@motleyterpz.com and let them know about the adjustments.</p>
</div>

<div class="pdf-footer">
  Auto-generated by ERPNext &nbsp;&middot;&nbsp; {datetime.now().strftime("%B %-d, %Y %H:%M")} UTC
</div>
</body></html>"""


# ── PDF section builders ──────────────────────────────────────────────────────

def _pdf_section_wrap(bg_color, title, meta, table_html, ig_html=""):
    return f"""<div class="sec">
  <div class="sec-hdr" style="background:{bg_color}">
    <div class="sec-title">{title}</div>
    <div class="sec-meta">{meta}</div>
  </div>
  {table_html}
  {ig_html}
</div>"""


def _pdf_so_section(rows):
    count    = len({r.name for r in rows})
    total    = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    site_url = frappe.utils.get_url()
    tbl      = _pdf_doc_table(rows, date_field=None, doc_slug="sales-order", site_url=site_url)
    ig       = _pdf_ig_summary(rows)
    return _pdf_section_wrap(
        "#2563eb", "Sales Orders — This Week",
        f"{count} order{'s' if count != 1 else ''} &nbsp;&middot;&nbsp; {_fmt(total)}",
        tbl, ig
    )


def _pdf_si_section(rows):
    count    = len({r.name for r in rows})
    total    = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    site_url = frappe.utils.get_url()
    tbl      = _pdf_invoice_table(rows, mode="all", doc_slug="sales-invoice", site_url=site_url)
    ig       = _pdf_ig_summary(rows)
    return _pdf_section_wrap(
        "#4f46e5", "Sales Invoices — This Week",
        f"{count} invoice{'s' if count != 1 else ''} &nbsp;&middot;&nbsp; {_fmt(total)}",
        tbl, ig
    )


def _pdf_dn_section(rows):
    count    = len({r.name for r in rows})
    total    = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    site_url = frappe.utils.get_url()
    tbl      = _pdf_doc_table(rows, date_field="posting_date", doc_slug="delivery-note", site_url=site_url)
    ig       = _pdf_ig_summary(rows)
    return _pdf_section_wrap(
        "#0d9488", "Delivery Notes — This Week",
        f"{count} delivery note{'s' if count != 1 else ''} &nbsp;&middot;&nbsp; {_fmt(total)}",
        tbl, ig
    )


def _pdf_gathered_section(rows):
    count    = len({r.name for r in rows})
    total    = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    site_url = frappe.utils.get_url()
    if not rows:
        tbl = '<div class="empty">No unpaid invoices created this week.</div>'
        ig  = ""
    else:
        tbl = _pdf_invoice_table(rows, mode="unpaid", doc_slug="sales-invoice", site_url=site_url)
        ig  = _pdf_ig_summary(rows)
    return _pdf_section_wrap(
        "#dc2626", "AR Gathered — Invoices Created, Not Yet Paid",
        f"{count} invoice{'s' if count != 1 else ''} unpaid &nbsp;&middot;&nbsp; {_fmt(total)}",
        tbl, ig
    )


def _pdf_collected_section(rows):
    count    = len({r.name for r in rows})
    total    = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    site_url = frappe.utils.get_url()
    if not rows:
        tbl = '<div class="empty">No invoices from this week fully collected.</div>'
        ig  = ""
    else:
        tbl = _pdf_invoice_table(rows, mode="paid", doc_slug="sales-invoice", site_url=site_url)
        ig  = _pdf_ig_summary(rows)
    return _pdf_section_wrap(
        "#059669", "AR Collected — Invoices Created &amp; Paid This Week",
        f"{count} invoice{'s' if count != 1 else ''} &nbsp;&middot;&nbsp; {_fmt(total)}",
        tbl, ig
    )


def _pdf_legacy_section(rows):
    total     = sum(flt(r.collected_amount) for r in rows)
    pay_count = len({r.payment_name for r in rows})
    site_url  = frappe.utils.get_url()
    if not rows:
        tbl = '<div class="empty">No legacy invoice payments received this week.</div>'
    else:
        tbl = _pdf_legacy_table(rows, site_url=site_url)
    return _pdf_section_wrap(
        "#7c3aed", "AR Legacy Collected — Old Invoices Paid This Week",
        f"{pay_count} payment{'s' if pay_count != 1 else ''} &nbsp;&middot;&nbsp; {_fmt(total)}",
        tbl
    )


def _pdf_signoff(gathered, collected, legacy, label):
    g_count   = len({r.name for r in gathered})
    g_total   = sum(flt(r.grand_total) for r in {r.name: r for r in gathered}.values())
    c_total   = sum(flt(r.grand_total) for r in {r.name: r for r in collected}.values())
    leg_total = sum(flt(r.collected_amount) for r in legacy)
    has_problem = g_count > 0

    cls    = "action" if has_problem else "clean"
    status = "Action Required" if has_problem else "Clean Week"
    color  = "#dc2626" if has_problem else "#059669"
    note   = (
        f"{g_count} invoice{'s' if g_count != 1 else ''} unpaid — {_fmt(g_total)} outstanding."
        if has_problem else
        "All invoices from this week have been collected. Week is clear for closure."
    )
    return f"""<div class="sf-box {cls}">
  <div class="sf-title" style="color:{color}">Week Sign-Off — {label} &nbsp; [{status}]</div>
  <div class="sf-note">{note}</div>
  <div class="sf-row">
    <div class="sf-cell">
      <div class="sf-lbl">Collected This Week</div>
      <div class="sf-val" style="color:#059669">{_fmt(c_total)}</div>
    </div>
    <div class="sf-cell">
      <div class="sf-lbl">Legacy Collected</div>
      <div class="sf-val" style="color:#7c3aed">{_fmt(leg_total)}</div>
    </div>
    <div class="sf-cell">
      <div class="sf-lbl">Outstanding AR</div>
      <div class="sf-val" style="color:#dc2626">{_fmt(g_total)}</div>
    </div>
  </div>
</div>"""


# ── PDF table builders ────────────────────────────────────────────────────────

def _pdf_doc_table(rows, date_field=None, doc_slug="", site_url=""):
    """Generic table for Sales Orders and Delivery Notes."""
    if not rows:
        return '<div class="empty">No records this week.</div>'

    docs = {}
    for r in rows:
        if r.name not in docs:
            docs[r.name] = {
                "name": r.name, "customer": r.customer,
                "grand_total": r.grand_total, "company": r.company,
                "date": str(getattr(r, date_field, "") or "")[:10] if date_field else "",
                "items": [],
            }
        docs[r.name]["items"].append(r)

    date_col = "<th>Date</th>" if date_field else ""
    html = f"""<table><thead><tr>
      <th>ID</th><th>Client</th><th>Entity</th>{date_col}
      <th>Item Group</th><th class="r">Qty</th>
      <th class="r">Line Amt</th><th class="r">Total</th>
    </tr></thead><tbody>"""

    for doc in docs.values():
        ent_cls  = "ent-mt" if doc["company"] == "Motley Terpz" else "ent-ts"
        ent_lbl  = "Motley"  if doc["company"] == "Motley Terpz" else "TSBC"
        doc_link = (
            f'<a href="{site_url}/app/{doc_slug}/{doc["name"]}" '
            f'style="color:#2563eb;text-decoration:none;font-size:8px">{_esc(doc["name"])}</a>'
            if site_url and doc_slug else _esc(doc["name"])
        )
        items = doc["items"]
        for j, item in enumerate(items):
            first   = j == 0
            last    = j == len(items) - 1
            date_td = f"<td class='m'>{doc['date'] if first else ''}</td>" if date_field else ""
            html += f"""<tr>
              <td class="m">{doc_link if first else ''}</td>
              <td class="b">{_esc(doc['customer']) if first else ''}</td>
              <td>{"<span class='ent " + ent_cls + "'>" + ent_lbl + "</span>" if first else ''}</td>
              {date_td}
              <td>{_esc(item.item_group or '—')}</td>
              <td class="r">{_qty(item.qty)}</td>
              <td class="r">{_fmt(item.amount)}</td>
              <td class="r b">{"" if not last else _fmt(doc['grand_total'])}</td>
            </tr>"""

    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    count = len(docs)
    span  = 7 if date_field else 6
    html += f"""<tr class="sub">
      <td colspan="{span}">Total — {count} record{"s" if count != 1 else ""}</td>
      <td class="r">{_fmt(total)}</td>
    </tr></tbody></table>"""
    return html


def _pdf_invoice_table(rows, mode="all", doc_slug="sales-invoice", site_url=""):
    """Table for Sales Invoices / AR Gathered / AR Collected."""
    if not rows:
        return '<div class="empty">No records this week.</div>'

    docs = {}
    for r in rows:
        if r.name not in docs:
            docs[r.name] = {
                "name": r.name, "customer": r.customer,
                "grand_total": r.grand_total,
                "outstanding_amount": r.outstanding_amount,
                "posting_date": str(r.posting_date)[:10],
                "company": r.company, "items": [],
            }
        docs[r.name]["items"].append(r)

    html = """<table><thead><tr>
      <th>ID</th><th>Client</th><th>Entity</th><th>Date</th>
      <th>Item Group</th><th class="r">Qty</th>
      <th class="r">Line Amt</th><th class="r">Total</th><th>Status</th>
    </tr></thead><tbody>"""

    for doc in docs.values():
        ent_cls     = "ent-mt" if doc["company"] == "Motley Terpz" else "ent-ts"
        ent_lbl     = "Motley"  if doc["company"] == "Motley Terpz" else "TSBC"
        outstanding = flt(doc["outstanding_amount"])
        doc_link    = (
            f'<a href="{site_url}/app/{doc_slug}/{doc["name"]}" '
            f'style="color:#2563eb;text-decoration:none;font-size:8px">{_esc(doc["name"])}</a>'
            if site_url and doc_slug else _esc(doc["name"])
        )
        if mode == "unpaid":
            status_html = f'<span class="bu">Unpaid {_fmt(outstanding)}</span>'
        elif mode == "paid":
            status_html = '<span class="bp">Collected</span>'
        else:
            status_html = (
                f'<span class="bu">Unpaid {_fmt(outstanding)}</span>'
                if outstanding > 0.01 else
                '<span class="bp">Paid</span>'
            )
        items = doc["items"]
        for j, item in enumerate(items):
            first = j == 0
            last  = j == len(items) - 1
            html += f"""<tr>
              <td class="m">{doc_link if first else ''}</td>
              <td class="b">{_esc(doc['customer']) if first else ''}</td>
              <td>{"<span class='ent " + ent_cls + "'>" + ent_lbl + "</span>" if first else ''}</td>
              <td class="m">{doc['posting_date'] if first else ''}</td>
              <td>{_esc(item.item_group or '—')}</td>
              <td class="r">{_qty(item.qty)}</td>
              <td class="r">{_fmt(item.amount)}</td>
              <td class="r b">{"" if not last else _fmt(doc['grand_total'])}</td>
              <td>{status_html if last else ''}</td>
            </tr>"""

    total = sum(flt(r.grand_total) for r in {r.name: r for r in rows}.values())
    count = len(docs)
    html += f"""<tr class="sub">
      <td colspan="7">Total — {count} invoice{"s" if count != 1 else ""}</td>
      <td class="r">{_fmt(total)}</td><td></td>
    </tr></tbody></table>"""
    return html


def _pdf_legacy_table(rows, site_url=""):
    html = """<table><thead><tr>
      <th>Client</th><th>Entity</th><th>Pay Date</th><th>Mode</th>
      <th>Invoice</th><th class="r">Inv Date</th>
      <th class="r">Inv Total</th><th class="r">Collected</th>
    </tr></thead><tbody>"""

    payments = {}
    for r in rows:
        if r.payment_name not in payments:
            payments[r.payment_name] = []
        payments[r.payment_name].append(r)

    for pay_rows in payments.values():
        for j, r in enumerate(pay_rows):
            first   = j == 0
            ent_cls = "ent-mt" if r.company == "Motley Terpz" else "ent-ts"
            ent_lbl = "Motley"  if r.company == "Motley Terpz" else "TSBC"
            mt      = _mode_type(r.mode_of_payment)
            mcls    = f"m{'b' if mt == 'bank' else 'c' if mt == 'cash' else 'o'}"
            inv_link = (
                f'<a href="{site_url}/app/sales-invoice/{r.invoice}" '
                f'style="color:#2563eb;text-decoration:none;font-size:8px">{_esc(r.invoice)}</a>'
                if site_url else _esc(r.invoice)
            )
            html += f"""<tr>
              <td class="b">{_esc(r.customer) if first else ''}</td>
              <td>{"<span class='ent " + ent_cls + "'>" + ent_lbl + "</span>" if first else ''}</td>
              <td class="m">{str(r.payment_date)[:10] if first else ''}</td>
              <td>{"<span class='" + mcls + "'>" + _esc(r.mode_of_payment) + "</span>" if first else ''}</td>
              <td class="m">{inv_link}</td>
              <td class="r m">{str(r.invoice_date)[:10]}</td>
              <td class="r">{_fmt(r.invoice_total)}</td>
              <td class="r b">{_fmt(r.collected_amount)}</td>
            </tr>"""

    leg_total = sum(flt(r.collected_amount) for r in rows)
    html += f"""<tr class="sub">
      <td colspan="7">Total Collected</td>
      <td class="r">{_fmt(leg_total)}</td>
    </tr></tbody></table>"""
    return html


def _pdf_ig_summary(rows):
    if not rows:
        return ""
    ig = {}
    for r in rows:
        key = r.item_group or "Other"
        if key not in ig:
            ig[key] = {"qty": 0.0, "amount": 0.0}
        ig[key]["qty"]    += flt(r.qty)
        ig[key]["amount"] += flt(r.amount)

    html = """<table class="ig-tbl"><thead><tr>
      <th colspan="2">Item Group Summary</th>
      <th class="r">Total Qty</th><th class="r">Total Amount</th>
    </tr></thead><tbody>"""
    for key, v in sorted(ig.items()):
        html += f"""<tr>
          <td colspan="2">{_esc(key)}</td>
          <td class="r">{_qty(v['qty'])}</td>
          <td class="r">{_fmt(v['amount'])}</td>
        </tr>"""
    html += "</tbody></table>"
    return html


# ── PDF generation ────────────────────────────────────────────────────────────

def _make_pdf(html):
    try:
        from frappe.utils.pdf import get_pdf
        return get_pdf(html)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[weekly_report] PDF generation failed")
        return None


# ── Week closure sign-off email ───────────────────────────────────────────────

def _send_week_closure_email(week_start, week_end):
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
<html><head><meta charset="UTF-8">
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
       background:#f1f5f9;color:#0f172a;}}
  .wrap{{max-width:560px;margin:20px auto;background:#fff;border-radius:14px;
         overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.08);}}
  .hdr{{background:linear-gradient(150deg,#0f172a 0%,#1e3a5f 100%);
        padding:26px 30px;text-align:center;}}
  .hdr-t{{font-size:18px;font-weight:800;color:#fff;margin-bottom:5px;}}
  .hdr-d{{color:rgba(255,255,255,.65);font-size:13px;}}
  .body{{padding:26px 30px;}}
  .badge{{display:inline-block;padding:5px 16px;border-radius:20px;
          font-weight:700;font-size:13px;margin-bottom:16px;
          background:{status_bg};color:{status_color};}}
  .stats{{display:flex;gap:12px;margin-top:16px;flex-wrap:wrap;}}
  .stat{{flex:1;min-width:130px;padding:12px 16px;background:#f8fafc;
         border-radius:10px;border:1px solid #e2e8f0;}}
  .stat-l{{font-size:10px;font-weight:700;text-transform:uppercase;
           letter-spacing:.5px;color:#64748b;margin-bottom:5px;}}
  .stat-v{{font-size:17px;font-weight:800;}}
  .footer{{padding:12px 30px;background:#f8fafc;border-top:1px solid #e2e8f0;
           font-size:11px;color:#94a3b8;text-align:center;}}
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
        <div class="stat-l">Collected This Week</div>
        <div class="stat-v" style="color:#059669">{_fmt(c_total)}</div>
      </div>
      <div class="stat">
        <div class="stat-l">Legacy Collected</div>
        <div class="stat-v" style="color:#7c3aed">{_fmt(leg_total)}</div>
      </div>
      <div class="stat">
        <div class="stat-l">Outstanding AR</div>
        <div class="stat-v" style="color:#dc2626">{_fmt(g_total)}</div>
      </div>
    </div>
  </div>
  <div class="footer">Auto-generated by ERPNext &nbsp;&middot;&nbsp; Do not reply.</div>
</div>
</body></html>"""

        frappe.sendmail(
            recipients=SIGNOFF_TO,
            cc=SIGNOFF_CC,
            subject=subject,
            message=html,
            delayed=False,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "[weekly_report] sign-off email failed")


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
