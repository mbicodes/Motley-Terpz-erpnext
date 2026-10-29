import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, nowdate

from cannabis_management.time_clock.pairing import (
	build_sessions,
	sessions_for_date,
	total_seconds,
)

TIME_CLOCK_ROLE = "Time Clock User"

NOTE_TAKER_ROLES = ("System Manager", "HR Manager", "Super Admin")


def _session_user():
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Please sign in to use the time clock."), frappe.PermissionError)
	return user


def _require_clock_access(user):
	if TIME_CLOCK_ROLE not in frappe.get_roles(user):
		frappe.throw(
			_('You do not have time clock access. Ask an administrator for the "{0}" role.').format(
				TIME_CLOCK_ROLE
			),
			frappe.PermissionError,
		)


def can_manage_notes(user=None):
	roles = set(frappe.get_roles(user or frappe.session.user))
	return bool(roles.intersection(NOTE_TAKER_ROLES))


def _require_note_access():
	if not can_manage_notes():
		frappe.throw(_("You are not permitted to manage day notes."), frappe.PermissionError)


def _last_punch(user):
	rows = frappe.get_all(
		"User Checkin",
		filters={"user": user},
		fields=["name", "time", "log_type"],
		order_by="time desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def _next_log_type(last_punch):
	return "IN" if (not last_punch or last_punch.log_type == "OUT") else "OUT"


def _punches_since(user, start_date):
	return frappe.get_all(
		"User Checkin",
		filters={"user": user, "time": [">=", f"{start_date} 00:00:00"]},
		fields=["name", "time", "log_type"],
		order_by="time asc, creation asc",
	)


def _day_note(user, date):
	name = frappe.db.exists("User Day Note", {"user": user, "date": date})
	if not name:
		return None
	doc = frappe.get_doc("User Day Note", name)
	return {"name": doc.name, "note": doc.note, "logged_by": doc.logged_by}


def _clock_users():
	role_rows = frappe.get_all(
		"Has Role",
		filters={"role": TIME_CLOCK_ROLE, "parenttype": "User"},
		fields=["parent"],
		distinct=True,
	)
	names = [row.parent for row in role_rows]
	if not names:
		return []

	return frappe.get_all(
		"User",
		filters={"name": ["in", names], "enabled": 1},
		fields=["name", "full_name"],
		order_by="full_name asc",
	)


def _request_context():
	ip = getattr(frappe.local, "request_ip", None)

	try:
		agent = frappe.get_request_header("User-Agent") or ""
	except Exception:
		agent = ""

	return ip, agent[:500]


def _serialise(sessions):
	return [
		{
			"in_time": str(s["in_time"]),
			"out_time": str(s["out_time"]) if s["out_time"] else None,
			"seconds": s["seconds"],
			"is_open": s["is_open"],
		}
		for s in sessions
	]


@frappe.whitelist()
def get_my_status():
	user = _session_user()
	_require_clock_access(user)

	today = getdate(nowdate())
	now = now_datetime()

	punches = _punches_since(user, add_days(today, -1))
	all_sessions = build_sessions(punches, now=now)
	today_sessions = [s for s in all_sessions if s["in_time"].date() == today]

	last = _last_punch(user)
	open_session = next((s for s in all_sessions if s["is_open"]), None)

	return {
		"user": user,
		"full_name": frappe.db.get_value("User", user, "full_name") or user,
		"server_time": str(now),
		"is_clocked_in": bool(last and last.log_type == "IN"),
		"next_action": _next_log_type(last),
		"last_punch": {"time": str(last.time), "log_type": last.log_type} if last else None,
		"open_since": str(open_session["in_time"]) if open_session else None,
		"today_sessions": _serialise(today_sessions),
		"today_seconds": total_seconds(today_sessions),
		"day_note": _day_note(user, today),
		"can_manage_notes": can_manage_notes(user),
	}


@frappe.whitelist()
def punch():
	user = _session_user()
	_require_clock_access(user)

	log_type = _next_log_type(_last_punch(user))

	doc = frappe.new_doc("User Checkin")
	doc.user = user
	doc.time = now_datetime()
	doc.log_type = log_type
	doc.source = "Portal"
	doc.device_ip, doc.user_agent = _request_context()
	doc.insert(ignore_permissions=True)

	status = get_my_status()
	status["punched"] = log_type
	return status


@frappe.whitelist()
def get_roster(date=None):
	_require_note_access()

	date = getdate(date or nowdate())
	now = now_datetime()
	roster = []

	for user in _clock_users():
		last = _last_punch(user.name)
		punches = _punches_since(user.name, add_days(date, -1))
		day_sessions = sessions_for_date(punches, date, now=now)

		roster.append(
			{
				"user": user.name,
				"full_name": user.full_name or user.name,
				"is_clocked_in": bool(last and last.log_type == "IN"),
				"last_punch": {"time": str(last.time), "log_type": last.log_type} if last else None,
				"seconds": total_seconds(day_sessions),
				"day_note": _day_note(user.name, date),
			}
		)

	return {"date": str(date), "server_time": str(now), "roster": roster}


@frappe.whitelist()
def set_day_note(user, note, date=None):
	_require_note_access()

	note = (note or "").strip()
	if not note:
		frappe.throw(_("Note cannot be empty."))

	if not frappe.db.exists("User", user):
		frappe.throw(_("Unknown user {0}.").format(user))

	date = getdate(date or nowdate())
	existing = frappe.db.exists("User Day Note", {"user": user, "date": date})

	if existing:
		doc = frappe.get_doc("User Day Note", existing)
		doc.note = note
		doc.logged_by = frappe.session.user
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.new_doc("User Day Note")
		doc.user = user
		doc.date = date
		doc.note = note
		doc.logged_by = frappe.session.user
		doc.insert(ignore_permissions=True)

	return {"name": doc.name, "note": doc.note, "logged_by": doc.logged_by}


@frappe.whitelist()
def remove_day_note(user, date=None):
	_require_note_access()

	date = getdate(date or nowdate())
	existing = frappe.db.exists("User Day Note", {"user": user, "date": date})
	if existing:
		frappe.delete_doc("User Day Note", existing, ignore_permissions=True)

	return {"removed": bool(existing)}
