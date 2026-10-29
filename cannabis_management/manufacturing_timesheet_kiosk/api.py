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

PENDING_OVERTIME_DISPLAY_SECONDS = 3600

REGULAR_HOURS_PER_SESSION = 8.0
OVERTIME_FIELD = "custom_overtime"
AUTO_ENDED_FIELD = TIMESHEET_FIELDS[2]["fieldname"]
OVERTIME_REQUEST_FIELD = TIMESHEET_FIELDS[3]["fieldname"]
WARNING_SENT_FIELD = TIMESHEET_FIELDS[4]["fieldname"]
DECLINED_FIELD = TIMESHEET_FIELDS[5]["fieldname"]
SILENCED_FIELD = TIMESHEET_FIELDS[6]["fieldname"]


def _installed_timesheet_fields(*fieldnames):
	return [f for f in fieldnames if frappe.db.has_column("Timesheet", f)]

WARNING_LEAD_HOURS = 0.5

OVERTIME_RECIPIENTS = [
	{"email": "mbi@alltechvirtual.com", "label": "Muhammad"},
	{"email": "jamie@motleyterpz.com", "label": "Jamie"},
]

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
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="Kiosk Access Log Failed")


def _make_token(employee):
	token = frappe.generate_hash(length=32)
	frappe.cache().set_value(f"kiosk_token:{token}", employee, expires_in_sec=TOKEN_TTL_SECONDS)
	return token


def _resolve_token(token):
	if not token:
		frappe.throw(_("Missing kiosk session token"))

	employee = frappe.cache().get_value(f"kiosk_token:{token}")
	if not employee:
		frappe.throw(_("Your session has expired. Please enter your access code again."))

	return employee

KIOSK_TIMEZONE = "America/Los_Angeles"


def _kiosk_now():
	utc_now = datetime.datetime.now(datetime.timezone.utc)
	return convert_utc_to_timezone(utc_now, KIOSK_TIMEZONE).replace(tzinfo=None)


def _elapsed_seconds(from_time, now=None):
	if not from_time:
		return None
	now = now or _kiosk_now()
	return max(0, int((now - get_datetime(from_time)).total_seconds()))


def _get_open_timesheet(employee):
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
	return {row.name: row.employee_name for row in _kiosk_roster()}


def _overtime_prompt(employee):
	if _get_open_timesheet(employee):
		return None

	last_ts = frappe.db.get_value(
		"Timesheet",
		{"employee": employee, "docstatus": 1},
		["name"] + _installed_timesheet_fields(AUTO_ENDED_FIELD, DECLINED_FIELD, SILENCED_FIELD),
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
		return {
			"state": "approved",
			"timesheet": last_ts.name,
			"requested_hours": req.requested_hours,
			"requested_at": str(_overtime_start_time(req)) if req.requested_at else None,
		}
	return None


def _early_overtime_state(employee, open_ts):
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
	roster = _kiosk_roster()
	if not roster:
		return []

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
				start = prev_end + datetime.timedelta(seconds=1)

	return min(start, now)


def _auto_start_overtime_session(req):
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

	start_dt = get_datetime(start_time) if start_time else _kiosk_now()

	if _get_open_timesheet(employee):
		frappe.throw(_("This employee already has an open kiosk session."))

	company = frappe.db.get_value("Employee", employee, "company")

	overtime_req = frappe.db.get_value(
		"Kiosk Overtime Request",
		{"employee": employee, "status": "Approved", "consumed": 0},
		["name", "timesheet", "requested_at"],
		order_by="modified desc",
		as_dict=True,
	)
	overtime_request = overtime_req.name if overtime_req else None

	if overtime_req and overtime_req.requested_at:
		start_dt = _overtime_start_time(overtime_req)

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

	hours = flt((end_dt - start_dt).total_seconds() / 3600.0, 2)

	timesheet = frappe.get_doc("Timesheet", open_ts.timesheet)
	row = timesheet.get("time_logs", {"name": open_ts.row_name})[0]
	row.completed = 1

	if hours > REGULAR_HOURS_PER_SESSION:
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


def auto_end_overtime_sessions():
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


@frappe.whitelist(allow_guest=True)
def submit_overtime_request(token, requested_hours):
	employee = _resolve_token(token)
	requested_hours = flt(requested_hours)
	if requested_hours <= 0:
		frappe.throw(_("Please enter how many hours of overtime you'd like to request."))
	if requested_hours > 16:
		frappe.throw(_("That's more overtime than one request can cover - please enter a smaller number."))

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
	prompt = _overtime_prompt(employee)
	if not prompt or prompt["state"] != "needs_request":
		frappe.throw(_("There is no alarm to stop right now."))

	if not frappe.db.has_column("Timesheet", SILENCED_FIELD):
		frappe.throw(
			_("Stop Alarm is not available on this site yet — run bench migrate to finish installing it.")
		)

	frappe.db.set_value("Timesheet", prompt["timesheet"], SILENCED_FIELD, 1)
	frappe.db.commit()

	return {"timesheet": prompt["timesheet"]}


@frappe.whitelist(allow_guest=True)
def decide_overtime_request(request, token, decision, by=None):
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
		open_row = _get_open_timesheet(doc.employee)
		still_running = bool(open_row and open_row.timesheet == doc.timesheet)

		if still_running:
			frappe.db.set_value("Timesheet", doc.timesheet, OVERTIME_REQUEST_FIELD, doc.name)
			frappe.db.set_value("Kiosk Overtime Request", doc.name, "consumed", 1)
			frappe.db.commit()
		else:
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
