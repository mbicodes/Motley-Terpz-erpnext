# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

"""
API endpoints for the Manufacturing Timesheet Kiosk (``/manufacturing-timesheet``).

Flow:
	1. get_employee_board() -> this kiosk's rostered employees (see BOARD_GROUPS),
	   grouped, with their running timer if any. This is the page the kiosk sits on
	   with nobody logged in - allow_guest, no code needed yet.
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
all mandatory now, matching what the kiosk UI enforces client-side. The data URL is
decoded once, here, and stored as a private File attached to the Timesheet; the
Timesheet's Attach Image field then holds that file's URL (see custom_fields.py). So
the photo shows as a picture on the Timesheet and opens by clicking it - nobody has to
copy base64 out of a text box and decode it by hand.

Neither the file nor the Timesheet can be deleted, by anyone: see the two guards in
timesheet_hooks.py. Those guards are what makes the photo permanent - not the storage
shape - because a File is inherently a separate document from the field pointing at it.
"""

import base64
import binascii
import datetime
import re

import frappe
from frappe import _
from frappe.utils import convert_utc_to_timezone, flt, get_datetime

from cannabis_management.manufacturing_timesheet_kiosk.custom_fields import (
	EMPLOYEE_FIELDS,
)

CODE_FIELD = EMPLOYEE_FIELDS[0]["fieldname"]
TOKEN_TTL_SECONDS = 300

# Which employees this kiosk's board shows, and under which heading.
#
# Holding a Kiosk Access Code is what lets someone clock in; it is *not* on its own
# a reason to put their card on this board. This kiosk sits on the Master Touch floor,
# so it lists only the people who clock in here - staff at the other sites keep their
# codes for their own kiosk without cluttering this screen.
#
# Keyed by Employee id, not employee_name: names are editable and not unique, ids are.
# Order here is the order the cards appear in - not alphabetical.
#
# A group with title None renders with no heading of its own; it sits directly under
# the page header (see the <h1> in manufacturing-timesheet.html), which already names
# the site. Give a group a title to break it out under its own heading.
BOARD_GROUPS = [
	{
		"title": None,
		"employees": [
			"HR-EMP-00020",  # Kayley B
			"HR-EMP-00022",  # Conner
			"HR-EMP-00021",  # Israel
			"HR-EMP-00014",  # Tori Sutliff
			"HR-EMP-00007",  # Wolf
			"HR-EMP-00023",  # Leo
			"HR-EMP-00024",  # Brian
		],
	},
	{
		"title": "Hemet Distro",
		"employees": [
			"HR-EMP-00008",  # Manny
			"HR-EMP-00006",  # Sean Carter
		],
	},
]


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
				"attempted_at": _kiosk_now(),
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


#: The plant floor's own timezone. Every ``from_time`` the kiosk writes is a wall
#: clock reading taken here, so every comparison against one has to be made on this
#: same clock. This deliberately does not follow System Settings, whose timezone is
#: America/Adak - two hours behind the plant - which made every running timer read
#: two hours short and pushed freshly entered start times into the future.
#: Correcting System Settings to match is the real fix; until then this keeps the
#: kiosk self-consistent, and it stays correct once that is done too.
KIOSK_TIMEZONE = "America/Los_Angeles"


def _kiosk_now():
	"""Current time on the plant's clock, as a naive datetime."""
	utc_now = datetime.datetime.now(datetime.timezone.utc)
	return convert_utc_to_timezone(utc_now, KIOSK_TIMEZONE).replace(tzinfo=None)


def _elapsed_seconds(from_time, now=None):
	"""Whole seconds between ``from_time`` and now, both on the plant's clock."""
	if not from_time:
		return None
	now = now or _kiosk_now()
	return max(0, int((now - get_datetime(from_time)).total_seconds()))


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
	"""The kiosk's rostered employees, grouped, each with their running timer if any.

	This is what the kiosk shows before anyone has entered a code - one "job card"
	per rostered employee, under its group's heading. Tapping a card is what triggers
	the code prompt (see verify_access_code's `employee` argument), not this call.

	Returns ``[{"title": str | None, "employees": [card, ...]}, ...]`` in BOARD_GROUPS
	order. Only employees named in BOARD_GROUPS appear, and only while they are Active
	with a code set: a card whose owner has no code would be a dead end, since
	verify_access_code could never match it. An empty group is dropped rather than
	rendered as a bare heading.
	"""
	rostered = [employee for group in BOARD_GROUPS for employee in group["employees"]]
	if not rostered:
		return []

	eligible = {
		row.name: row.employee_name
		for row in frappe.get_all(
			"Employee",
			filters={"name": ["in", rostered], "status": "Active", CODE_FIELD: ["is", "set"]},
			fields=["name", "employee_name"],
		)
	}

	# Elapsed is measured here rather than in the browser: the kiosk tablet's own
	# clock and timezone then stop mattering, so a card can no longer read hours out
	# just because the tablet is set to a different zone than System Settings.
	now = _kiosk_now()

	board = []
	for group in BOARD_GROUPS:
		cards = []
		for employee in group["employees"]:
			if employee not in eligible:
				continue
			open_ts = _get_open_timesheet(employee)
			cards.append(
				{
					"employee": employee,
					"employee_name": eligible[employee],
					"running": bool(open_ts),
					"activity_type": open_ts.activity_type if open_ts else None,
					"start_time": open_ts.from_time if open_ts else None,
					"elapsed_seconds": _elapsed_seconds(open_ts.from_time, now) if open_ts else None,
				}
			)
		if cards:
			board.append({"title": group["title"], "employees": cards})

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


# What the page's canvas.toDataURL() produces. Kept strict on purpose: this is a
# guest endpoint, and the only thing that should ever reach it is an image the kiosk
# just captured.
_DATA_URL = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,(?P<payload>[A-Za-z0-9+/=\s]+)$")

# A generous ceiling for one captured frame - the kiosk's own captures run ~55KB at
# 640x480. Not a tuning knob: it is here so a guest cannot post an arbitrarily large
# body and have it land on disk.
MAX_PHOTO_BYTES = 8 * 1024 * 1024


def _store_photo(timesheet, fieldname, data_url, label):
	"""Decode a captured data URL onto disk and return the private file's URL.

	The File is attached to the Timesheet and to `fieldname`, which is what makes it
	show up as the picture in that Attach Image field rather than as a loose
	attachment, and what lets the guard in timesheet_hooks.py recognise it later.

	Private (is_private=1): a verification photo of a worker should not be readable
	by URL alone. Frappe gates private files on read permission for the document they
	are attached to, so this inherits Timesheet's permissions.
	"""
	match = _DATA_URL.match((data_url or "").strip())
	if not match:
		frappe.throw(_("The verification photo was not in a format the kiosk recognises."))

	try:
		content = base64.b64decode(match.group("payload"), validate=False)
	except (binascii.Error, ValueError):
		frappe.throw(_("The verification photo could not be read. Please try again."))

	if not content:
		frappe.throw(_("The verification photo was empty. Please try again."))
	if len(content) > MAX_PHOTO_BYTES:
		frappe.throw(_("The verification photo is too large."))

	extension = "jpg" if match.group(1) in ("jpeg", "jpg") else match.group(1)

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{timesheet}-{label}.{extension}",
			"attached_to_doctype": "Timesheet",
			"attached_to_name": timesheet,
			"attached_to_field": fieldname,
			"is_private": 1,
			"content": content,
		}
	)
	file_doc.insert(ignore_permissions=True)
	return file_doc.file_url


@frappe.whitelist(allow_guest=True)
def start_session(token, activity_type, start_time=None, photo=None):
	employee = _resolve_token(token)

	# Camera, Activity Type and Start Time are all mandatory - none of these are
	# optional extras the kiosk can silently skip.
	if not activity_type:
		frappe.throw(_("Please select an Activity Type"))
	if not photo:
		frappe.throw(_("A verification photo is required to start."))
	# The kiosk sends this already expressed on the site's clock (it converts through
	# System Settings' timezone before filling the picker), so it is stored verbatim.
	start_dt = get_datetime(start_time) if start_time else _kiosk_now()

	if _get_open_timesheet(employee):
		frappe.throw(_("This employee already has an open kiosk session."))

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

	# After the insert, not before: a File has to name the document it is attached to,
	# and the Timesheet has no name until it exists. db_set rather than another save so
	# this writes the one field without re-running validation on a Draft that ERPNext
	# already considers half-finished.
	doc.db_set(
		"custom_start_verification_photo",
		_store_photo(doc.name, "custom_start_verification_photo", photo, "start"),
		update_modified=False,
	)
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
	end_dt = get_datetime(end_time) if end_time else _kiosk_now()

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
	timesheet.custom_end_verification_photo = _store_photo(
		timesheet.name, "custom_end_verification_photo", photo, "end"
	)
	timesheet.save(ignore_permissions=True)
	timesheet.submit()

	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {
		"timesheet": timesheet.name,
		"hours": hours,
		"activity_type": open_ts.activity_type,
	}
