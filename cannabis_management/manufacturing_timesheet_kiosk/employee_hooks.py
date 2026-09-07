"""Employee validation for the Manufacturing Timesheet Kiosk access code.

Uniqueness is enforced here rather than with a DB unique index on purpose: most
employees have no code, and Frappe stores an unset Data field as ``''`` rather than
NULL, so a unique index would reject the *second* employee without a code. Validating
in Python lets empty values be ignored - same reasoning as
``cannabis_management.manufacturing_portal.user_hooks``.
"""

import frappe
from frappe import _

FIELDNAME = "custom_kiosk_access_code"


def validate(doc, method=None):
	code = (doc.get(FIELDNAME) or "").strip()

	# Normalise before anything else so " 1234 " and "1234" cannot both exist.
	if code != (doc.get(FIELDNAME) or ""):
		doc.set(FIELDNAME, code)

	if not code:
		return

	_validate_unique(doc, code)


def _validate_unique(doc, code):
	"""A code must identify exactly one employee, or 'whoever it matches' is undefined."""
	clash = frappe.db.get_value(
		"Employee",
		{FIELDNAME: code, "name": ["!=", doc.name]},
		["name", "employee_name"],
		as_dict=True,
	)
	if clash:
		frappe.throw(
			_("This Kiosk Access Code is already assigned to another employee ({0}). "
			  "Please choose a different code.").format(
				frappe.bold(f"{clash.name} - {clash.employee_name}")
			),
			title=_("Duplicate Code"),
		)
