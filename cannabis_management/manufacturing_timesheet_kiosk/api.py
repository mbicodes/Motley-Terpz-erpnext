# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

"""
API endpoints for the Manufacturing Timesheet Kiosk (``/manufacturing-timesheet``).

Flow:
	1. verify_access_code(access_code) -> {token, employee, employee_name, open_session}
	2. start_session(token, activity_type, start_time) -> {name}
	   OR
	   end_session(token, end_time) -> {timesheet, hours}

`token` is a short-lived (5 minute), single-use handle returned by
verify_access_code. It stands in for the employee for the rest of the flow so the
employee id is never trusted directly from the client, and a guest cannot start/end a
session without first passing the access-code check.

The access code itself lives in a plain Data field (see custom_fields.py) so this
lookup is a single indexed query rather than a decrypt-and-compare loop.
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


def _get_open_session(employee):
	rows = frappe.get_all(
		"Kiosk Timesheet Session",
		filters={"employee": employee, "status": "Running"},
		fields=["name", "activity_type", "start_time"],
		order_by="creation desc",
		limit_page_length=1,
	)
	return rows[0] if rows else None


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
def verify_access_code(access_code):
	access_code = (access_code or "").strip()
	if not access_code:
		frappe.throw(_("Please enter your access code"))

	matched = frappe.db.get_value(
		"Employee",
		{CODE_FIELD: access_code, "status": "Active"},
		["name", "employee_name"],
		as_dict=True,
	)

	if not matched:
		_log_attempt(None, "Failed", "Invalid access code")
		frappe.throw(_("Invalid access code"))

	_log_attempt(matched.name, "Success")

	return {
		"token": _make_token(matched.name),
		"employee": matched.name,
		"employee_name": matched.employee_name,
		"open_session": _get_open_session(matched.name),
	}


@frappe.whitelist(allow_guest=True)
def start_session(token, activity_type, start_time=None):
	employee = _resolve_token(token)

	if not activity_type:
		frappe.throw(_("Please select an Activity Type"))

	if _get_open_session(employee):
		frappe.throw(_("This employee already has an open kiosk session."))

	start_dt = get_datetime(start_time) if start_time else now_datetime()

	doc = frappe.get_doc(
		{
			"doctype": "Kiosk Timesheet Session",
			"employee": employee,
			"activity_type": activity_type,
			"start_time": start_dt,
			"status": "Running",
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {"name": doc.name, "activity_type": doc.activity_type, "start_time": doc.start_time}


@frappe.whitelist(allow_guest=True)
def end_session(token, end_time=None):
	employee = _resolve_token(token)

	session = _get_open_session(employee)
	if not session:
		frappe.throw(_("No open kiosk session found for this employee."))

	start_dt = get_datetime(session.start_time)
	end_dt = get_datetime(end_time) if end_time else now_datetime()

	if end_dt <= start_dt:
		frappe.throw(_("End time must be after the start time."))

	# Rounded to the nearest hundredth of an hour (~36 seconds) for the kiosk
	# receipt/display. The Timesheet Detail row itself is recalculated by ERPNext's
	# own Timesheet.calculate_hours() from from_time/to_time (same formula used
	# everywhere else in ERPNext), so the two stay consistent.
	hours = flt((end_dt - start_dt).total_seconds() / 3600.0, 2)

	company = frappe.db.get_value("Employee", employee, "company")

	timesheet = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"employee": employee,
			"company": company,
			"time_logs": [
				{
					"activity_type": session.activity_type,
					"from_time": start_dt,
					"to_time": end_dt,
					"hours": hours,
				}
			],
		}
	)
	timesheet.insert(ignore_permissions=True)

	session_doc = frappe.get_doc("Kiosk Timesheet Session", session.name)
	session_doc.end_time = end_dt
	session_doc.status = "Completed"
	session_doc.timesheet = timesheet.name
	session_doc.save(ignore_permissions=True)

	frappe.db.commit()
	frappe.cache().delete_value(f"kiosk_token:{token}")

	return {
		"timesheet": timesheet.name,
		"hours": hours,
		"activity_type": session.activity_type,
	}
