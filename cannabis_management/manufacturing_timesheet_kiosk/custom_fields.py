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
	{
		"fieldname": "custom_kiosk_timesheet",
		"fieldtype": "Check",
		"label": "Kiosk Timesheet",
		"insert_after": "custom_kiosk_access_code",
		"default": "0",
		"description": (
			"Show this employee's card on the Manufacturing Timesheet kiosk board "
			"(/manufacturing-timesheet). Leave unchecked to keep their card off the "
			"board entirely."
		),
	},
	{
		"fieldname": "custom_kiosk_section",
		"fieldtype": "Select",
		"label": "Kiosk Section",
		# Blank first option so a freshly-checked employee doesn't silently land in
		# a section nobody picked - get_employee_board() (api.py) leaves a card off
		# the board until this is set to one of the two real options below.
		"options": "\nMaster Touch Manufacturing\nHemet Distro",
		"insert_after": "custom_kiosk_timesheet",
		"depends_on": "eval:doc.custom_kiosk_timesheet",
		"description": (
			"Which section of the Manufacturing Timesheet kiosk board this "
			"employee's card appears under."
		),
	},
]

# A fresh permlevel (2 - Timesheet's Custom DocPerm rows already use 0 and 1, and
# level 1 already grants Accounts User write for the costing fields, so reusing it
# would hand them write on these too) with no role granted *write* at that level:
# nobody can clear or edit these through the Desk form, not even System Manager.
#
# These are Attach Image fields holding a private file URL, so the photo shows as a
# picture on the Timesheet and opens by clicking it - no base64 to copy out and
# decode by hand.
#
# That does mean the photo is a File document the field points at, and a File can
# normally be deleted independently of whatever points at it - the little (x) on the
# attachment, or the Desk File list. Field permissions cannot stop that, because the
# deletion never touches this field. What stops it is a pair of document guards, in
# timesheet_hooks.py: one refuses to delete a Timesheet carrying a photo, the other
# refuses to delete a File that is one. The guards are the protection here, not the
# storage shape - see that module's docstring.
PHOTO_PERMLEVEL = 2

TIMESHEET_FIELDS = [
	{
		"fieldname": "custom_start_verification_photo",
		"fieldtype": "Attach Image",
		"label": "Start Verification Photo",
		"insert_after": "time_logs",
		"no_copy": 1,
		"read_only": 1,
		"permlevel": PHOTO_PERMLEVEL,
		"description": "No longer captured (face-detection/photo step was removed from the kiosk). Left in place for old Timesheets that still hold one.",
	},
	{
		"fieldname": "custom_end_verification_photo",
		"fieldtype": "Attach Image",
		"label": "End Verification Photo",
		"insert_after": "custom_start_verification_photo",
		"no_copy": 1,
		"read_only": 1,
		"permlevel": PHOTO_PERMLEVEL,
		"description": "No longer captured (face-detection/photo step was removed from the kiosk). Left in place for old Timesheets that still hold one.",
	},
	{
		"fieldname": "custom_auto_ended",
		"fieldtype": "Check",
		"label": "Auto-ended (8h)",
		"insert_after": "custom_end_verification_photo",
		"default": "0",
		"no_copy": 1,
		"read_only": 1,
		"description": (
			"Set by the kiosk's scheduled 8-hour cutoff (api.auto_end_overtime_sessions): "
			"this Timesheet was force-ended by the system, not by the employee tapping End, "
			"because the session hit 8 hours. Drives the 'request overtime' prompt on the "
			"board until the employee submits a Kiosk Overtime Request for it."
		),
	},
	{
		"fieldname": "custom_overtime_request",
		"fieldtype": "Link",
		"options": "Kiosk Overtime Request",
		"label": "Overtime Request",
		"insert_after": "custom_auto_ended",
		"no_copy": 1,
		"read_only": 1,
		"description": (
			"Set by start_session when this employee has an Approved, not-yet-used "
			"overtime request: exempts THIS session from the 8-hour auto-cutoff, so it "
			"runs until manually ended - same as before this feature existed - and "
			"end_session's normal 8h row-split (custom_overtime) takes over from there."
		),
	},
]

# On the Timesheet Detail child table (one row per time log), not on Timesheet
# itself: a single kiosk session that runs past 8 hours is split into two rows on
# end_session (api.py) - the regular row, and this one for the hours past 8 - so
# this checkbox has to live on the row, not the parent. Set automatically by the
# kiosk; nothing on the Employee/Timesheet form needs to touch it by hand.
TIMESHEET_DETAIL_FIELDS = [
	{
		"fieldname": "custom_overtime",
		"fieldtype": "Check",
		"label": "Overtime",
		"insert_after": "completed",
		"default": "0",
		"no_copy": 1,
		"read_only": 1,
		"description": (
			"Set automatically by the kiosk: this row holds the hours worked past "
			"8 in a single clock-in/out session."
		),
	},
]

CUSTOM_FIELDS = {
	"Employee": EMPLOYEE_FIELDS,
	"Timesheet": TIMESHEET_FIELDS,
	"Timesheet Detail": TIMESHEET_DETAIL_FIELDS,
}

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
