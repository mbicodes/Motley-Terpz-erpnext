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
		"options": "\nMaster Touch Manufacturing\nHemet Distro",
		"insert_after": "custom_kiosk_timesheet",
		"depends_on": "eval:doc.custom_kiosk_timesheet",
		"description": (
			"Which section of the Manufacturing Timesheet kiosk board this "
			"employee's card appears under."
		),
	},
]

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
	{
		"fieldname": "custom_overtime_warning_sent",
		"fieldtype": "Check",
		"label": "Overtime Warning Sent",
		"insert_after": "custom_overtime_request",
		"default": "0",
		"no_copy": 1,
		"read_only": 1,
		"description": (
			"Set by the kiosk's scheduled 30-minutes-before-cutoff warning "
			"(api.send_upcoming_cutoff_warnings) once that email has gone out for this "
			"still-running session, so the next minute's tick doesn't send it again."
		),
	},
	{
		"fieldname": "custom_overtime_declined",
		"fieldtype": "Check",
		"label": "Overtime Declined By Employee",
		"insert_after": "custom_overtime_warning_sent",
		"default": "0",
		"no_copy": 1,
		"read_only": 1,
		"description": (
			"Set by api.decline_overtime_request when the employee taps End instead of "
			"Request Overtime after this Timesheet was auto-ended at 8h: permanently "
			"resolves the board's needs_request prompt/alarm for this session without "
			"filing a Kiosk Overtime Request - unlike a Rejected request (which still "
			"invites a fresh request), this means the employee themself is done."
		),
	},
	{
		"fieldname": "custom_overtime_alarm_silenced",
		"fieldtype": "Check",
		"label": "Overtime Alarm Silenced",
		"insert_after": "custom_overtime_declined",
		"default": "0",
		"no_copy": 1,
		"read_only": 1,
		"description": (
			"Set by api.silence_overtime_alarm when Stop Alarm is tapped on this "
			"session's needs-overtime card. Server-side (not per-browser) on purpose: "
			"every kiosk board polling get_employee_board reads the same flag, so "
			"stopping the siren on one tablet stops it everywhere, not just there. "
			"Only mutes the alarm - Request Overtime/End stay available exactly as "
			"before, and this clears again the moment the prompt itself resolves."
		),
	},
]

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

PHOTO_VIEWER_ROLES = ("HR User", "Manufacturing User", "CEO")


def install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	_lock_photo_fields()


def _lock_photo_fields():
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
