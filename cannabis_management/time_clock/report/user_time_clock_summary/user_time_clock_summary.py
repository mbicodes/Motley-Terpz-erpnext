"""Pairs raw punches into worked sessions with hours.

This report exists because clocking Users rather than Employees means none of HRMS's
attendance/timesheet reporting applies — the summary layer has to be built by hand.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, nowdate

from cannabis_management.time_clock.pairing import build_sessions


def execute(filters=None):
	filters = frappe._dict(filters or {})

	from_date = getdate(filters.get("from_date") or nowdate())
	to_date = getdate(filters.get("to_date") or nowdate())
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."))

	return get_columns(), get_data(from_date, to_date, filters.get("user"))


def get_columns():
	return [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "user",
			"label": _("User"),
			"fieldtype": "Link",
			"options": "User",
			"width": 200,
		},
		{"fieldname": "full_name", "label": _("Full Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "in_time", "label": _("In"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "out_time", "label": _("Out"), "fieldtype": "Datetime", "width": 160},
		{
			"fieldname": "hours",
			"label": _("Hours"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 90,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "note", "label": _("Day Note"), "fieldtype": "Data", "width": 240},
	]


def get_data(from_date, to_date, user=None):
	punch_filters = {
		# Reach a day earlier so an overnight session starting before the window is
		# paired correctly, and two days later so its OUT is still in scope.
		"time": ["between", [f"{add_days(from_date, -1)} 00:00:00", f"{add_days(to_date, 2)} 23:59:59"]]
	}
	if user:
		punch_filters["user"] = user

	punches = frappe.get_all(
		"User Checkin",
		filters=punch_filters,
		fields=["user", "user_full_name", "time", "log_type"],
		order_by="user asc, time asc, creation asc",
	)

	by_user = {}
	names = {}
	for punch in punches:
		by_user.setdefault(punch.user, []).append(punch)
		if punch.user_full_name:
			names[punch.user] = punch.user_full_name

	notes = get_notes(from_date, to_date, user)
	now = now_datetime()
	rows = []

	for punch_user, user_punches in by_user.items():
		for session in build_sessions(user_punches, now=now):
			session_date = session["in_time"].date()
			if not (from_date <= session_date <= to_date):
				continue

			rows.append(
				{
					"date": session_date,
					"user": punch_user,
					"full_name": names.get(punch_user) or punch_user,
					"in_time": session["in_time"],
					"out_time": session["out_time"],
					"hours": round(session["seconds"] / 3600.0, 2),
					"status": _("Open") if session["is_open"] else _("Complete"),
					"note": notes.get((punch_user, session_date), ""),
				}
			)

	rows.sort(key=lambda r: (r["date"], r["full_name"], r["in_time"]))
	return rows


def get_notes(from_date, to_date, user=None):
	note_filters = {"date": ["between", [from_date, to_date]]}
	if user:
		note_filters["user"] = user

	return {
		(row.user, getdate(row.date)): row.note
		for row in frappe.get_all(
			"User Day Note", filters=note_filters, fields=["user", "date", "note"]
		)
	}
