"""Move existing kiosk verification photos from base64 text into private Files.

The photo fields started life as Long Text holding a base64 data URL. They are now
Attach Image fields holding a private file's URL, so the photo shows as a picture on
the Timesheet instead of as a wall of base64 nobody can read without decoding it by
hand. Any row written before that switch still holds the raw data URL, which would
render as a broken image in an Attach Image field - so decode each one onto disk and
leave the URL behind.

Timesheets are not saved here. db_set writes the one field directly, which is what we
want: these are submitted documents, the fields are permlevel-2 read_only, and a
save() would re-run validation on rows whose only problem is the format of a field
this patch is fixing.
"""

import frappe

from cannabis_management.manufacturing_timesheet_kiosk.api import _store_photo
from cannabis_management.manufacturing_timesheet_kiosk.custom_fields import (
	PHOTO_PERMLEVEL,
	TIMESHEET_FIELDS,
)

PHOTO_FIELDS = tuple(
	field["fieldname"]
	for field in TIMESHEET_FIELDS
	if field.get("permlevel") == PHOTO_PERMLEVEL
)


def execute():
	# Only ever true of a value written before the fieldtype changed - a converted
	# field holds "/private/files/...", never "data:".
	conditions = " or ".join(f"`{field}` like 'data:%%'" for field in PHOTO_FIELDS)
	names = frappe.db.sql_list(f"select name from `tabTimesheet` where {conditions}")
	if not names:
		return

	for name in names:
		row = frappe.db.get_value("Timesheet", name, PHOTO_FIELDS, as_dict=True)
		for field in PHOTO_FIELDS:
			value = row.get(field)
			if not value or not value.startswith("data:"):
				continue
			label = "start" if "start" in field else "end"
			try:
				file_url = _store_photo(name, field, value, label)
			except Exception:
				# One unreadable capture must not strand the rest. Leave the base64
				# in place - it is still the photo, just not yet viewable - and log
				# it so it can be looked at.
				frappe.log_error(title=f"Kiosk photo conversion failed: {name}.{field}")
				continue
			frappe.db.set_value("Timesheet", name, field, file_url, update_modified=False)

	frappe.db.commit()
