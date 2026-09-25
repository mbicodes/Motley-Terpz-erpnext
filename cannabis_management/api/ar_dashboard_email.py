"""Daily AR Dashboard email: 1 PM California, to Nikki with Matt / Muhammad / Imran on CC.

Sends the two PDFs the dashboard's manual Email button sends - Legacy AR and
New AR, All Entities - in one email. The manual button is untouched.

The manual PDF is built in the browser (ar_dashboard.js: build_table_html, then
ard_build_report_table trims it to the mode's columns). A scheduled job has no
browser, so this module builds that same trimmed sheet server-side from the
same get_ar_data rows, with the page's own stylesheet and the same print /
report CSS, and renders it with the same _render_ar_pdf. If the sheet layout in
ar_dashboard.js changes, mirror it in _sheet_html below.
"""

import base64
import os
from datetime import date

import frappe
from frappe.utils import getdate, nowdate

from cannabis_management.cannabis_management.page.ar_dashboard import ar_dashboard as ard

TO = ["nikki@motleyterpz.com"]
CC = ["matt@motleyterpz.com", "muhammad@motleyterpz.com", "imran@motleyterpz.com"]
MODES = ("legacy", "new")
SEND_TZ = "America/Los_Angeles"
SEND_HOUR = 13

NEW_AR_START = "2026-06-01"
RANGE_STR = "7, 15, 21, 30, 60, 90, 120"
LOGO_FILE = "FULL_LOGO295b72.png"
PAGE_DIR = os.path.dirname(os.path.abspath(ard.__file__))
DASH = "—"


def send_scheduled_ar_report():
	"""Cron entry. Fires at 11:00 site time (America/Adak), which is 13:00 in
	California all year because both follow US DST. Re-checks the California
	clock anyway so a site timezone change cannot move the send silently."""
	from zoneinfo import ZoneInfo

	from frappe.utils import get_system_timezone, now_datetime

	local = now_datetime().replace(tzinfo=ZoneInfo(get_system_timezone()))
	if local.astimezone(ZoneInfo(SEND_TZ)).hour != SEND_HOUR:
		return

	frappe.enqueue(
		"cannabis_management.api.ar_dashboard_email.send_ar_dashboard_email",
		queue="long",
		timeout=1500,
		job_id="ar_dashboard_daily_email",
		deduplicate=True,
	)


def send_ar_dashboard_email(to=None, cc=None):
	"""Build both sheets and send one email. Safe to call by hand for an
	immediate send (``to`` / ``cc`` override the defaults)."""
	to = to or TO
	cc = CC if cc is None else cc
	as_of = nowdate()

	attachments = []
	for mode in MODES:
		label = ard._AR_MODE_LABELS[mode]
		attachments.append({
			"fname": "{0} Aging - All Entities - {1}.pdf".format(label, as_of),
			"fcontent": ard._render_ar_pdf(build_report_document(mode, as_of)),
		})

	frappe.sendmail(
		recipients=to,
		cc=cc,
		subject="AR Aging Report - All Entities - as of {0}".format(as_of),
		message=(
			"<p>Attached are today's <b>Legacy AR</b> and <b>New AR</b> aging reports "
			"for <b>All Entities</b>, as of {0}.</p>"
			"<p>Sent automatically from the AR Dashboard.</p>"
		).format(as_of),
		attachments=attachments,
		reference_doctype="Page",
		reference_name="ar-dashboard",
		now=True,
	)
	return {"to": to, "cc": cc, "files": [a["fname"] for a in attachments]}


# ─── Data: the page's All Entities load, per mode ────────────────────────────


def _load_rows(mode, as_of):
	"""load_all_entities: every company except the TMM Group roll-up, merged."""
	companies = [c for c in ard.init_page()["companies"] if c not in ("TMM Group", "__ALL__")]
	rows, ranges = [], None
	for company in companies:
		res = ard.get_ar_data(company, report_date=as_of, customer=None, ageing_based_on="Due Date",
		                      range_str=RANGE_STR, ar_mode=mode)
		ranges = ranges or res.get("ranges")
		for row in res.get("rows") or []:
			row["company"] = company
			rows.append(row)
	return _filter_rows(rows, mode), ranges or []


def _filter_rows(rows, mode):
	"""filter_rows with the page's defaults: New AR mode opens with New AR > 0 on."""
	rows = [r for r in rows if (r.get("outstanding") or 0) > 0]
	if mode == "new":
		new_ar = {}
		for r in rows:
			if not r.get("is_legacy") and str(r.get("posting_date") or "") >= NEW_AR_START:
				new_ar[r["party"]] = new_ar.get(r["party"], 0) + (r.get("outstanding") or 0)
		rows = [r for r in rows if new_ar.get(r["party"], 0) > 1]
	return rows


def _days(later, earlier):
	if not later or not earlier:
		return None
	return (getdate(later) - getdate(earlier)).days


def _classify(row, anchor):
	past = _days(anchor, row.get("due_date"))
	if past is not None and past > 0:
		return "bad", None
	left = _days(row.get("due_date"), anchor)
	if left is None or left < 0:
		left = 0
	return "good", ("g1" if left <= 10 else "g2" if left <= 20 else "g3")


def _na_sum(rows, anchor):
	s = dict(total=0, good=0, bad=0, g1=0, g2=0, g3=0)
	for row in rows:
		amt = row.get("outstanding") or 0
		if amt <= 0 or row.get("is_legacy"):
			continue
		section, bkey = _classify(row, anchor)
		s["total"] += amt
		if section == "good":
			s["good"] += amt
			s[bkey] += amt
		else:
			s["bad"] += amt
	return s


# ─── Markup: build_table_html already trimmed by ard_build_report_table ──────


def _cur(v):
	return "${:,.2f}".format(v or 0)


def _cur_or_dash(v):
	return _cur(v) if v and v > 0 else DASH


def _range_cls(idx):
	return ("bar-current", "bar-30", "bar-60")[idx] if idx < 3 else "bar-90"


def _sums(rows, ranges):
	s = dict(invoiced=0, paid=0, outstanding=0)
	for r in ranges:
		s[r["key"]] = 0
	for row in rows:
		for k in s:
			s[k] += row.get(k) or 0
	return s


def _row_cells(mode, sums, na, name_html):
	"""One sheet row: Customer, the mode's money columns, then the aging buckets."""
	cells = ['<td class="ard-td-sticky">{0}</td>'.format(name_html)]
	if mode == "legacy":
		cells += [
			'<td class="ard-num ard-total-cell">{0}</td>'.format(_cur(sums["invoiced"])),
			'<td class="ard-num ard-total-cell">{0}</td>'.format(_cur(sums["paid"])),
			'<td class="ard-num ard-total-cell ard-outstanding">{0}</td>'.format(_cur(sums["outstanding"])),
		]
	else:
		cells += [
			'<td class="ard-num ard-total-cell ard-na-new">{0}</td>'.format(_cur_or_dash(na["total"])),
			'<td class="ard-num ard-total-cell ard-na-good">{0}</td>'.format(_cur_or_dash(na["good"])),
			'<td class="ard-num ard-total-cell ard-na-bad">{0}</td>'.format(_cur_or_dash(na["bad"])),
			'<td class="ard-num ard-total-cell ard-term-red">{0}</td>'.format(_cur_or_dash(na["g1"])),
			'<td class="ard-num ard-total-cell ard-term-amber">{0}</td>'.format(_cur_or_dash(na["g2"])),
			'<td class="ard-num ard-total-cell ard-term-green">{0}</td>'.format(_cur_or_dash(na["g3"])),
		]
	return cells


def _sheet_html(mode, rows, ranges, as_of):
	esc = frappe.utils.escape_html
	range_cells = lambda sums: "".join(
		'<td class="ard-range-cell {0} ard-total-cell">{1}</td>'.format(_range_cls(i), _cur_or_dash(sums[r["key"]]))
		for i, r in enumerate(ranges)
	)

	groups = {}
	for row in rows:
		g = groups.setdefault(row["party"], {"name": row.get("customer_name") or row["party"], "rows": []})
		g["rows"].append(row)
	order = sorted(groups, key=lambda p: (groups[p]["name"] or "").lower())

	totals = _sums(rows, ranges)
	top = _row_cells(mode, totals, _na_sum(rows, as_of) if mode == "new" else None,
	                 'TOTALS<div class="ard-invoice-count-compact">All Entities &bull; {0} inv &bull; {1} cust</div>'
	                 .format(len(rows), len(order)))
	top = [c.replace('<td class="ard-td-sticky">', '<td class="ard-td-sticky ard-total-cell">', 1) for c in top]

	head = ['<th class="ard-th-sticky">Customer</th>']
	if mode == "legacy":
		head += ['<th class="ard-th-num">Invoiced</th>', '<th class="ard-th-num">Paid</th>',
		         '<th class="ard-th-num">Outstanding</th>']
		band = ""
	else:
		head += [
			'<th class="ard-th-num ard-na-new">New AR</th>',
			'<th class="ard-th-num ard-na-good">Total New AR on Good standing</th>',
			'<th class="ard-th-num ard-na-bad">Total New AR on Bad standing</th>',
			'<th class="ard-th-num ard-term-red">0-10 Days<br><small>left in terms</small></th>',
			'<th class="ard-th-num ard-term-amber">10-20 Days<br><small>left in terms</small></th>',
			'<th class="ard-th-num ard-term-green">20-30 Days<br><small>left in terms</small></th>',
		]
		band = (
			'<tr class="ard-band-row"><th colspan="4" class="ard-band-blank"></th>'
			'<th colspan="3" class="ard-band-terms">New AR on Terms</th>'
			'<th colspan="{0}" class="ard-band-overdue">OVERDUE NEW AR</th></tr>'
		).format(len(ranges))
	head += ['<th class="ard-th-range {0}">{1}<br><small>Days</small></th>'.format(_range_cls(i), esc(r["label"]))
	         for i, r in enumerate(ranges)]

	body = []
	for party in order:
		g = groups[party]
		sums = _sums(g["rows"], ranges)
		cells = _row_cells(mode, sums, _na_sum(g["rows"], as_of) if mode == "new" else None,
		                   '<span class="ard-customer-group-name">{0}</span>'.format(esc(g["name"])))
		body.append('<tr class="ard-customer-group-row">{0}{1}</tr>'.format("".join(cells), range_cells(sums)))

	return (
		'<table class="ard-table"><thead>'
		'<tr class="ard-totals-row ard-top-totals">{0}{1}</tr>{2}'
		'<tr class="ard-head-row">{3}</tr></thead><tbody>{4}</tbody></table>'
	).format("".join(top), range_cells(totals), band, "".join(head), "".join(body))


def _print_css():
	"""ard_print_css() + ard_report_css() from ar_dashboard.js, verbatim."""
	return (
		"body{padding:0;margin:0;background:#fff;}"
		".ard-container{max-width:none!important;margin:0!important;padding:4px 6px!important;}"
		"#ard-pdf-page{padding:0;}"
		".ard-pdf-logo-banner{background:#5a1a9e;padding:12px 18px;margin:0 0 8px;text-align:left;}"
		".ard-pdf-logo-banner img{height:64px;width:auto;display:inline-block;}"
		".ard-invoice-row{display:none!important;}"
		".ard-invoice-count-compact,.ard-customer-group-id{display:none!important;}"
		".ard-td-sticky{white-space:normal!important;}"
		".ard-customer-group-name{font-size:9px!important;font-weight:700!important;white-space:normal!important;}"
		".ard-table-wrap{overflow:visible!important;max-height:none!important;height:auto!important;"
		"border:none!important;box-shadow:none!important;border-radius:0!important;}"
		".ard-table{width:auto!important;}"
		".ard-table th,.ard-table td{font-size:7px!important;padding:1px 3px!important;white-space:nowrap;}"
		".ard-th-sticky,.ard-td-sticky,.ard-grid-rownum,.ard-grid-corner,"
		".ard-table thead th{position:static!important;left:auto!important;top:auto!important;box-shadow:none!important;}"
		"*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important;}"
		"@page{size:landscape;margin:5mm;}"
		# ard_report_css
		".ard-container{padding:0!important;margin:0!important;}"
		".ard-pdf-logo-banner{text-align:center;}"
		".ard-table{width:100%!important;table-layout:fixed!important;}"
		".ard-table th,.ard-table td{font-size:7px!important;white-space:normal!important;overflow:hidden;}"
		".ard-table th.ard-th-sticky,.ard-table td.ard-td-sticky{width:21%!important;}"
		".ard-customer-group-name{font-size:7px!important;}"
	)


def _logo_data_uri():
	path = frappe.get_site_path("public", "files", LOGO_FILE)
	if not os.path.exists(path):
		return None
	with open(path, "rb") as f:
		return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def build_report_document(mode, as_of=None):
	"""ard_report_document(): the full HTML handed to wkhtmltopdf."""
	as_of = as_of or nowdate()
	rows, ranges = _load_rows(mode, as_of)
	label = ard._AR_MODE_LABELS[mode]

	with open(os.path.join(PAGE_DIR, "ar_dashboard.css")) as f:
		page_css = f.read()
	logo = _logo_data_uri()
	banner = '<div class="ard-pdf-logo-banner"><img src="{0}" alt="Motley Terpz"></div>'.format(logo) if logo else ""

	table = _sheet_html(mode, rows, ranges, as_of) if rows else (
		'<p>No outstanding receivables found across any entity.</p>'
	)
	return (
		'<!doctype html><html><head><meta charset="utf-8"><title>{0} Aging Report</title>'
		"<style>{1}</style><style>{2}</style></head><body><div id=\"ard-pdf-page\">{3}"
		'<div class="ard-container"><div class="ard-table-wrap ard-newar-table ard-sheet{4}">{5}'
		"</div></div></div></body></html>"
	).format(label, page_css, _print_css(), banner, " ard-mode-new" if mode == "new" else "", table)
