from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.utils import getdate

SETTINGS = "Daily Report Settings"
DEFAULT_TIME_ZONE = "America/Los_Angeles"


def farm_time_zone():
	tz = frappe.db.get_single_value(SETTINGS, "time_zone") or DEFAULT_TIME_ZONE
	try:
		return ZoneInfo(tz)
	except (ZoneInfoNotFoundError, ValueError):
		return ZoneInfo(DEFAULT_TIME_ZONE)


def farm_now():
	return datetime.now(farm_time_zone())


def farm_today():
	return farm_now().date()


def stamp_new(doc):
	if doc.is_new() and not doc.amended_from:
		doc.submitted_by = frappe.session.user
		doc.report_date = farm_today()


def block_duplicate(doc):
	existing = frappe.db.exists(
		doc.doctype,
		{
			"submitted_by": doc.submitted_by,
			"report_date": doc.report_date,
			"docstatus": 1,
			"name": ["!=", doc.name or ""],
		},
	)
	if existing:
		frappe.throw(
			_("A {0} for {1} is already submitted ({2}).").format(
				_(doc.doctype), frappe.format(doc.report_date, "Date"), existing
			)
		)


def clear_unless(doc, controlling_field, value, *dependents):
	if doc.get(controlling_field) == value:
		return
	for fieldname in dependents:
		if doc.meta.get_field(fieldname).fieldtype == "Table":
			doc.set(fieldname, [])
		else:
			doc.set(fieldname, None)


def check_not_before_report_date(doc, *fieldnames):
	report_date = getdate(doc.report_date)
	for fieldname in fieldnames:
		if doc.get(fieldname) and getdate(doc.get(fieldname)) < report_date:
			frappe.throw(_("{0} cannot be before the report date.").format(_(doc.meta.get_label(fieldname))))


def require_male_photos(doc):
	if doc.males_found == "Yes" and not doc.get("male_photos"):
		frappe.throw(_("Add at least one photo of the males found before submitting."))
