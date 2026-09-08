# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

"""
API endpoints for the Manufacturing Timesheet Kiosk (``/manufacturing-timesheet``).

Flow:
	1. get_employee_board() -> every kiosk-enabled employee, with their running
	   timer if any. This is the page the kiosk sits on with nobody logged in -
	   allow_guest, no code needed yet.
	2. Employee taps their own card's Start/End button -> the page asks for their
	   code -> verify_access_code(access_code, employee) ->
	   {token, employee, employee_name, open_session, recent_timesheets}. Passing
	   `employee` (the card that was tapped) makes sure the code that was typed
	   actually belongs to *that* card, not just *some* employee.
	3. start_session(token, activity_type, start_time, photo) -> {name}
	   OR
	   end_session(token, end_time, photo) -> {timesheet, hours}

`token` is a short-lived (5 minute), single-use handle returned by
verify_access_code. It stands in for the employee for the rest of the flow so the
employee id is never trusted directly from the client, and a guest cannot start/end a
session without first passing the access-code check.

The access code itself lives in a plain Data field (see custom_fields.py) so this
lookup is a single indexed query rather than a decrypt-and-compare loop.

No separate "session" doctype: an open clock-in is just a Draft Timesheet whose single
Timesheet Detail row has ``from_time`` set and ``to_time``/``completed`` empty - the
same shape the Desk "Start Timer" button creates (see
erpnext/public/js/projects/timer.js). ERPNext only enforces "hours must be > 0" at
*submit* time (Timesheet.validate_mandatory_fields runs from on_submit, not validate),
so a Draft can sit half-filled indefinitely. Ending the session fills in to_time/hours
and submits it.

Verification photo: start_session/end_session both *require* a `photo` (base64 data
URL from the kiosk page's camera capture) - Camera, Activity Type and Start Time are
all mandatory now, matching what the kiosk UI enforces client-side. The photo is
written straight into a Long Text field on the Timesheet (see custom_fields.py) rather
than saved as a File attachment - deliberately, so there is nothing for anyone to
detach/delete independently of the Timesheet row itself.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from cannabis_management.manufacturing_timesheet_kiosk.custom_fields import (
	EMPLOYEE_FIELDS,
)

CODE_FIELD = EMPLOYEE_FIELDS[0]["fieldname"]
TOKEN_TTL_SECONDS = 300


def _client_ip():
	try:
		return frappe.local.request_ip
	except Exception:
		return None


def _log_attempt(employee, status, reason=None):
	try:
		employee_name = None
		if employee:
			employee_name = frappe.db.get_value("Employee", employee, "employee_name")

		frappe.get_doc(
			{
				"doctype": "Kiosk Access Log",
				"employee": employee,
				"employee_name": employee_name,
				"status": status,
				"reason": reason,
				"ip_address": _client_ip(),
				"attempted_at": now_datetime(),
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep - audit log must persist even if caller rolls back
	except Exception:
		frappe.log_error(title="Kiosk Access Log Failed")


def _make_token(employee):
	token = frappe.generate_hash(length=32)
	frappe.cache().set_value(f"kiosk_token:{token}", employee, expires_in_sec=TOKEN_TTL_SECONDS)
	return token


def _resolve_token(token):
	"""Look up the employee for a kiosk token without consuming it.

	The token is only invalidated once the caller's operation (start/end session)
	actually succeeds - see the explicit delete_value calls in start_session/
	end_session - so a failed attempt (e.g. duplicate open session) doesn't strand the
	employee without a valid token.
	"""
	if not token:
		frappe.throw(_("Missing kiosk session token"))

	employee = frappe.cache().get_value(f"kiosk_token:{token}")
	if not employee:
		frappe.throw(_("Your session has expired. Please enter your access code again."))

	return employee


def _get_open_timesheet(employee):
	"""The employee's Draft Timesheet with a not-yet-completed time log row, if any.

	Returns a dict with the Timesheet name plus that row's activity_type/from_time, or
	None. Kiosk-started Timesheets only ever carry one row, but this also recognises a
	Timesheet started from Desk (Start Timer) so the two never disagree.
	"""
	row = frappe.db.sql(
		"""
		select ts.name as timesheet, tsd.name as row_name, tsd.activity_type, tsd.from_time
		from `tabTimesheet Detail` tsd
		inner join `tabTimesheet` ts on ts.name = tsd.parent
		where ts.employee = %s
			and ts.docstatus = 0
			and tsd.from_time is not null
			and tsd.completed = 0
		order by tsd.creation desc
		limit 1
		""",
		employee,
		as_dict=True,
	)
	return row[0] if row else None


def _get_recent_timesheets(employee, limit=5):
	"""Last few *submitted* Timesheets for this employee, most recent first.

	Reads straight from `Timesheet`/`Timesheet Detail` so this also picks up any
	Timesheet entered outside the kiosk (e.g. from Desk).
	"""
	timesheets = frappe.get_all(
		"Timesheet",
		filters={"employee": employee, "docstatus": 1},
		fields=["name", "start_date", "total_hours"],
		order_by="start_date desc, creation desc",
		limit_page_length=limit,
	)

	for ts in timesheets:
		activity_types = frappe.get_all(
			"Timesheet Detail",
			filters={"parent": ts.name},
			fields=["activity_type"],
			pluck="activity_type",
		)
		ts["activity_types"] = ", ".join(dict.fromkeys(a for a in activity_types if a))

	return timesheets


@frappe.whitelist(allow_guest=True)
def get_employee_board():
	"""Every kiosk-enabled employee plus their running timer, if any.

	This is what the kiosk shows before anyone has entered a code - one "job card"
	per employee with a Start or End button on it. Tapping a card is what triggers
	the code prompt (see verify_access_code's `employee` argument), not this call.
	"""
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", CODE_FIELD: ["is", "set"]},
		fields=["name", "employee_name"],
		order_by="employee_name asc",
	)

	board = []
	for emp in employees:
		open_ts = _get_open_timesheet(emp.name)
		board.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"running": bool(open_ts),
				"activity_type": open_ts.activity_type if open_ts else None,
				"start_time": open_ts.from_time if open_ts else None,
			}
		)
	return board


@frappe.whitelist(allow_guest=True)
def get_activity_types():
	return frappe.get_all(
		"Activity Type",
		filters={"disabled": 0},
		fields=["name"],
		order_by="name asc",
		pluck="name",
	)


@frappe.whitelist(allow_guest=True)
def verify_access_code(access_code, employee=None):
	access_code = (access_code or "").strip()
	if not access_code:
		frappe.throw(_("Please enter your access code"))

	matched = frappe.db.get_value(
		"Employee",
		{CODE_FIELD: access_code, "status": "Active"},
		["name", "employee_name"],
		as_dict=True,
	)

	# Same message either way - whether the code is wrong outright, or is a real
	# code that just belongs to someone else's card - so failed attempts can't be
	# used to probe whose code is whose.
	if not matched or (employee and matched.name != employee):
		_log_attempt(matched.name if matched else None, "Failed", "Invalid access code")
		frappe.throw(_("Invalid access code"))

	_log_attempt(matched.name, "Success")

	open_ts = _get_open_timesheet(matched.name)

	return {
		"token": _make_token(matched.name),
		"employee": matched.name,
		"employee_name": matched.employee_name,
		"open_session": (
			{"activity_type": open_ts.activity_type, "start_time": open_ts.from_time}
			if open_ts
			else None
		),
		"recent_timesheets": _get_recent_timesheets(matched.name),
	}


@frappe.whitelist(allow_guest=True)
def start_session(token, activity_type, start_time=None, photo=None):
	employee = _resolve_token(token)

	# Camera, Activity Type and Start Time are all mandatory - none of these are
	# optional extras the kiosk can silently skip.
	if not activity_type:
		frappe.throw(_("Please select an Activity Type"))
	if not photo:
		frappe.throw(_("A verification photo is required to start."))
	if not start_time:
		start_time = now_datetime()

	if _get_open_timesheet(employee):
		frappe.throw(_("This employee already has an open kiosk session."))

	start_dt = get_datetime(start_time)
	company = frappe.db.get_value("Employee", employee, "company")

	# Draft, one incomplete row - the same shape Desk's "Start Timer" leaves behind.
	# The site's Timesheet after_insert hook will try to auto-submit this and fail
	# (hours is 0 until the row is completed); that failure is caught there and only
	# logs/msgprints, so the insert itself is unaffected and the Timesheet stays Draft.
	doc = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": employee,
			"company": company,
			"custom_start_verification_photo": photo,
			"time_logs": [
				{
					"activity_type": activity_type,
					"from_time": start_dt,
					"completed": 0,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {"name": doc.name, "activity_type": activity_type, "start_time": start_dt}


@frappe.whitelist(allow_guest=True)
def end_session(token, end_time=None, photo=None):
	employee = _resolve_token(token)

	if not photo:
		frappe.throw(_("A verification photo is required to end."))

	open_ts = _get_open_timesheet(employee)
	if not open_ts:
		frappe.throw(_("No open kiosk session found for this employee."))

	start_dt = get_datetime(open_ts.from_time)
	end_dt = get_datetime(end_time) if end_time else now_datetime()

	if end_dt <= start_dt:
		frappe.throw(_("End time must be after the start time."))

	# Rounded to the nearest hundredth of an hour (~36 seconds) for the kiosk
	# receipt/display. The Timesheet Detail row itself is recalculated by ERPNext's
	# own Timesheet.calculate_hours() from from_time/to_time (same formula used
	# everywhere else in ERPNext) when the doc is saved below, so the two stay
	# consistent.
	hours = flt((end_dt - start_dt).total_seconds() / 3600.0, 2)

	timesheet = frappe.get_doc("Timesheet", open_ts.timesheet)
	row = timesheet.get("time_logs", {"name": open_ts.row_name})[0]
	row.to_time = end_dt
	row.hours = hours
	row.completed = 1
	timesheet.custom_end_verification_photo = photo
	timesheet.save(ignore_permissions=True)
	timesheet.submit()

	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {
		"timesheet": timesheet.name,
		"hours": hours,
		"activity_type": open_ts.activity_type,
	}
