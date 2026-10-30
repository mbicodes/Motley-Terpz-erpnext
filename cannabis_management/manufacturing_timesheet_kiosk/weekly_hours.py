"""Friday end-of-day email to every kiosk employee with their hours for the week.

Week = Saturday 00:00 → Friday end of day, kiosk time (America/Los_Angeles). Sessions are
counted on the day they started. The scheduler fires hourly on Fri/Sat (site tz is
America/Adak, not Pacific), and send_weekly_hours_emails only acts once the kiosk clock
reaches Friday SEND_HOUR; a stored default stops a second send for the same week.
"""

import datetime

import frappe
from frappe.utils import flt, getdate

from cannabis_management.manufacturing_timesheet_kiosk.api import (
	_EMAIL_WRAP,
	_employee_email,
	_kiosk_now,
	_kiosk_roster,
)

SEND_HOUR = 23
LAST_SENT_KEY = "kiosk_weekly_hours_last_sent"

CONTACT_NAME = "Muhammad"
CONTACT_EMPLOYEE = "HR-EMP-00015"


def _week_ending(now):
	"""The Friday whose emails are due at `now` (kiosk time), or None if not due yet."""
	if now.weekday() == 4 and now.hour >= SEND_HOUR:
		return now.date()
	if now.weekday() == 5 and now.hour < 6:
		return now.date() - datetime.timedelta(days=1)
	return None


def send_weekly_hours_emails():
	friday = _week_ending(_kiosk_now())
	if not friday or frappe.db.get_default(LAST_SENT_KEY) == str(friday):
		return
	send_for_week(friday)
	frappe.db.set_default(LAST_SENT_KEY, str(friday))
	frappe.db.commit()


def _week_rows(week_start, week_end):
	return frappe.db.sql(
		"""
		select t.employee, t.docstatus, date(d.from_time) as day, d.hours
		from `tabTimesheet` t
		join `tabTimesheet Detail` d on d.parent = t.name
		where t.docstatus < 2
			and d.from_time >= %s and d.from_time < %s
		""",
		(week_start, week_end + datetime.timedelta(days=1)),
		as_dict=True,
	)


def send_for_week(friday, only_employee=None, recipient_override=None):
	"""Send the weekly hours email for the Sat–Fri week ending `friday`.

	only_employee / recipient_override are for testing: limit to one employee and/or send
	to a different address instead of the employee.
	"""
	friday = getdate(friday)
	saturday = friday - datetime.timedelta(days=6)

	per_employee = {}
	for row in _week_rows(saturday, friday):
		entry = per_employee.setdefault(row.employee, {"days": {}, "running": False})
		if row.docstatus == 0:
			entry["running"] = True
			continue
		entry["days"][row.day] = entry["days"].get(row.day, 0) + flt(row.hours)

	contact_phone = frappe.db.get_value("Employee", CONTACT_EMPLOYEE, "cell_number")
	sent = 0
	for emp in _kiosk_roster():
		if only_employee and emp.name != only_employee:
			continue
		entry = per_employee.get(emp.name)
		if not entry:
			continue
		email, employee_name = _employee_email(emp.name)
		if not email:
			frappe.log_error(
				title="Kiosk: no email on file for weekly hours",
				message=f"employee={emp.name} week_ending={friday}",
			)
			continue
		_send_one(recipient_override or email, employee_name, saturday, friday, entry, contact_phone)
		sent += 1
	return sent


def _send_one(email, employee_name, saturday, friday, entry, contact_phone):
	total = sum(entry["days"].values())
	day_rows = ""
	for i in range(7):
		day = saturday + datetime.timedelta(days=i)
		hours = entry["days"].get(day)
		day_rows += f"""
		<tr>
		  <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;">{day.strftime("%a %b %d")}</td>
		  <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;">{f"{hours:.2f}" if hours else "—"}</td>
		</tr>"""

	running_note = ""
	if entry["running"]:
		running_note = """
		<p style="color:#64748b;font-size:12.5px;">You still had a session running when this email
		   was sent, so it is not included in the total above.</p>"""

	call = f"call <b>{CONTACT_NAME}</b>"
	if contact_phone:
		call += f" at <b>{contact_phone}</b>"

	body = f"""
	<p>Hi {employee_name},</p>
	<p>Here are your kiosk hours for the week of
	   <b>{saturday.strftime("%b %d")} – {friday.strftime("%b %d, %Y")}</b>.</p>
	<div style="text-align:center;margin:18px 0;">
	  <div style="font-size:34px;font-weight:800;color:#0f172a;">{total:.2f} hrs</div>
	  <div style="color:#64748b;font-size:12.5px;">Total this week</div>
	</div>
	<table style="width:100%;border-collapse:collapse;font-size:13.5px;">
	  <tr style="background:#f8fafc;">
	    <th style="padding:6px 8px;text-align:left;">Day</th>
	    <th style="padding:6px 8px;text-align:right;">Hours</th>
	  </tr>
	  {day_rows}
	</table>
	{running_note}
	<p style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px 14px;color:#9a3412;margin-top:18px;">
	   If anything looks wrong or you have any issue with your hours, please {call}
	   and ask him.</p>
	"""
	html = _EMAIL_WRAP.format(
		gradient="linear-gradient(135deg,#1e293b,#334155)",
		heading="Your Hours This Week",
		body=body,
	)
	try:
		frappe.sendmail(
			recipients=[email],
			subject=f"Your hours this week: {total:.2f} hrs ({saturday.strftime('%b %d')} – {friday.strftime('%b %d')})",
			message=html,
		)
	except Exception:
		frappe.log_error(title="Kiosk weekly hours email failed", message=frappe.get_traceback())
