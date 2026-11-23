"""PTO and Sick Time: balances in hours, approve / deny / cancel, the Google Calendar invite,
the "did you take it?" email after the time off ends, and data for the My Time Off page and
the Time Off Request calendar view.

Balance for a year = earned (from the Time Off Policy of the employee's Full Time / Part Time
category) - hours of Approved and Taken requests that start in that year. Pending holds no hours;
Denied, Cancelled and Not Taken give them back simply by not being counted.
"""
import datetime

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, get_url, get_url_to_form, getdate, nowdate, random_string

DT = "Time Off Request"
TYPES = (("PTO", "pto"), ("Sick Time", "sick"))
HR_ROLES = {"HR Manager", "HR User", "System Manager"}
USES_HOURS = ("Approved", "Taken")
CATEGORY_FIELD = "custom_time_off_category"


def is_hr(user=None):
	return bool(HR_ROLES & set(frappe.get_roles(user)))


def employee_of(user=None):
	return frappe.db.get_value("Employee", {"user_id": user or frappe.session.user, "status": "Active"}, "name")


def weekdays(from_date, to_date):
	d, end, n = getdate(from_date), getdate(to_date), 0
	while d <= end:
		n += d.weekday() < 5
		d += datetime.timedelta(days=1)
	return n


def approver_for(employee):
	boss = frappe.db.get_value("Employee", employee, "reports_to")
	user = boss and frappe.db.get_value("Employee", boss, "user_id")
	return user or frappe.db.get_single_value("Time Off Settings", "fallback_approver")


def _hours_worked(employee, year):
	from cannabis_management.cannabis_management.page.employee_timesheet.employee_timesheet import build_rows

	end = min(getdate(nowdate()), getdate(f"{year}-12-31"))
	return sum(flt(r["hours"]) for r in build_rows(f"{year}-01-01", end, employee))


def _sum_hours(employee, leave_type, year, statuses):
	return flt(frappe.db.sql(
		f"""select coalesce(sum(total_hours), 0) from `tab{DT}`
		where employee=%s and leave_type=%s and status in %s and year(from_date)=%s""",
		(employee, leave_type, statuses, year))[0][0], 2)


def balances(employee, year=None):
	year = cint(year) or getdate(nowdate()).year
	category = frappe.db.get_value("Employee", employee, CATEGORY_FIELD)
	policy = category and frappe.db.get_value("Time Off Policy", category, "*", as_dict=True)
	worked, out = None, {}
	for leave_type, p in TYPES:
		earned = 0.0
		if policy:
			yearly = flt(policy[f"{p}_hours"])
			if policy[f"{p}_method"] == "Per hour worked":
				worked = _hours_worked(employee, year) if worked is None else worked
				earned = worked * flt(policy[f"{p}_rate"])
				earned = min(earned, yearly) if yearly else earned
			else:
				earned = yearly
		used = _sum_hours(employee, leave_type, year, USES_HOURS)
		out[leave_type] = {
			"earned": flt(earned, 2),
			"used": used,
			"pending": _sum_hours(employee, leave_type, year, ("Pending",)),
			"available": flt(earned - used, 2),
		}
	return {"category": category, "year": year, "types": out}


@frappe.whitelist()
def get_balances(employee=None, year=None):
	employee = employee or employee_of()
	if not employee:
		return None
	if employee != employee_of() and not is_hr():
		frappe.throw(_("You can only see your own time off balance."), frappe.PermissionError)
	return balances(employee, year)


# ---------- messages ----------


def _mail(user):
	return user and user not in ("Administrator", "Guest") and frappe.db.get_value("User", user, "email")


def _summary(doc):
	return _("{0} · {1} · {2} to {3} ({4} hrs)").format(
		doc.employee_name, doc.leave_type, formatdate(doc.from_date), formatdate(doc.to_date), flt(doc.total_hours, 2))


def _tell(users, subject, html, doc, cc=None):
	users = [u for u in dict.fromkeys(users) if u and u not in ("Administrator", "Guest")]
	emails = [e for e in (_mail(u) for u in users) if e]
	if emails:
		try:  # a mail problem must not undo the request or decision it reports
			frappe.sendmail(recipients=emails, cc=[e for e in (_mail(u) for u in (cc or [])) if e],
				subject=subject, message=html, reference_doctype=DT, reference_name=doc.name)
		except Exception:
			frappe.log_error(title=f"Time Off email: {doc.name}")
	if users:
		from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

		enqueue_create_notification(users, {"type": "Alert", "document_type": DT, "document_name": doc.name,
			"subject": subject, "from_user": frappe.session.user})


def notify_new(doc):
	"""Tell the approver (or every HR Manager when nobody is set) that a request is waiting."""
	users = [doc.approver] if doc.approver else frappe.get_all(
		"Has Role", filters={"role": "HR Manager", "parenttype": "User"}, pluck="parent")
	b = balances(doc.employee, getdate(doc.from_date).year)["types"][doc.leave_type]
	_tell(users, _("Time off request: {0}").format(_summary(doc)), f"""
		<p>{frappe.bold(doc.employee_name)} asked for {doc.leave_type}: {formatdate(doc.from_date)} to
		{formatdate(doc.to_date)}, {flt(doc.total_hours, 2)} hrs.</p>
		<p>{doc.leave_type} available: {b['available']} hrs.</p>
		{f'<p>Note: {frappe.utils.escape_html(doc.reason)}</p>' if doc.reason else ''}
		<p><a href="{get_url_to_form(DT, doc.name)}">Open the request to approve or deny</a></p>""", doc)


# ---------- actions ----------


@frappe.whitelist()
def decide(name, approve, comment=None):
	doc = frappe.get_doc(DT, name)
	user, approve = frappe.session.user, cint(approve)
	if not (user == doc.approver or is_hr()):
		frappe.throw(_("Only {0} or HR can approve or deny this request.").format(doc.approver or _("the approver")),
			frappe.PermissionError)
	if user == doc.employee_user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("You cannot approve or deny your own request."), frappe.PermissionError)
	if doc.status != "Pending":
		frappe.throw(_("This request is already {0}.").format(doc.status))
	if approve:
		left = balances(doc.employee, getdate(doc.from_date).year)["types"][doc.leave_type]["available"]
		if flt(doc.total_hours) > left:
			frappe.throw(_("{0} has {1} hrs of {2} left; this request needs {3} hrs.").format(
				doc.employee_name, left, doc.leave_type, flt(doc.total_hours, 2)))
	doc.db_set({"status": "Approved" if approve else "Denied", "approver_comment": comment or "", "decided_by": user})
	if approve:
		push_google(doc)
	verdict = _("approved") if approve else _("denied")
	_tell([doc.employee_user], _("Your time off was {0}: {1}").format(verdict, _summary(doc)), f"""
		<p>Your {doc.leave_type} request for {formatdate(doc.from_date)} to {formatdate(doc.to_date)}
		({flt(doc.total_hours, 2)} hrs) was <b>{verdict}</b> by {frappe.utils.get_fullname(user)}.</p>
		{f'<p>Comment: {frappe.utils.escape_html(comment)}</p>' if comment else ''}
		<p><a href="{get_url_to_form(DT, doc.name)}">Open the request</a></p>""", doc)
	return doc.status


@frappe.whitelist()
def cancel(name):
	doc = frappe.get_doc(DT, name)
	user = frappe.session.user
	if user not in (doc.employee_user, doc.owner) and not is_hr():
		frappe.throw(_("Only the employee or HR can cancel this request."), frappe.PermissionError)
	if doc.status not in ("Pending", "Approved"):
		frappe.throw(_("This request is already {0}.").format(doc.status))
	was = doc.status
	doc.db_set("status", "Cancelled")
	drop_google(doc)
	if was == "Approved":
		_tell([doc.approver], _("Time off cancelled: {0}").format(_summary(doc)),
			f"<p>{frappe.utils.get_fullname(user)} cancelled this approved time off. The hours are back in the bank.</p>", doc)
	return doc.status


def send_confirmations():
	"""Daily: approved time off that has ended gets one "did you take it?" email."""
	for name in frappe.get_all(DT, filters={"status": "Approved", "to_date": ["<", nowdate()], "confirmation_sent": 0},
			pluck="name"):
		doc = frappe.get_doc(DT, name)
		key = random_string(32)
		link = lambda taken: get_url(  # noqa: E731
			f"/api/method/cannabis_management.time_clock.time_off.confirm?name={doc.name}&key={key}&taken={taken}")
		doc.db_set({"confirm_key": key, "confirmation_sent": 1}, update_modified=False)
		_tell([doc.employee_user], _("Did you take your time off? {0}").format(_summary(doc)), f"""
			<p>Your approved {doc.leave_type} for {formatdate(doc.from_date)} to {formatdate(doc.to_date)}
			({flt(doc.total_hours, 2)} hrs) has ended. Please confirm so your hours stay correct.</p>
			<p><a href="{link(1)}"><b>Yes, I took it</b></a> &nbsp;|&nbsp;
			<a href="{link(0)}"><b>No, I worked. Give my hours back</b></a></p>""", doc, cc=[doc.approver])
		frappe.db.commit()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def confirm(name, key, taken):
	"""One-click answer from the confirmation email; the random key in the link is the proof."""
	doc = frappe.db.get_value(DT, name, ["name", "status", "confirm_key", "approver", "employee_name", "leave_type",
		"from_date", "to_date", "total_hours"], as_dict=True)
	if not doc or not key or doc.confirm_key != key:
		return frappe.respond_as_web_page(_("Link not valid"), _("This confirmation link is not valid."),
			indicator_color="red", http_status_code=404)
	if doc.status == "Approved":
		doc.status = "Taken" if cint(taken) else "Not Taken"
		frappe.db.set_value(DT, name, "status", doc.status)
		if doc.status == "Not Taken":
			_tell([doc.approver], _("Time off not taken: {0}").format(_summary(doc)),
				f"<p>{doc.employee_name} says this approved time off was not taken. The hours went back to the bank.</p>", doc)
		frappe.db.commit()
	msg = _("Thanks. Recorded as taken.") if doc.status == "Taken" else (
		_("Thanks. Recorded as not taken; the hours are back in your bank.") if doc.status == "Not Taken"
		else _("This request is {0}; nothing changed.").format(doc.status))
	return frappe.respond_as_web_page(_("Time off"), msg, indicator_color="green")


# ---------- Google Calendar ----------


def _calendar():
	cal = frappe.db.get_single_value("Time Off Settings", "google_calendar")
	if not cal:
		return None
	from frappe.integrations.doctype.google_calendar.google_calendar import get_google_calendar_object

	service, account = get_google_calendar_object(cal)
	return (service, account.google_calendar_id) if account.google_calendar_id else None


def push_google(doc):
	"""Event in the shared Time Off calendar; employee and approver are invited, so Google emails them."""
	try:
		acc = _calendar()
		if not acc:
			return
		service, cal_id = acc
		body = {
			"summary": f"{doc.employee_name}: {doc.leave_type}",
			"description": f"{flt(doc.total_hours, 2)} hrs. {get_url_to_form(DT, doc.name)}",
			"start": {"date": str(doc.from_date)},
			"end": {"date": str(add_days(doc.to_date, 1))},  # Google's end date is exclusive
			"attendees": [{"email": e} for e in dict.fromkeys((_mail(doc.employee_user), _mail(doc.approver))) if e],
		}
		gid = service.events().insert(calendarId=cal_id, body=body, sendUpdates="all").execute().get("id")
		doc.db_set("google_event_id", gid, update_modified=False)
	except Exception:
		frappe.log_error(title=f"Time Off Google Calendar: {doc.name}")


def drop_google(doc):
	if not doc.google_event_id:
		return
	try:
		acc = _calendar()
		if acc:
			acc[0].events().delete(calendarId=acc[1], eventId=doc.google_event_id, sendUpdates="all").execute()
	except Exception:
		frappe.log_error(title=f"Time Off Google Calendar delete: {doc.name}")


# ---------- pages ----------


@frappe.whitelist()
def my_dashboard():
	from cannabis_management.cannabis_management.page.employee_timesheet.employee_timesheet import (
		build_rows,
		pay_period_for,
		report_today,
	)

	start, end = pay_period_for()
	today = report_today()
	out = {"period": [str(start), str(end)], "today": str(today),
		"handbook": frappe.db.get_single_value("Time Off Settings", "handbook")}
	emp = employee_of()
	if not emp:
		return out
	worked = {r["shift_day"]: r["hours"] for r in build_rows(start, end, emp, include_open=True)}
	n = (getdate(end) - getdate(start)).days + 1
	fields = ["name", "leave_type", "status", "from_date", "to_date", "total_hours"]
	out.update(
		employee=emp,
		employee_name=frappe.db.get_value("Employee", emp, "employee_name"),
		balances=balances(emp),
		days=[{"date": str(add_days(start, i)), "hours": flt(worked.get(str(add_days(start, i))), 2)} for i in range(n)],
		off=frappe.get_all(DT, fields=fields, filters={"employee": emp, "status": ["in", USES_HOURS],
			"from_date": ["<=", end], "to_date": [">=", start]}),
		upcoming=frappe.get_all(DT, fields=fields, order_by="from_date", filters={"employee": emp,
			"status": ["in", ["Pending", "Approved"]], "to_date": [">=", str(today)]}),
	)
	return out


COLOURS = {"PTO": "#7c3aed", "Sick Time": "#ea580c"}


@frappe.whitelist()
def calendar_events(start, end, filters=None):
	"""Calendar view of Time Off Request: one bar per request, named and coloured by type."""
	f = frappe.parse_json(filters) or []
	f = [[DT, k, "=", v] for k, v in f.items()] if isinstance(f, dict) else list(f)
	f += [["status", "in", ["Pending", "Approved", "Taken"]], ["from_date", "<=", getdate(end)], ["to_date", ">=", getdate(start)]]
	rows = frappe.get_list(DT, filters=f, fields=["name", "employee_name", "leave_type", "status", "from_date", "to_date"])
	for r in rows:
		r.title = f"{r.employee_name} · {r.leave_type}" + (" (waiting)" if r.status == "Pending" else "")
		r.color = "#9ca3af" if r.status == "Pending" else COLOURS.get(r.leave_type)
		r.all_day, r.locked, r.no_tz = 1, 0, 0
	return rows
