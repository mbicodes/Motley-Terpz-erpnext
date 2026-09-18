# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

"""
API endpoints for the Manufacturing Timesheet Kiosk (``/manufacturing-timesheet``).

Flow:
	1. get_employee_board() -> this kiosk's rostered employees (see SECTION_TITLES
	   and Employee's Kiosk Timesheet/Kiosk Section fields), grouped, with their
	   running timer if any. This is the page the kiosk sits on
	   with nobody logged in - allow_guest, no code needed yet.
	2. Employee taps their own card's Start/End/Request Overtime button -> the page
	   asks for their code -> verify_access_code(access_code, employee) ->
	   {token, employee, employee_name, open_session, overtime_prompt,
	   recent_timesheets}. Passing `employee` (the card that was tapped) makes sure
	   the code that was typed actually belongs to *that* card, not just *some*
	   employee.
	3. start_session(token, activity_type, start_time) -> {name}
	   OR
	   end_session(token, end_time) -> {timesheet, hours}
	   OR
	   submit_overtime_request(token, requested_hours) -> {name}

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
*submit* time (Timesheet.validate_mandatory_fields runs from on_submit, not
validate), so a Draft can sit half-filled indefinitely. Ending the session fills in
to_time/hours and submits it.

No verification photo any more: the camera/face-detection step (capture on
start/end, server-side face check) has been removed from the kiosk end to end - see
the module's git history for the old ``_decode_photo``/face_detect.py-based version.
custom_start_verification_photo/custom_end_verification_photo stay defined on
Timesheet (custom_fields.py) purely so old Timesheets that already carry a photo
keep displaying it; nothing writes to them any more.

8-hour auto-cutoff + overtime requests (new):
	- A scheduled job, auto_end_overtime_sessions() (wired hourly->every minute in
	  hooks.py's cron), force-ends any kiosk session that has been running at least
	  REGULAR_HOURS_PER_SESSION hours - sets to_time to exactly the 8h mark,
	  completes + submits the Timesheet, flags it custom_auto_ended, and emails the
	  employee. It skips any session whose Timesheet already carries
	  custom_overtime_request (see below) - that one is allowed to run long, same
	  as before this feature existed.
	- The board (get_employee_board) and verify_access_code both surface
	  _overtime_prompt(employee): if the employee's most recent Timesheet was
	  auto-ended and they have not yet requested overtime for it, the kiosk shows
	  an alarm + "Request Overtime" prompt in place of their Start button.
	- submit_overtime_request(token, requested_hours) records a Kiosk Overtime
	  Request (Pending) against that Timesheet and emails OVERTIME_RECIPIENTS with
	  one-click Approve/Reject links (decide_overtime_request, guest + a per-request
	  action_token - no login needed to act on the email).
	- Approving starts the overtime session right there and then
	  (_auto_start_overtime_session): the employee does not have to walk back to the
	  kiosk and tap Start, and the new Timesheet's clock is backdated to the moment
	  they submitted the request (_overtime_start_time) rather than the moment the
	  approver got round to the email - they kept working through that wait, so that
	  time is theirs. The new Timesheet carries custom_overtime_request, exempting it
	  from the auto-cutoff, and the request is marked consumed.
	- If auto-start can't run (the employee already has an open session, or the
	  insert fails), the request is left Approved + unconsumed and the old path still
	  works: their next start_session picks it up, links it, marks it consumed, and
	  backdates the same way. end_session's existing 8-hour row-split
	  (custom_overtime, untouched by any of this) takes it from there if that session
	  also runs past 8 hours.

30-minutes-before warning + requesting overtime *before* the cutoff (new):
	- A second scheduled job, send_upcoming_cutoff_warnings() (same every-minute cron
	  as the auto-cutoff above), emails an employee once their still-running session
	  reaches WARNING_LEAD_HOURS before the 8-hour mark, telling them their time is
	  about to end and to request overtime now if they want to keep working - so they
	  find out with enough notice to act, instead of only after being auto-clocked-out.
	  Guarded by custom_overtime_warning_sent so it only fires once per session, and
	  skipped entirely for a session already exempted by custom_overtime_request.
	- submit_overtime_request(token, requested_hours) now covers a still-running
	  session too, not just an already auto-ended one: if the employee has an open
	  session (no request tied to it yet), the request is tied to THAT Timesheet
	  instead of waiting for the 8h auto-cutoff to create one. get_employee_board
	  surfaces this as `early_overtime` on a running card, alongside the End button.
	- decide_overtime_request's Approved branch tells the two shapes apart by
	  re-checking whether the linked Timesheet is still open: if so, the session
	  never stopped, so approval just stamps custom_overtime_request onto it in place
	  (no new Timesheet, no backdating - there was no gap to backdate across) and the
	  employee's email says they're already covered. Otherwise it falls back to the
	  existing _auto_start_overtime_session path for a session that already got cut
	  off before the approval came through.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import convert_utc_to_timezone, flt, format_datetime, get_datetime, get_url

from cannabis_management.manufacturing_timesheet_kiosk.custom_fields import (
	EMPLOYEE_FIELDS,
	TIMESHEET_FIELDS,
)

CODE_FIELD = EMPLOYEE_FIELDS[0]["fieldname"]
TOKEN_TTL_SECONDS = 300

# How long a Pending request keeps showing "awaiting approval" on the board. The
# request itself is untouched in the backend past this point - Muhammad/Jamie's
# email link still works whenever they get to it - this only stops the card
# nagging the employee about it once it's been sitting long enough that it's
# clearly not getting an answer soon.
PENDING_OVERTIME_DISPLAY_SECONDS = 3600

# Timesheet Detail row is split at REGULAR_HOURS_PER_SESSION on manual end (see
# end_session) - untouched by the auto-cutoff feature below, which reads the same
# constant to decide *when* to force-end a still-running session.
REGULAR_HOURS_PER_SESSION = 8.0
OVERTIME_FIELD = "custom_overtime"  # Timesheet Detail (Check) - set on the split row
AUTO_ENDED_FIELD = TIMESHEET_FIELDS[2]["fieldname"]  # custom_auto_ended (Timesheet)
OVERTIME_REQUEST_FIELD = TIMESHEET_FIELDS[3]["fieldname"]  # custom_overtime_request (Timesheet)
WARNING_SENT_FIELD = TIMESHEET_FIELDS[4]["fieldname"]  # custom_overtime_warning_sent (Timesheet)
DECLINED_FIELD = TIMESHEET_FIELDS[5]["fieldname"]  # custom_overtime_declined (Timesheet)
SILENCED_FIELD = TIMESHEET_FIELDS[6]["fieldname"]  # custom_overtime_alarm_silenced (Timesheet)

# How long before the 8-hour auto-cutoff send_upcoming_cutoff_warnings() emails the
# employee - see that function below.
WARNING_LEAD_HOURS = 0.5

# Who gets emailed when an employee requests overtime, and who their approval/
# rejection email credits as "Decided By" (each gets their own Approve/Reject
# links in a separately-sent copy of the request email - see
# _send_overtime_request_email - purely so the audit trail on the request records
# which of the two actually clicked, not just "someone with the link").
OVERTIME_RECIPIENTS = [
	{"email": "mbi@alltechvirtual.com", "label": "Muhammad"},
	{"email": "jamie@motleyterpz.com", "label": "Jamie"},
]

# Which board heading each Kiosk Section (Employee's custom_kiosk_section, see
# custom_fields.py) renders under, in board order. Who's on the board at all is set
# entirely from the Employee form now - Active, a Kiosk Access Code, Kiosk Timesheet
# checked, and one of these picked for Kiosk Section - not from a list in this file,
# so adding/removing a card never needs a code change or a restart.
#
# "Master Touch Manufacturing" renders with no heading of its own; those cards sit
# directly under the page header (see the <h1> in manufacturing-timesheet.html),
# which already names the site. Every other section breaks out under its own name.
SECTION_TITLES = {
	"Master Touch Manufacturing": None,
	"Hemet Distro": "Hemet Distro",
}


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

	Returns a dict with the Timesheet name plus that row's activity_type/from_time/
	overtime_request, or None. Kiosk-started Timesheets only ever carry one open row,
	but this also recognises a Timesheet started from Desk (Start Timer) so the two
	never disagree.
	"""
	row = frappe.db.sql(
		f"""
		select ts.name as timesheet, tsd.name as row_name, tsd.activity_type, tsd.from_time,
			ts.{OVERTIME_REQUEST_FIELD} as overtime_request
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


def _kiosk_roster():
	"""Every employee this kiosk covers, with the section their card belongs in:
	Active, a Kiosk Access Code set, Kiosk Timesheet checked, and a Kiosk Section
	chosen (unchecked or section-less employees don't get a card - see
	custom_fields.py's note on the blank section option). One query shared by
	_eligible_employees (auto-cutoff cron) and get_employee_board so both agree on
	exactly who this kiosk covers."""
	return frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			CODE_FIELD: ["is", "set"],
			"custom_kiosk_timesheet": 1,
			"custom_kiosk_section": ["in", list(SECTION_TITLES.keys())],
		},
		fields=["name", "employee_name", "custom_kiosk_section"],
		order_by="employee_name asc",
	)


def _eligible_employees():
	"""Kiosk-eligible employees, keyed by id -> employee_name. Shared by
	get_employee_board and the auto-cutoff cron so both agree on exactly who this
	kiosk covers."""
	return {row.name: row.employee_name for row in _kiosk_roster()}


def _overtime_prompt(employee):
	"""What (if anything) the board/code-entry screen should show this employee
	about overtime, based on their most recent *submitted* Timesheet:

	- None: nothing to show (last Timesheet was a normal manual end, or there
	  isn't one yet, or they're currently running again).
	- {"state": "needs_request", "silenced": bool, ...}: their last session was
	  auto-ended at 8h and they have not requested overtime for it (or a prior
	  request was Rejected) - the board should alarm (unless silenced - see
	  silence_overtime_alarm) + show "Request Overtime"/"End" in place of Start.
	- {"state": "pending", ...}: a request is in for it, awaiting Muhammad/Jamie.
	- {"state": "approved", ...}: approved and not yet used by a new session -
	  informational hint only; start_session is what actually applies it.
	- None also once the employee has tapped End on this same session instead of
	  Request Overtime (see decline_overtime_request) - unlike a Rejected request,
	  this is the employee's own final word, so it stays resolved for good rather
	  than re-inviting another request.
	"""
	if _get_open_timesheet(employee):
		# Running again already (e.g. the exempt overtime session itself) - no
		# prompt makes sense while that's in progress.
		return None

	last_ts = frappe.db.get_value(
		"Timesheet",
		{"employee": employee, "docstatus": 1},
		["name", AUTO_ENDED_FIELD, DECLINED_FIELD, SILENCED_FIELD],
		order_by="creation desc",
		as_dict=True,
	)
	if not last_ts or not last_ts.get(AUTO_ENDED_FIELD) or last_ts.get(DECLINED_FIELD):
		return None

	req = frappe.db.get_value(
		"Kiosk Overtime Request",
		{"employee": employee, "timesheet": last_ts.name},
		["name", "status", "requested_hours", "consumed", "requested_at"],
		order_by="creation desc",
		as_dict=True,
	)
	if not req or req.status == "Rejected":
		return {
			"state": "needs_request",
			"timesheet": last_ts.name,
			"hours": REGULAR_HOURS_PER_SESSION,
			"silenced": bool(last_ts.get(SILENCED_FIELD)),
		}
	if req.status == "Pending":
		if req.requested_at and _elapsed_seconds(req.requested_at) >= PENDING_OVERTIME_DISPLAY_SECONDS:
			return None
		return {
			"state": "pending",
			"timesheet": last_ts.name,
			"requested_hours": req.requested_hours,
			"requested_at": str(req.requested_at) if req.requested_at else None,
		}
	if req.status == "Approved" and not req.consumed:
		# requested_at rides along so the start screen can show - and pre-fill - the
		# backdated clock-in the session will actually get (see _overtime_start_time).
		return {
			"state": "approved",
			"timesheet": last_ts.name,
			"requested_hours": req.requested_hours,
			"requested_at": str(_overtime_start_time(req)) if req.requested_at else None,
		}
	return None


def _early_overtime_state(employee, open_ts):
	"""Whether a *still-running* kiosk session can ask for overtime before the 8-hour
	auto-cutoff ever reaches it - shown on a running job card as a secondary "Request
	Overtime" option next to End. None once the session is already exempted
	(custom_overtime_request already set - nothing left to ask for) or once a request
	for THIS session is already Approved (decide_overtime_request stamps the exemption
	straight onto the Timesheet the moment that happens, so this state is never seen
	after that - the card just shows a normal running session again)."""
	if not open_ts or open_ts.overtime_request:
		return None

	req = frappe.db.get_value(
		"Kiosk Overtime Request",
		{"employee": employee, "timesheet": open_ts.timesheet},
		["status", "requested_hours"],
		order_by="creation desc",
		as_dict=True,
	)
	if not req or req.status == "Rejected":
		return {"state": "available"}
	if req.status == "Pending":
		return {"state": "pending", "requested_hours": req.requested_hours}
	return None


@frappe.whitelist(allow_guest=True)
def get_employee_board():
	"""The kiosk's rostered employees, grouped, each with their running timer (and
	any overtime prompt) if any.

	This is what the kiosk shows before anyone has entered a code - one "job card"
	per rostered employee, under its group's heading. Tapping a card is what triggers
	the code prompt (see verify_access_code's `employee` argument), not this call.

	Returns ``[{"title": str | None, "employees": [card, ...]}, ...]`` in
	SECTION_TITLES order. Only employees opted in via the Employee form appear (see
	_kiosk_roster) - a card whose owner has no code would be a dead end, since
	verify_access_code could never match it. An empty section is dropped rather than
	rendered as a bare heading.
	"""
	roster = _kiosk_roster()
	if not roster:
		return []

	# Elapsed is measured here rather than in the browser: the kiosk tablet's own
	# clock and timezone then stop mattering, so a card can no longer read hours out
	# just because the tablet is set to a different zone than System Settings.
	now = _kiosk_now()

	by_section = {}
	for row in roster:
		by_section.setdefault(row.custom_kiosk_section, []).append(row)

	board = []
	for section, title in SECTION_TITLES.items():
		cards = []
		for row in by_section.get(section, []):
			employee = row.name
			open_ts = _get_open_timesheet(employee)
			cards.append(
				{
					"employee": employee,
					"employee_name": row.employee_name,
					"running": bool(open_ts),
					"activity_type": open_ts.activity_type if open_ts else None,
					"start_time": open_ts.from_time if open_ts else None,
					"elapsed_seconds": _elapsed_seconds(open_ts.from_time, now) if open_ts else None,
					"is_overtime_session": bool(open_ts and open_ts.overtime_request) if open_ts else False,
					"overtime": None if open_ts else _overtime_prompt(employee),
					"early_overtime": _early_overtime_state(employee, open_ts) if open_ts else None,
				}
			)
		if cards:
			board.append({"title": title, "employees": cards})

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
		"overtime_prompt": None if open_ts else _overtime_prompt(matched.name),
		"recent_timesheets": _get_recent_timesheets(matched.name),
	}


def _overtime_start_time(req, now=None):
	"""Where an approved-overtime session's clock starts: the moment the employee
	submitted the request, not the moment approval came through or the moment they
	got back to the kiosk. They carried on working through that wait, so that time
	is theirs.

	Clamped at both ends, because a backdate that lands in the wrong place would
	produce a Timesheet that cannot be saved at all:
	  - never before the end of the auto-ended session the request belongs to,
	    which would overlap it and trip Timesheet's own validate_overlap_for;
	  - never into the future, in case a clock somewhere is off.
	"""
	now = now or _kiosk_now()
	start = get_datetime(req.get("requested_at"))

	timesheet = req.get("timesheet")
	if timesheet:
		last_row = frappe.get_all(
			"Timesheet Detail",
			filters={"parent": timesheet, "parenttype": "Timesheet"},
			fields=["to_time"],
			order_by="to_time desc",
			limit=1,
		)
		if last_row and last_row[0].to_time:
			prev_end = get_datetime(last_row[0].to_time)
			if start < prev_end:
				# One second clear of the previous row, so the two never touch.
				start = prev_end + datetime.timedelta(seconds=1)

	return min(start, now)


def _auto_start_overtime_session(req):
	"""Opens the overtime session the moment the request is approved, so the
	employee doesn't have to come back to the kiosk and tap Start to have their
	clock running. Continues whatever activity the auto-ended session was on, since
	this is the same work carrying past 8 hours.

	Returns the new Timesheet's name, or None when auto-start doesn't apply - an
	employee who is already running keeps their open session, and the request simply
	stays Approved + unconsumed for start_session to pick up as before.
	"""
	if _get_open_timesheet(req.employee):
		return None

	activity_type = None
	if req.timesheet:
		last_row = frappe.get_all(
			"Timesheet Detail",
			filters={"parent": req.timesheet, "parenttype": "Timesheet"},
			fields=["activity_type"],
			order_by="to_time desc",
			limit=1,
		)
		if last_row:
			activity_type = last_row[0].activity_type
	if not activity_type:
		return None

	start_dt = _overtime_start_time(req)

	# Same Draft/placeholder shape start_session builds - see the long note there on
	# why to_time is seeded with from_time rather than left null.
	doc = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": req.employee,
			"company": frappe.db.get_value("Employee", req.employee, "company"),
			OVERTIME_REQUEST_FIELD: req.name,
			"time_logs": [
				{
					"activity_type": activity_type,
					"from_time": start_dt,
					"to_time": start_dt,
					"completed": 0,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.set_value("Kiosk Overtime Request", req.name, "consumed", 1)

	return doc.name


@frappe.whitelist(allow_guest=True)
def start_session(token, activity_type, start_time=None):
	employee = _resolve_token(token)

	if not activity_type:
		frappe.throw(_("Please select an Activity Type"))

	# The kiosk sends this already expressed on the site's clock (it converts through
	# System Settings' timezone before filling the picker), so it is stored verbatim.
	start_dt = get_datetime(start_time) if start_time else _kiosk_now()

	if _get_open_timesheet(employee):
		frappe.throw(_("This employee already has an open kiosk session."))

	company = frappe.db.get_value("Employee", employee, "company")

	# An Approved, not-yet-used overtime request exempts *this* session from the
	# 8-hour auto-cutoff (auto_end_overtime_sessions skips any Timesheet carrying
	# OVERTIME_REQUEST_FIELD) - picked up and marked consumed right away so a second
	# new session started later can't also claim the same approval.
	overtime_req = frappe.db.get_value(
		"Kiosk Overtime Request",
		{"employee": employee, "status": "Approved", "consumed": 0},
		["name", "timesheet", "requested_at"],
		order_by="modified desc",
		as_dict=True,
	)
	overtime_request = overtime_req.name if overtime_req else None

	# An approved request's session is clocked from when it was asked for, whatever
	# the kiosk sent up - the picker only ever offers "now", and taking it would quietly
	# drop the hours worked between the request and this tap. Normally auto-start has
	# already opened this session at approval time and we never get here; this covers
	# the cases where it couldn't (see _auto_start_overtime_session).
	if overtime_req and overtime_req.requested_at:
		start_dt = _overtime_start_time(overtime_req)

	# Draft, one incomplete row - the same shape Desk's "Start Timer" leaves behind
	# (see erpnext/public/js/projects/timer.js), *including* to_time = from_time as
	# a placeholder. That last part matters, not just cosmetic: Timesheet's own
	# overlap check (validate_overlap_for in timesheet.py) reads a null to_time via
	# get_datetime(None), which returns *now* rather than "open-ended" - so a truly
	# empty to_time gets compared as if the row already ran from from_time to this
	# instant, and can spuriously collide with an earlier session of this same
	# employee's from earlier today (exactly the case this feature introduces: an
	# 8h-auto-ended session, then a second approved-overtime one later the same
	# day). Mirroring Desk's own placeholder avoids that false OverlapError.
	# The site's Timesheet after_insert hook will try to auto-submit this and fail
	# (hours is 0 until the row is completed); that failure is caught there and only
	# logs/msgprints, so the insert itself is unaffected and the Timesheet stays Draft.
	doc = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": employee,
			"company": company,
			OVERTIME_REQUEST_FIELD: overtime_request,
			"time_logs": [
				{
					"activity_type": activity_type,
					"from_time": start_dt,
					"to_time": start_dt,
					"completed": 0,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)

	if overtime_request:
		frappe.db.set_value("Kiosk Overtime Request", overtime_request, "consumed", 1)

	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {"name": doc.name, "activity_type": activity_type, "start_time": start_dt}


@frappe.whitelist(allow_guest=True)
def end_session(token, end_time=None):
	employee = _resolve_token(token)

	open_ts = _get_open_timesheet(employee)
	if not open_ts:
		frappe.throw(_("No open kiosk session found for this employee."))

	start_dt = get_datetime(open_ts.from_time)
	end_dt = get_datetime(end_time) if end_time else _kiosk_now()

	if end_dt <= start_dt:
		frappe.throw(_("End time must be after the start time."))

	# Rounded to the nearest hundredth of an hour (~36 seconds) for the kiosk
	# receipt/display. Each Timesheet Detail row's own `hours` is recalculated by
	# ERPNext's own Timesheet.calculate_hours() from from_time/to_time (same formula
	# used everywhere else in ERPNext) when the doc is saved below, so the two stay
	# consistent - that's true of both rows below, not just a single one.
	hours = flt((end_dt - start_dt).total_seconds() / 3600.0, 2)

	timesheet = frappe.get_doc("Timesheet", open_ts.timesheet)
	row = timesheet.get("time_logs", {"name": open_ts.row_name})[0]
	row.completed = 1

	if hours > REGULAR_HOURS_PER_SESSION:
		# Split automatically at the REGULAR_HOURS_PER_SESSION mark: this row keeps
		# the regular hours, and a second row - appended here, Overtime checked -
		# picks up everything past it. No separate action for anyone to take; the
		# employee just taps End same as always. In practice this only fires for an
		# overtime-exempt session (see start_session/OVERTIME_REQUEST_FIELD) - a
		# normal session never gets here because auto_end_overtime_sessions force-
		# ends it at the 8h mark first.
		split_at = start_dt + datetime.timedelta(hours=REGULAR_HOURS_PER_SESSION)
		row.to_time = split_at
		timesheet.append(
			"time_logs",
			{
				"activity_type": open_ts.activity_type,
				"from_time": split_at,
				"to_time": end_dt,
				"completed": 1,
				OVERTIME_FIELD: 1,
			},
		)
	else:
		row.to_time = end_dt

	timesheet.save(ignore_permissions=True)
	timesheet.submit()

	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {
		"timesheet": timesheet.name,
		"hours": hours,
		"activity_type": open_ts.activity_type,
	}


# ── 8-hour auto-cutoff (scheduled) ───────────────────────────────────────────────


def auto_end_overtime_sessions():
	"""Scheduled every minute (see hooks.py's cron). Force-ends any kiosk session
	that has been running at least REGULAR_HOURS_PER_SESSION hours, skipping any
	Timesheet already exempted by an approved overtime request (OVERTIME_REQUEST_FIELD
	- see start_session). Does *not* touch the overtime-request loop itself - that
	only starts once the employee taps Request Overtime on the board.
	"""
	eligible = _eligible_employees()
	if not eligible:
		return

	cutoff = _kiosk_now() - datetime.timedelta(hours=REGULAR_HOURS_PER_SESSION)
	placeholders = ", ".join(["%s"] * len(eligible))

	rows = frappe.db.sql(
		f"""
		select ts.name as timesheet, ts.employee, tsd.name as row_name, tsd.from_time
		from `tabTimesheet Detail` tsd
		inner join `tabTimesheet` ts on ts.name = tsd.parent
		where ts.docstatus = 0
			and tsd.from_time is not null
			and tsd.completed = 0
			and tsd.from_time <= %s
			and ts.employee in ({placeholders})
			and (ts.{OVERTIME_REQUEST_FIELD} is null or ts.{OVERTIME_REQUEST_FIELD} = '')
		""",
		[cutoff, *eligible.keys()],
		as_dict=True,
	)

	for row in rows:
		_force_end_session(row)


def _force_end_session(row):
	"""Force-end one open Timesheet Detail row at exactly the 8-hour mark - same
	shape as a normal end_session, minus any input from the employee - then email
	them. Any failure here must not crash the scheduler tick for the rest of `rows`,
	so it's caught, logged, and skipped; the next tick (a minute later) retries it."""
	try:
		timesheet = frappe.get_doc("Timesheet", row.timesheet)
		time_row = timesheet.get("time_logs", {"name": row.row_name})[0]
		time_row.completed = 1
		time_row.to_time = get_datetime(row.from_time) + datetime.timedelta(hours=REGULAR_HOURS_PER_SESSION)
		timesheet.set(AUTO_ENDED_FIELD, 1)
		timesheet.save(ignore_permissions=True)
		timesheet.submit()
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Kiosk auto-end failed", message=frappe.get_traceback())
		return

	_send_hours_complete_email(row.employee, timesheet.name)


def send_upcoming_cutoff_warnings():
	"""Scheduled every minute (see hooks.py's cron), alongside auto_end_overtime_sessions:
	emails an employee once their still-running session is WARNING_LEAD_HOURS away from
	the 8-hour auto-cutoff, so they find out with enough notice to request overtime
	before it happens rather than only after being force-clocked-out.

	Skips exactly what auto_end_overtime_sessions itself skips (already exempted by an
	approved overtime request), plus anyone already warned for this same session
	(WARNING_SENT_FIELD) so this doesn't re-send on every later tick up to the cutoff.
	"""
	eligible = _eligible_employees()
	if not eligible:
		return

	now = _kiosk_now()
	warn_at = now - datetime.timedelta(hours=REGULAR_HOURS_PER_SESSION - WARNING_LEAD_HOURS)
	cutoff = now - datetime.timedelta(hours=REGULAR_HOURS_PER_SESSION)
	placeholders = ", ".join(["%s"] * len(eligible))

	rows = frappe.db.sql(
		f"""
		select ts.name as timesheet, ts.employee, tsd.from_time
		from `tabTimesheet Detail` tsd
		inner join `tabTimesheet` ts on ts.name = tsd.parent
		where ts.docstatus = 0
			and tsd.from_time is not null
			and tsd.completed = 0
			and tsd.from_time <= %s
			and tsd.from_time > %s
			and ts.employee in ({placeholders})
			and (ts.{OVERTIME_REQUEST_FIELD} is null or ts.{OVERTIME_REQUEST_FIELD} = '')
			and (ts.{WARNING_SENT_FIELD} is null or ts.{WARNING_SENT_FIELD} = 0)
		""",
		[warn_at, cutoff, *eligible.keys()],
		as_dict=True,
	)

	for row in rows:
		try:
			frappe.db.set_value("Timesheet", row.timesheet, WARNING_SENT_FIELD, 1)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title="Kiosk overtime warning flag failed", message=frappe.get_traceback())
			continue

		cutoff_time = get_datetime(row.from_time) + datetime.timedelta(hours=REGULAR_HOURS_PER_SESSION)
		_send_upcoming_cutoff_email(row.employee, row.timesheet, cutoff_time)


# ── Overtime requests ────────────────────────────────────────────────────────────


@frappe.whitelist(allow_guest=True)
def submit_overtime_request(token, requested_hours):
	employee = _resolve_token(token)
	requested_hours = flt(requested_hours)
	if requested_hours <= 0:
		frappe.throw(_("Please enter how many hours of overtime you'd like to request."))
	if requested_hours > 16:
		frappe.throw(_("That's more overtime than one request can cover - please enter a smaller number."))

	# A still-running session ties the request straight to its own (open) Timesheet,
	# so an approval can just exempt it in place - see decide_overtime_request. Only
	# once that session is over (or never existed) does this fall back to the older
	# post-8h-cutoff path, tied to the last auto-ended Timesheet instead.
	open_ts = _get_open_timesheet(employee)
	if open_ts:
		if open_ts.overtime_request:
			frappe.throw(_("This session is already cleared to run long - no request needed."))
		timesheet = open_ts.timesheet
		existing = frappe.db.exists(
			"Kiosk Overtime Request",
			{"employee": employee, "timesheet": timesheet, "status": ["in", ["Pending", "Approved"]]},
		)
		if existing:
			frappe.throw(_("A request for this session has already been sent."))
	else:
		prompt = _overtime_prompt(employee)
		if not prompt or prompt["state"] != "needs_request":
			frappe.throw(_("There is no overtime request needed for this employee right now."))
		timesheet = prompt["timesheet"]

	employee_name = frappe.db.get_value("Employee", employee, "employee_name")

	doc = frappe.get_doc(
		{
			"doctype": "Kiosk Overtime Request",
			"employee": employee,
			"employee_name": employee_name,
			"timesheet": timesheet,
			"requested_hours": requested_hours,
			"status": "Pending",
			"requested_at": _kiosk_now(),
			"action_token": frappe.generate_hash(length=32),
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	_send_overtime_request_email(doc)

	return {"name": doc.name}


@frappe.whitelist(allow_guest=True)
def decline_overtime_request(token):
	"""Employee taps End (instead of Request Overtime) on a card that's alarming for
	an auto-ended session: they're done for the day, no overtime wanted. Permanently
	resolves _overtime_prompt's needs_request state for that Timesheet - see
	DECLINED_FIELD - so the board stops alarming and offering Request Overtime for it,
	without filing a Kiosk Overtime Request at all."""
	employee = _resolve_token(token)

	prompt = _overtime_prompt(employee)
	if not prompt or prompt["state"] != "needs_request":
		frappe.throw(_("There is nothing to end right now."))

	frappe.db.set_value("Timesheet", prompt["timesheet"], DECLINED_FIELD, 1)
	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {"timesheet": prompt["timesheet"]}


@frappe.whitelist(allow_guest=True)
def silence_overtime_alarm(employee):
	"""Stops the siren for this employee's needs-overtime card on every kiosk board -
	not just the tablet that tapped it. Server-side on purpose (SILENCED_FIELD on the
	Timesheet, read back by every board's get_employee_board poll) rather than the
	old per-browser localStorage version, which only silenced the one tablet clicked.

	Deliberately guest + no access-code token, same as this button already was before
	it made a server call at all: this only mutes a notification sound, it doesn't
	touch the overtime decision itself - Request Overtime/End stay exactly as
	available as before, gated by their own token as always. Anyone standing at a
	blaring kiosk should be able to quiet it without knowing that employee's PIN."""
	prompt = _overtime_prompt(employee)
	if not prompt or prompt["state"] != "needs_request":
		frappe.throw(_("There is no alarm to stop right now."))

	frappe.db.set_value("Timesheet", prompt["timesheet"], SILENCED_FIELD, 1)
	frappe.db.commit()

	return {"timesheet": prompt["timesheet"]}


@frappe.whitelist(allow_guest=True)
def decide_overtime_request(request, token, decision, by=None):
	"""Landed on directly from the Approve/Reject links in the request email - a
	guest endpoint on purpose (Muhammad/Jamie shouldn't need to log into Desk from
	their phone to act on it), gated by the per-request action_token instead of a
	session. Returns a plain confirmation page, not JSON, since a browser opens
	this straight from the email."""
	decision = (decision or "").strip().capitalize()
	if decision not in ("Approved", "Rejected"):
		frappe.throw(_("Invalid decision"))

	doc = frappe.get_doc("Kiosk Overtime Request", request)

	if not token or doc.action_token != token:
		frappe.respond_as_web_page(
			_("Link not valid"),
			_("This approval link is not valid."),
			indicator_color="red",
		)
		return

	if doc.status != "Pending":
		frappe.respond_as_web_page(
			_("Already decided"),
			_("{0}'s overtime request was already marked {1}.").format(doc.employee_name, doc.status),
			indicator_color="blue",
		)
		return

	doc.status = decision
	doc.decided_by = by or "Unknown"
	doc.decided_at = _kiosk_now()
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	started_timesheet = None
	still_running = False
	if decision == "Approved":
		# Tell the two shapes of request apart: one made *before* the 8h cutoff, whose
		# Timesheet never stopped running, vs one made after auto-end created a fresh
		# Timesheet to backdate into existence. The first just needs the exemption
		# stamped onto the session that's already ticking - there's no gap to
		# backdate across and nothing to auto-start.
		open_row = _get_open_timesheet(doc.employee)
		still_running = bool(open_row and open_row.timesheet == doc.timesheet)

		if still_running:
			frappe.db.set_value("Timesheet", doc.timesheet, OVERTIME_REQUEST_FIELD, doc.name)
			frappe.db.set_value("Kiosk Overtime Request", doc.name, "consumed", 1)
			frappe.db.commit()
		else:
			# The approval itself puts them back on the clock. Never at the cost of the
			# decision: if this fails the request stays Approved + unconsumed and their
			# next Start picks it up, so the worst case is the old behaviour.
			try:
				started_timesheet = _auto_start_overtime_session(doc)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback()
				started_timesheet = None
				frappe.log_error(
					title="Kiosk overtime auto-start failed",
					message=frappe.get_traceback(),
				)

		_send_overtime_decision_email(doc, started_timesheet, still_running=still_running)

	message = _("{0}'s request for {1} hour(s) of overtime has been {2}.").format(
		doc.employee_name, doc.requested_hours, decision.lower()
	)
	if still_running:
		message += " " + _("Their timer is already running - they can keep working uninterrupted.")
	elif started_timesheet:
		message += " " + _("Their timer is running from {0}, when they asked.").format(
			format_datetime(_overtime_start_time(doc), "d MMM, h:mm a")
		)

	frappe.respond_as_web_page(
		_("Overtime request {0}").format(decision.lower()),
		message,
		indicator_color="green" if decision == "Approved" else "orange",
	)


# ── Email ─────────────────────────────────────────────────────────────────────────


def _employee_email(employee):
	row = frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "user_id", "personal_email", "company_email", "prefered_email"],
		as_dict=True,
	)
	if not row:
		return None, None
	return (row.user_id or row.personal_email or row.company_email or row.prefered_email), row.employee_name


_EMAIL_WRAP = """<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;color:#0f172a;margin:0;padding:20px;">
<div style="max-width:520px;margin:0 auto;">
  <div style="background:{gradient};border-radius:14px;padding:24px 30px;margin-bottom:16px;text-align:center;">
    <div style="font-size:20px;font-weight:800;color:#fff;">{heading}</div>
    <div style="color:rgba(255,255,255,.85);font-size:13px;margin-top:6px;">Master Touch Manufacturing · Timesheet Kiosk</div>
  </div>
  <div style="background:#fff;border-radius:10px;padding:20px 22px;border:1px solid #e2e8f0;font-size:14px;line-height:1.6;color:#334155;">
    {body}
  </div>
  <div style="text-align:center;color:#94a3b8;font-size:11px;margin-top:16px;">Automated message from the Manufacturing Timesheet Kiosk · Do not reply.</div>
</div></body></html>"""


def _send_hours_complete_email(employee, timesheet_name):
	email, employee_name = _employee_email(employee)
	if not email:
		frappe.log_error(
			title="Kiosk: no email on file for auto-ended employee",
			message=f"employee={employee} timesheet={timesheet_name}",
		)
		return

	body = f"""
	<p>Hi {employee_name},</p>
	<p>You've hit your <b>8 hours</b> for today, so the kiosk has clocked you out automatically
	   (Timesheet <b>{timesheet_name}</b>).</p>
	<p style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px 14px;color:#9a3412;">
	   Want to keep working? Tap your card on the kiosk board and choose
	   <b>Request Overtime</b> to ask for more time.</p>
	<p>Thanks for a solid shift!</p>
	"""
	html = _EMAIL_WRAP.format(
		gradient="linear-gradient(135deg,#1e293b,#334155)",
		heading="Your 8 Hours Are Complete",
		body=body,
	)
	try:
		frappe.sendmail(recipients=[email], subject="Your 8 hours are complete", message=html, delayed=False)
	except Exception:
		frappe.log_error(title="Kiosk hours-complete email failed", message=frappe.get_traceback())


def _send_upcoming_cutoff_email(employee, timesheet_name, cutoff_time):
	"""The 30-minutes-before warning (see send_upcoming_cutoff_warnings). Unlike the
	hours-complete email above, nothing has happened to the session yet - it's still
	running - so this is purely a heads-up with time left to act, not a notice of
	something already done."""
	email, employee_name = _employee_email(employee)
	if not email:
		frappe.log_error(
			title="Kiosk: no email on file for employee nearing 8h cutoff",
			message=f"employee={employee} timesheet={timesheet_name}",
		)
		return

	cutoff_str = format_datetime(cutoff_time, "h:mm a")
	body = f"""
	<p>Hi {employee_name},</p>
	<p>Heads up - your <b>8 hours</b> for today will be up around <b>{cutoff_str}</b>,
	   about {int(WARNING_LEAD_HOURS * 60)} minutes from now.</p>
	<p style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px 14px;color:#9a3412;">
	   Want to keep working past that? Tap your card on the kiosk board now and choose
	   <b>Request Overtime</b> - do it before your time runs out so you're not clocked
	   out in the middle of the day.</p>
	<p>If you're happy to stop at 8 hours, there's nothing you need to do.</p>
	"""
	html = _EMAIL_WRAP.format(
		gradient="linear-gradient(135deg,#78350f,#b45309)",
		heading="Your Time Is Almost Up",
		body=body,
	)
	try:
		frappe.sendmail(
			recipients=[email],
			subject="Your 8 hours end in 30 minutes - request overtime now if you need it",
			message=html,
			delayed=False,
		)
	except Exception:
		frappe.log_error(title="Kiosk upcoming-cutoff email failed", message=frappe.get_traceback())


def _send_overtime_request_email(doc):
	base_url = get_url()
	for person in OVERTIME_RECIPIENTS:
		approve_url = (
			f"{base_url}/kiosk-api/decide_overtime_request"
			f"?request={doc.name}&token={doc.action_token}&decision=Approved&by={person['email']}"
		)
		reject_url = (
			f"{base_url}/kiosk-api/decide_overtime_request"
			f"?request={doc.name}&token={doc.action_token}&decision=Rejected&by={person['email']}"
		)
		body = f"""
		<p>Hi {person['label']},</p>
		<p><b>{doc.employee_name}</b> has already worked 8 hours today and is requesting
		   <b>{doc.requested_hours} hour(s)</b> of overtime.</p>
		<p style="text-align:center;margin:24px 0;">
		  <a href="{approve_url}" style="display:inline-block;background:#16a34a;color:#fff;text-decoration:none;
		     font-weight:700;padding:12px 26px;border-radius:8px;margin:0 6px;">Approve</a>
		  <a href="{reject_url}" style="display:inline-block;background:#dc2626;color:#fff;text-decoration:none;
		     font-weight:700;padding:12px 26px;border-radius:8px;margin:0 6px;">Reject</a>
		</p>
		<p style="color:#64748b;font-size:12.5px;">One tap, no login needed. Timesheet: {doc.timesheet}</p>
		"""
		html = _EMAIL_WRAP.format(
			gradient="linear-gradient(135deg,#7c2d12,#c2410c)",
			heading="Overtime Request",
			body=body,
		)
		try:
			frappe.sendmail(
				recipients=[person["email"]],
				subject=f"Overtime request — {doc.employee_name} ({doc.requested_hours}h)",
				message=html,
				delayed=False,
			)
		except Exception:
			frappe.log_error(title="Kiosk overtime request email failed", message=frappe.get_traceback())


def _send_overtime_decision_email(doc, started_timesheet=None, still_running=False):
	email, employee_name = _employee_email(doc.employee)
	if not email:
		return

	if still_running:
		# Asked before the cutoff and it never actually happened - there's no gap to
		# backdate across or new session to start, the one they're already on just
		# got cleared to keep going.
		next_step = (
			"<p>You're already covered - your current session is cleared to keep running "
			"past 8 hours. Nothing else to do; just tap <b>End</b> on the kiosk when you "
			"finish.</p>"
		)
	elif started_timesheet:
		started_from = format_datetime(_overtime_start_time(doc), "d MMM, h:mm a")
		next_step = (
			f"<p>Your timer is <b>already running</b> - it was started for you from "
			f"<b>{started_from}</b>, when you sent the request, so the time you worked "
			f"while waiting counts. Just tap <b>End</b> on the kiosk when you finish.</p>"
		)
	else:
		next_step = (
			f"<p>You can work up to {doc.requested_hours} extra hour(s) next time you clock in - "
			f"just tap <b>Start</b> on the kiosk board as usual.</p>"
		)

	body = f"""
	<p>Hi {employee_name},</p>
	<p style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 14px;color:#166534;">
	   Your overtime request has been <b>approved</b> for <b>{doc.requested_hours} hour(s)</b>.</p>
	{next_step}
	"""
	html = _EMAIL_WRAP.format(
		gradient="linear-gradient(135deg,#14532d,#16a34a)",
		heading="Overtime Approved",
		body=body,
	)
	try:
		frappe.sendmail(recipients=[email], subject="Your overtime request was approved", message=html, delayed=False)
	except Exception:
		frappe.log_error(title="Kiosk overtime decision email failed", message=frappe.get_traceback())
