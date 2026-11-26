import base64
import datetime
import re

import frappe
from frappe import _
from frappe.utils import escape_html, flt, get_datetime, getdate
from frappe.utils.pdf import get_pdf

from cannabis_management.manufacturing_timesheet_kiosk.api import (
	OVERTIME_FIELD,
	OVERTIME_REQUEST_FIELD,
	_get_open_timesheet,
	_kiosk_now,
)

MAX_RANGE_DAYS = 1100
LOGO_FILE = ("public", "images", "kiosk", "mlt-dark.png")


def _overtime_clause():
	conditions = []
	joins = ""
	if frappe.db.has_column("Timesheet Detail", OVERTIME_FIELD):
		conditions.append(f"d.{OVERTIME_FIELD} = 1")
	if frappe.db.has_column("Timesheet", OVERTIME_REQUEST_FIELD) and frappe.db.table_exists(
		"Kiosk Overtime Request"
	):
		joins = f"left join `tabKiosk Overtime Request` kor on kor.name = ts.{OVERTIME_REQUEST_FIELD}"
		conditions.append("(kor.name is not null and ifnull(kor.timesheet, '') != ts.name)")
	if not conditions:
		return "0", joins
	return "(" + " or ".join(conditions) + ")", joins


def _first_day(employee):
	first = frappe.db.sql(
		"""
		select min(d.from_time)
		from `tabTimesheet Detail` d
		inner join `tabTimesheet` ts on ts.name = d.parent
		where ts.employee = %s and ts.docstatus = 1 and d.from_time is not null
		""",
		employee,
	)
	return getdate(first[0][0]) if first and first[0][0] else None


def _stamp(value):
	if not value:
		return None
	return str(get_datetime(value).replace(microsecond=0))


def build_report(employee, from_date=None, to_date=None):
	today = _kiosk_now().date()
	to_date = getdate(to_date) if to_date else today
	from_date = getdate(from_date) if from_date else (_first_day(employee) or to_date)

	if from_date > to_date:
		frappe.throw(_("The start date must be on or before the end date."))
	if (to_date - from_date).days > MAX_RANGE_DAYS:
		frappe.throw(_("Please pick a range of three years or less."))

	overtime_expr, joins = _overtime_clause()
	rows = frappe.db.sql(
		f"""
		select ts.name as timesheet, d.activity_type, d.from_time, d.to_time, d.hours,
			{overtime_expr} as overtime
		from `tabTimesheet Detail` d
		inner join `tabTimesheet` ts on ts.name = d.parent
		{joins}
		where ts.employee = %(employee)s
			and ts.docstatus = 1
			and d.from_time >= %(start)s
			and d.from_time < %(end)s
		order by d.from_time asc, d.idx asc
		""",
		{"employee": employee, "start": from_date, "end": to_date + datetime.timedelta(days=1)},
		as_dict=True,
	)

	days = {}
	total = 0.0
	overtime = 0.0
	for row in rows:
		hours = flt(row.hours)
		day = get_datetime(row.from_time).date()
		entry = days.setdefault(day, {"date": str(day), "hours": 0.0, "overtime_hours": 0.0, "entries": []})
		entry["hours"] += hours
		total += hours
		if row.overtime:
			entry["overtime_hours"] += hours
			overtime += hours
		entry["entries"].append(
			{
				"timesheet": row.timesheet,
				"activity_type": row.activity_type or "",
				"start": _stamp(row.from_time),
				"end": _stamp(row.to_time),
				"hours": flt(hours, 2),
				"overtime": bool(row.overtime),
			}
		)

	for entry in days.values():
		entry["hours"] = flt(entry["hours"], 2)
		entry["overtime_hours"] = flt(entry["overtime_hours"], 2)

	open_ts = _get_open_timesheet(employee)

	return {
		"employee": employee,
		"employee_name": frappe.db.get_value("Employee", employee, "employee_name") or employee,
		"from_date": str(from_date),
		"to_date": str(to_date),
		"generated_at": _stamp(_kiosk_now()),
		"total_hours": flt(total, 2),
		"overtime_hours": flt(overtime, 2),
		"regular_hours": flt(total - overtime, 2),
		"days_worked": len(days),
		"entries": len(rows),
		"days": [days[d] for d in sorted(days)],
		"open_session": (
			{"activity_type": open_ts.activity_type, "start_time": _stamp(open_ts.from_time)}
			if open_ts
			else None
		),
	}


def _logo_data_uri():
	try:
		with open(frappe.get_app_path("cannabis_management", *LOGO_FILE), "rb") as fh:
			return "data:image/png;base64," + base64.b64encode(fh.read()).decode()
	except OSError:
		return None


def _fmt_day(value):
	d = getdate(value)
	return d.strftime("%a, %b ") + str(d.day) + d.strftime(", %Y")


def _fmt_time(value):
	if not value:
		return "—"
	t = get_datetime(value)
	return t.strftime("%I:%M %p").lstrip("0")


def _fmt_hours(value):
	value = flt(value)
	h = int(value)
	m = int(round((value - h) * 60))
	if m == 60:
		h, m = h + 1, 0
	return f"{value:.2f}", f"{h}h {m:02d}m"


_PDF_CSS = """
body { font-family: Helvetica, Arial, sans-serif; color: #1d1029; font-size: 11.5px; margin: 0; }
.head { width: 100%; border-collapse: collapse; margin-bottom: 14px; }
.head td { vertical-align: middle; }
.logo { width: 64px; }
.brand { font-size: 10.5px; color: #6b5a80; letter-spacing: .4px; }
.title { font-size: 22px; font-weight: bold; color: #2a0b52; margin: 2px 0 0; }
.who { text-align: right; padding-right: 6px; white-space: nowrap; }
.who .name { font-size: 15px; font-weight: bold; color: #1d1029; }
.who .meta { font-size: 10.5px; color: #6b5a80; margin-top: 3px; }
.bar { height: 4px; background: #4f149f; margin: 0 0 14px; }
.stats { width: 100%; border-collapse: collapse; margin: 0 0 16px; }
.stats td { background: #f5ecfb; border: 1px solid #e2cdf0; border-radius: 6px; padding: 9px 12px; width: 23.5%; }
.stats td.gap { background: none; border: 0; padding: 0; width: 2%; }
.stats .v { font-size: 19px; font-weight: bold; color: #2a0b52; }
.stats .l { font-size: 10px; color: #6b5a80; margin-top: 2px; }
.stats td.ot { background: #fff4e5; border-color: #f6d3a6; }
.stats td.ot .v { color: #9a4a00; }
table.rows { width: 100%; border-collapse: collapse; }
table.rows th { background: #2a0b52; color: #fff; font-size: 10.5px; text-align: left; padding: 7px 8px; }
table.rows th.num, table.rows td.num { text-align: right; }
table.rows td { padding: 6px 8px; border-bottom: 1px solid #ece4f2; }
tr.day td { background: #efe2f8; color: #2a0b52; font-weight: bold; border-bottom: 1px solid #dcc6ec; }
tr.total td { background: #2a0b52; color: #fff; font-weight: bold; font-size: 12.5px; }
.ot-tag { display: inline-block; background: #ffe2bf; color: #8a4300; font-size: 9px; font-weight: bold; padding: 1px 5px; border-radius: 3px; margin-left: 6px; }
.muted { color: #8a7a9c; }
.empty { padding: 26px; text-align: center; color: #6b5a80; border: 1px dashed #d9c7e8; border-radius: 6px; }
.note { margin-top: 12px; font-size: 10.5px; color: #6b5a80; }
tr { page-break-inside: avoid; }
"""


def _report_html(report):
	e = escape_html
	logo = _logo_data_uri()
	period = f"{_fmt_day(report['from_date'])} – {_fmt_day(report['to_date'])}"

	body_rows = []
	for day in report["days"]:
		dec, hm = _fmt_hours(day["hours"])
		ot_note = ""
		if day["overtime_hours"]:
			ot_note = f' <span class="muted">({_fmt_hours(day["overtime_hours"])[0]} overtime)</span>'
		body_rows.append(
			f'<tr class="day"><td colspan="4">{e(_fmt_day(day["date"]))}{ot_note}</td>'
			f'<td class="num">{dec}</td><td class="num">{hm}</td></tr>'
		)
		for row in day["entries"]:
			r_dec, r_hm = _fmt_hours(row["hours"])
			tag = '<span class="ot-tag">OT</span>' if row["overtime"] else ""
			body_rows.append(
				"<tr>"
				f'<td class="muted">{e(row["timesheet"])}</td>'
				f'<td>{e(row["activity_type"] or "—")}{tag}</td>'
				f"<td>{_fmt_time(row['start'])}</td>"
				f"<td>{_fmt_time(row['end'])}</td>"
				f'<td class="num">{r_dec}</td>'
				f'<td class="num">{r_hm}</td>'
				"</tr>"
			)

	if body_rows:
		t_dec, t_hm = _fmt_hours(report["total_hours"])
		table = (
			'<table class="rows"><thead><tr><th>Timesheet</th><th>Activity</th><th>Clock in</th>'
			'<th>Clock out</th><th class="num">Hours</th><th class="num">H:M</th></tr></thead><tbody>'
			+ "".join(body_rows)
			+ f'<tr class="total"><td colspan="4">Total for period</td><td class="num">{t_dec}</td>'
			f'<td class="num">{t_hm}</td></tr></tbody></table>'
		)
	else:
		table = '<div class="empty">No completed shifts in this period.</div>'

	open_note = ""
	if report.get("open_session"):
		s = report["open_session"]
		open_note = (
			f'<p class="note">Currently clocked in since {e(_fmt_day(s["start_time"]))} '
			f'{_fmt_time(s["start_time"])} ({e(s["activity_type"] or "")}). That shift is not '
			"included until it is clocked out.</p>"
		)

	logo_cell = f'<td class="logo"><img src="{logo}" width="56"></td>' if logo else ""

	return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_PDF_CSS}</style></head><body>
<table class="head"><tr>
	{logo_cell}
	<td><div class="brand">MASTER TOUCH MANUFACTURING</div><div class="title">Timesheet</div></td>
	<td class="who"><div class="name">{e(report['employee_name'])}</div>
		<div class="meta">{e(period)}</div>
		<div class="meta">Generated {e(_fmt_day(report['generated_at']))} at {_fmt_time(report['generated_at'])} (Pacific)</div></td>
</tr></table>
<div class="bar"></div>
<table class="stats"><tr>
	<td><div class="v">{_fmt_hours(report['total_hours'])[0]}</div><div class="l">Total hours · {_fmt_hours(report['total_hours'])[1]}</div></td>
	<td class="gap"></td>
	<td><div class="v">{_fmt_hours(report['regular_hours'])[0]}</div><div class="l">Regular hours</div></td>
	<td class="gap"></td>
	<td class="ot"><div class="v">{_fmt_hours(report['overtime_hours'])[0]}</div><div class="l">Overtime hours</div></td>
	<td class="gap"></td>
	<td><div class="v">{report['days_worked']}</div><div class="l">Days worked · {report['entries']} entries</div></td>
</tr></table>
{table}
{open_note}
<p class="note">Times are Pacific. Shifts are listed on the day they started. Questions about these hours? Ask your manager.</p>
</body></html>"""


def _filename(report):
	name = re.sub(r"[^A-Za-z0-9 _.-]+", "", report["employee_name"]).strip() or "Employee"
	return f"Timesheet - {name} - {report['from_date']} to {report['to_date']}.pdf"


def render_pdf(report):
	pdf = get_pdf(
		_report_html(report),
		{
			"page-size": "Letter",
			"margin-top": "12mm",
			"margin-bottom": "12mm",
			"margin-left": "11mm",
			"margin-right": "11mm",
		},
	)
	return {"filename": _filename(report), "content": base64.b64encode(pdf).decode()}
