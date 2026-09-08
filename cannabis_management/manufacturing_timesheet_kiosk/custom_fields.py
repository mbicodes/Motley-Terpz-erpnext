"""Custom field definitions for the Manufacturing Timesheet Kiosk module.

Applied idempotently from ``after_migrate`` (see hooks.py) so a plain ``bench migrate``
reproduces the field on any site - the same pattern used by
``cannabis_management.manufacturing_portal.custom_fields``.

Storage note: the code is stored as plain text in a Data field, deliberately, matching
the Manufacturing Portal's access code - not hashed, not a Password field. This makes
the kiosk's login lookup and the uniqueness check in ``employee_hooks.py`` plain,
indexed-friendly DB queries instead of a decrypt-and-compare loop over every employee.
An administrator can also read a worker's code back off the Employee form if they
forget it. See that module's README for the fuller reasoning; it applies here too.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

EMPLOYEE_FIELDS = [
	{
		"fieldname": "custom_kiosk_access_code",
		"fieldtype": "Data",
		"label": "Kiosk Access Code",
		"insert_after": "status",
		"no_copy": 1,
		"description": (
			"Personal access code / PIN this employee types at the Manufacturing "
			"Process timesheet kiosk to clock in/out. Must be unique across all "
			"employees. Leave blank to deny kiosk access."
		),
	},
]

# A fresh permlevel (2 - Timesheet's Custom DocPerm rows already use 0 and 1, and
# level 1 already grants Accounts User write for the costing fields, so reusing it
# would hand them write on these too) with no role granted *write* at that level:
# nobody can clear or edit these through the Desk form, not even System Manager.
#
# Storing the photo as plain base64 text - not an Attach/Attach Image field - is
# what actually matters for "nobody can delete it" though: an Attach field is just
# a pointer to a File document, and File documents can always be removed
# independently of the field that points at them (the little (x) on the
# attachment, or the Desk File list). A Long Text field holding the data itself has
# nothing separate left to delete - removing it means editing/deleting the
# Timesheet row itself, same as any other field on the document.
PHOTO_PERMLEVEL = 2

TIMESHEET_FIELDS = [
	{
		"fieldname": "custom_start_verification_photo",
		"fieldtype": "Long Text",
		"label": "Start Verification Photo",
		"insert_after": "time_logs",
		"no_copy": 1,
		"read_only": 1,
		"permlevel": PHOTO_PERMLEVEL,
		"description": "Captured by the kiosk when this employee started - not an attachment, so it cannot be removed independently of the Timesheet itself.",
	},
	{
		"fieldname": "custom_end_verification_photo",
		"fieldtype": "Long Text",
		"label": "End Verification Photo",
		"insert_after": "custom_start_verification_photo",
		"no_copy": 1,
		"read_only": 1,
		"permlevel": PHOTO_PERMLEVEL,
		"description": "Captured by the kiosk when this employee ended - not an attachment, so it cannot be removed independently of the Timesheet itself.",
	},
]

CUSTOM_FIELDS = {"Employee": EMPLOYEE_FIELDS, "Timesheet": TIMESHEET_FIELDS}

# Mirrors the roles that already hold permlevel-0 read on Timesheet (see the
# existing Custom DocPerm rows) - granting level-2 read to a role with no base
# access to the doctype at all wouldn't let them open the form to see it anyway.
PHOTO_VIEWER_ROLES = ("HR User", "Manufacturing User", "CEO")


def install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	_lock_photo_fields()


def _lock_photo_fields():
	"""Grant *read* at PHOTO_PERMLEVEL to roles that already see Timesheets, and
	write to nobody - re-applied every migrate so the lock can't drift."""
	import frappe

	for role in PHOTO_VIEWER_ROLES:
		if not frappe.db.exists("Role", role):
			continue
		if frappe.db.exists("Custom DocPerm", {"parent": "Timesheet", "role": role, "permlevel": PHOTO_PERMLEVEL}):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Timesheet",
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": PHOTO_PERMLEVEL,
				"read": 1,
				"write": 0,
			}
		).insert(ignore_permissions=True)
