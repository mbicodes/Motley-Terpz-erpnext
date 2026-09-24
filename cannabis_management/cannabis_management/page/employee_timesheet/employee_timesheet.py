# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Employee Timesheet — hours and overtime per employee, per shift day.

Three things this has to get right:

1. TIME ZONE. Frappe stores naive datetimes in the *site* time zone, which on
   this bench is America/Adak — not where the work happens. Every timestamp is
   converted to REPORT_TZ (California) before anything else looks at it, so a
   shift is dated by the day it happened locally, and the 6am email really is
   6am for the people reading it.

2. SHIFT DAY, not calendar day. A shift that starts at 10pm and ends at 2am is
   one night's work. Every session is attributed to the day it STARTED, so those
   hours stay on the night they belong to instead of splitting across midnight.
   A session starting before SHIFT_DAY_CUTOFF_HOUR is treated as a continuation
   of the previous night for the same reason.

3. OVERTIME is per shift day, not per session. Someone who works 5 hours, breaks,
   then works 4 more has done 9 hours that day — one hour of it overtime — even
   though neither session on its own passed 8.
"""

import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate

# Where the work actually happens. Everything user-facing is in this zone.
REPORT_TZ = "America/Los_Angeles"

# Hours past which a shift day counts as overtime.
OVERTIME_AFTER_HOURS = 8.0

# A session starting before this hour belongs to the previous shift day — it is
# the tail of a night shift, not the start of a new one.
SHIFT_DAY_CUTOFF_HOUR = 4

# Pay runs Friday to Friday, fortnightly. This is a Friday; every pay period is
# counted in 14-day steps from here, so the cycle survives year boundaries
# without a stored calendar.
PAY_PERIOD_ANCHOR = "2026-01-02"
PAY_PERIOD_DAYS = 14

REPORT_RECIPIENTS = [
	"muhammad@motleyterpz.com",
	"matt@motleyterpz.com",
	"imran@motleyterpz.com",
	"jamie@motleyterpz.com",
]


# ── Time zone ────────────────────────────────────────────────────────────────

def _site_tz():
	return ZoneInfo(frappe.db.get_single_value("System Settings", "time_zone") or "UTC")


def _to_report_tz(value):
	"""Naive site-local datetime -> naive datetime in REPORT_TZ."""
	if not value:
		return None
	dt = get_datetime(value)
	return dt.replace(tzinfo=_site_tz()).astimezone(ZoneInfo(REPORT_TZ)).replace(tzinfo=None)


def report_now():
	"""'Now' where the work happens, not where the server thinks it is."""
	return datetime.datetime.now(ZoneInfo(REPORT_TZ)).replace(tzinfo=None)


def report_today():
	return report_now().date()


def _shift_day(started):
	"""The day a session's hours belong to (see the module docstring)."""
	if started.hour < SHIFT_DAY_CUTOFF_HOUR:
		return (started - datetime.timedelta(days=1)).date()
	return started.date()


# ── Pay periods ──────────────────────────────────────────────────────────────

def pay_period_for(day=None):
	"""(start, end) of the fortnight containing `day`. Ends on a Friday."""
	day = getdate(day or report_today())
	anchor = getdate(PAY_PERIOD_ANCHOR)
	elapsed = (day - anchor).days
	index = elapsed // PAY_PERIOD_DAYS
	start = add_days(anchor, index * PAY_PERIOD_DAYS)
	return start, add_days(start, PAY_PERIOD_DAYS - 1)


# ── Aggregation ──────────────────────────────────────────────────────────────

def _fetch_sessions(from_date, to_date, employee=None, include_open=False):
	"""Timesheet Detail rows whose SHIFT DAY falls in range.

	The SQL window is widened by a day at each end because a row is selected on
	its shift day, which the time-zone shift and the night-shift rule can move
	either side of its stored date. The precise filtering happens in Python once
	each row has been converted and dated.
	"""
	docstatuses = (0, 1) if include_open else (1,)
	conds = ["ts.docstatus in %(docstatuses)s"]
	values = {
		"docstatuses": docstatuses,
		"from_dt": f"{add_days(from_date, -2)} 00:00:00",
		"to_dt": f"{add_days(to_date, 2)} 23:59:59",
	}
	conds.append("td.from_time between %(from_dt)s and %(to_dt)s")
	if employee:
		conds.append("ts.employee = %(employee)s")
		values["employee"] = employee

	return frappe.db.sql(
		"""
		select ts.name as timesheet, ts.employee, ts.employee_name, ts.docstatus,
		       td.name as detail, td.from_time, td.to_time, td.hours,
		       td.activity_type, td.project
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		where {0}
		order by td.from_time
		""".format(" and ".join(conds)),
		values, as_dict=True,
	)


def build_rows(from_date, to_date, employee=None, include_open=False, overtime_only=False):
	"""One row per employee per shift day."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	groups = {}

	for s in _fetch_sessions(from_date, to_date, employee, include_open):
		started = _to_report_tz(s.from_time)
		ended = _to_report_tz(s.to_time)
		if not started:
			continue

		day = _shift_day(started)
		if day < from_date or day > to_date:
			continue

		# An open session (still clocked in) carries no hours yet: the kiosk
		# writes to_time = from_time as a placeholder on insert.
		open_session = s.docstatus == 0 and ended and ended <= started
		hours = 0.0 if open_session else flt(s.hours)

		key = (s.employee, day)
		g = groups.setdefault(key, {
			"employee": s.employee,
			"employee_name": s.employee_name or s.employee,
			"shift_day": day,
			"hours": 0.0,
			"sessions": 0,
			"open_sessions": 0,
			"first_in": started,
			"last_out": ended,
			"crosses_midnight": 0,
			"timesheets": set(),
		})
		g["hours"] += hours
		g["sessions"] += 1
		g["timesheets"].add(s.timesheet)
		if open_session:
			g["open_sessions"] += 1
		if started < g["first_in"]:
			g["first_in"] = started
		if ended and (not g["last_out"] or ended > g["last_out"]):
			g["last_out"] = ended
		if ended and ended.date() != started.date():
			g["crosses_midnight"] = 1

	rows = []
	for g in groups.values():
		total = flt(g["hours"], 2)
		overtime = max(0.0, total - OVERTIME_AFTER_HOURS)
		if overtime_only and overtime <= 0:
			continue
		g["hours"] = total
		g["regular_hours"] = flt(min(total, OVERTIME_AFTER_HOURS), 2)
		g["overtime_hours"] = flt(overtime, 2)
		g["shift_day"] = str(g["shift_day"])
		g["first_in"] = g["first_in"].strftime("%Y-%m-%d %H:%M") if g["first_in"] else None
		g["last_out"] = g["last_out"].strftime("%Y-%m-%d %H:%M") if g["last_out"] else None
		g["timesheets"] = sorted(g["timesheets"])
		rows.append(g)

	rows.sort(key=lambda r: (r["employee_name"].lower(), r["shift_day"]))
	return rows


def summarise(rows):
	return {
		"total_hours": flt(sum(r["hours"] for r in rows), 2),
		"regular_hours": flt(sum(r["regular_hours"] for r in rows), 2),
		"overtime_hours": flt(sum(r["overtime_hours"] for r in rows), 2),
		"employees": len({r["employee"] for r in rows}),
		"days": len({r["shift_day"] for r in rows}),
		"open_sessions": sum(r["open_sessions"] for r in rows),
	}


# ── Whitelisted API ──────────────────────────────────────────────────────────

@frappe.whitelist()
def get_timesheet(from_date=None, to_date=None, employee=None,
                  include_open=0, overtime_only=0):
	if not frappe.has_permission("Timesheet", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not from_date or not to_date:
		from_date, to_date = pay_period_for()

	rows = build_rows(
		from_date, to_date, employee,
		include_open=bool(int(include_open or 0)),
		overtime_only=bool(int(overtime_only or 0)),
	)
	period_start, period_end = pay_period_for()
	return {
		"rows": rows,
		"summary": summarise(rows),
		"from_date": str(getdate(from_date)),
		"to_date": str(getdate(to_date)),
		"today": str(report_today()),
		"current_period": [str(period_start), str(period_end)],
		"timezone": REPORT_TZ,
		"overtime_after": OVERTIME_AFTER_HOURS,
	}


@frappe.whitelist()
def get_pay_period(offset=0):
	"""Pay period `offset` fortnights from the current one (0 = current, -1 = last)."""
	start, _end = pay_period_for()
	start = add_days(start, int(offset) * PAY_PERIOD_DAYS)
	return {"from_date": str(start), "to_date": str(add_days(start, PAY_PERIOD_DAYS - 1))}


# ── Scheduled email ──────────────────────────────────────────────────────────
#
# Sent at 6am California, which is 6pm Pakistan. The cron that calls this is
# written in SITE time (America/Adak) — Adak and Los Angeles both follow US DST
# rules, so the gap between them is a constant 2 hours all year and "0 4 * * *"
# site-time is 6am California in both summer and winter. The job still derives
# its own dates from REPORT_TZ rather than trusting the clock that woke it.

def _html_table(rows, show_employee_totals=True):
	if not rows:
		return "<p style='color:#767b8a'>No timesheet entries for this period.</p>"

	th = ("padding:7px 10px;border-bottom:1px solid #e8e8ef;text-align:left;"
	      "font-size:11px;color:#767b8a;background:#f8f8fb;")
	td = "padding:7px 10px;border-bottom:1px solid #f0f0f5;font-size:12px;"
	num = td + "text-align:right;font-variant-numeric:tabular-nums;"

	html = [
		"<table style='width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif'>",
		f"<tr><th style='{th}'>Employee</th><th style='{th}'>Shift Day</th>"
		f"<th style='{th}'>First In</th><th style='{th}'>Last Out</th>"
		f"<th style='{th}text-align:right'>Total</th>"
		f"<th style='{th}text-align:right'>Regular</th>"
		f"<th style='{th}text-align:right'>Overtime</th></tr>",
	]

	for r in rows:
		flags = ""
		if r["crosses_midnight"]:
			flags += " <span style='font-size:10px;color:#c2410c'>(overnight)</span>"
		if r["open_sessions"]:
			flags += " <span style='font-size:10px;color:#4f46e5'>(open)</span>"
		ot_style = num + ("color:#c2410c;font-weight:bold;" if r["overtime_hours"] > 0 else "color:#767b8a;")
		html.append(
			f"<tr><td style='{td}'>{frappe.utils.escape_html(r['employee_name'])}</td>"
			f"<td style='{td}'>{r['shift_day']}{flags}</td>"
			f"<td style='{td}'>{(r['first_in'] or '')[11:]}</td>"
			f"<td style='{td}'>{(r['last_out'] or '')[11:]}</td>"
			f"<td style='{num}'>{r['hours']:.2f}</td>"
			f"<td style='{num}'>{r['regular_hours']:.2f}</td>"
			f"<td style='{ot_style}'>{r['overtime_hours']:.2f}</td></tr>"
		)

	s = summarise(rows)
	foot = td + "font-weight:bold;background:#f4f4fa;"
	footn = num + "font-weight:bold;background:#f4f4fa;"
	html.append(
		f"<tr><td style='{foot}' colspan='4'>Total — {s['employees']} employee(s)</td>"
		f"<td style='{footn}'>{s['total_hours']:.2f}</td>"
		f"<td style='{footn}'>{s['regular_hours']:.2f}</td>"
		f"<td style='{footn}color:#c2410c'>{s['overtime_hours']:.2f}</td></tr>"
	)
	html.append("</table>")
	return "".join(html)


def build_email(day=None):
	"""(subject, html) for the report covering `day` — yesterday by default.

	On a Friday the pay period to date is appended, because Friday is pay day.
	"""
	day = getdate(day or add_days(report_today(), -1))
	rows = build_rows(day, day, include_open=True)

	is_friday = day.weekday() == 4
	period_start, period_end = pay_period_for(day)

	parts = [
		f"<p style='font-family:Arial,Helvetica,sans-serif'>Timesheet for "
		f"<b>{day:%A, %d %B %Y}</b> (California time).</p>",
		_html_table(rows),
	]

	if is_friday:
		period_rows = build_rows(period_start, day, include_open=True)
		parts += [
			f"<h3 style='font-family:Arial,Helvetica,sans-serif;margin-top:26px'>"
			f"Pay period {period_start} to {period_end} — to date</h3>",
			_html_table(period_rows),
		]

	parts.append(
		"<p style='font-size:11px;color:#767b8a;font-family:Arial,Helvetica,sans-serif;margin-top:20px'>"
		"A shift is counted on the day it started, so a night shift running past midnight stays on "
		f"that night. Overtime is anything beyond {OVERTIME_AFTER_HOURS:g} hours per employee per "
		"shift day. Times are California local.</p>"
	)

	subject = f"Employee Timesheet — {day:%a %d %b %Y}"
	if is_friday:
		subject += " + pay period to date"
	return subject, "".join(parts)


def send_daily_report():
	"""Scheduler entry point — see the note above for the 6am California timing."""
	day = add_days(report_today(), -1)
	subject, message = build_email(day)

	frappe.sendmail(
		recipients=REPORT_RECIPIENTS,
		subject=subject,
		message=message,
		now=False,      # queued: a slow SMTP hop must not hold up the scheduler
	)
	frappe.logger().info(f"Employee Timesheet report queued for {day} -> {REPORT_RECIPIENTS}")
	return {"day": str(day), "recipients": REPORT_RECIPIENTS, "subject": subject}


# ── PDF export ───────────────────────────────────────────────────────────────

def _pdf_document(rows, from_date, to_date, employee=None):
	"""Print-ready version of what the page shows, grouped by employee."""
	s = summarise(rows)
	th = ("padding:6px 8px;border-bottom:1.5px solid #d8dae3;text-align:left;font-size:9px;"
	      "color:#6b7280;text-transform:uppercase;letter-spacing:.4px;")
	thn = th + "text-align:right;"
	td = "padding:5px 8px;border-bottom:1px solid #f0f0f5;font-size:10px;"
	num = td + "text-align:right;font-variant-numeric:tabular-nums;"
	emp = ("padding:6px 8px;border-bottom:1px solid #d8dae3;background:#f4f4fa;"
	       "font-size:10px;font-weight:bold;")
	empn = emp + "text-align:right;"

	who = ""
	if employee:
		who = f" &middot; {frappe.utils.escape_html(frappe.db.get_value('Employee', employee, 'employee_name') or employee)}"

	out = [
		"<html><head><meta charset='utf-8'><style>",
		"@page{size:A4 landscape;margin:10mm;}",
		"body{font-family:Arial,Helvetica,sans-serif;color:#16181d;margin:0;}",
		"*{-webkit-print-color-adjust:exact;print-color-adjust:exact;}",
		"</style></head><body>",
		f"<h2 style='margin:0 0 2px'>Employee Timesheet</h2>",
		f"<div style='font-size:10px;color:#6b7280;margin-bottom:12px'>"
		f"{from_date} to {to_date}{who} &middot; {REPORT_TZ} &middot; "
		f"overtime beyond {OVERTIME_AFTER_HOURS:g}h per shift day</div>",
		"<div style='font-size:11px;margin-bottom:12px'>"
		f"<b>{s['total_hours']:.2f}</b> total &nbsp;|&nbsp; "
		f"<b>{s['regular_hours']:.2f}</b> regular &nbsp;|&nbsp; "
		f"<b style='color:#c2410c'>{s['overtime_hours']:.2f}</b> overtime &nbsp;|&nbsp; "
		f"{s['employees']} employees &nbsp;|&nbsp; {s['days']} days</div>",
		"<table style='width:100%;border-collapse:collapse'>",
		f"<thead><tr><th style='{th}'>Employee</th><th style='{th}'>Shift Day</th>"
		f"<th style='{th}'>First In</th><th style='{th}'>Last Out</th>"
		f"<th style='{thn}'>Sessions</th><th style='{thn}'>Total</th>"
		f"<th style='{thn}'>Regular</th><th style='{thn}'>Overtime</th></tr></thead><tbody>",
	]

	order, by_emp = [], {}
	for r in rows:
		if r["employee"] not in by_emp:
			by_emp[r["employee"]] = []
			order.append(r["employee"])
		by_emp[r["employee"]].append(r)

	for key in order:
		group = by_emp[key]
		tot = sum(r["hours"] for r in group)
		reg = sum(r["regular_hours"] for r in group)
		ot = sum(r["overtime_hours"] for r in group)
		out.append(
			f"<tr><td style='{emp}'>{frappe.utils.escape_html(group[0]['employee_name'])}</td>"
			f"<td style='{emp}' colspan='3'>{len(group)} shift day(s)</td>"
			f"<td style='{empn}'>{sum(r['sessions'] for r in group)}</td>"
			f"<td style='{empn}'>{tot:.2f}</td><td style='{empn}'>{reg:.2f}</td>"
			f"<td style='{empn}color:#c2410c'>{ot:.2f}</td></tr>"
		)
		for r in group:
			flags = " <span style='font-size:8px;color:#c2410c'>OVERNIGHT</span>" if r["crosses_midnight"] else ""
			if r["open_sessions"]:
				flags += " <span style='font-size:8px;color:#5b4bdb'>OPEN</span>"
			ot_style = num + ("color:#c2410c;font-weight:bold;" if r["overtime_hours"] > 0 else "color:#b9bec9;")
			out.append(
				f"<tr><td style='{td}'></td><td style='{td}'>{r['shift_day']}{flags}</td>"
				f"<td style='{td}'>{(r['first_in'] or '')[11:]}</td>"
				f"<td style='{td}'>{(r['last_out'] or '')[11:]}</td>"
				f"<td style='{num}'>{r['sessions']}</td><td style='{num}'>{r['hours']:.2f}</td>"
				f"<td style='{num}'>{r['regular_hours']:.2f}</td><td style='{ot_style}'>{r['overtime_hours']:.2f}</td></tr>"
			)

	if not rows:
		out.append(f"<tr><td style='{td}' colspan='8'>No timesheet entries in this range.</td></tr>")

	out.append("</tbody></table></body></html>")
	return "".join(out)


@frappe.whitelist()
def export_pdf(from_date=None, to_date=None, employee=None,
               include_open=0, overtime_only=0):
	"""Download the current view as a PDF."""
	if not frappe.has_permission("Timesheet", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	if not from_date or not to_date:
		from_date, to_date = pay_period_for()
	from_date, to_date = getdate(from_date), getdate(to_date)

	rows = build_rows(
		from_date, to_date, employee,
		include_open=bool(int(include_open or 0)),
		overtime_only=bool(int(overtime_only or 0)),
	)

	from frappe.utils.pdf import get_pdf

	pdf = get_pdf(
		_pdf_document(rows, from_date, to_date, employee),
		options={"orientation": "Landscape", "page-size": "A4",
		         "margin-top": "10mm", "margin-bottom": "10mm",
		         "margin-left": "10mm", "margin-right": "10mm"},
	)

	frappe.local.response.filename = f"employee-timesheet-{from_date}-to-{to_date}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"
