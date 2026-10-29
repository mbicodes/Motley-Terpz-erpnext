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
				frappe.log_error(title=f"Kiosk photo conversion failed: {name}.{field}")
				continue
			frappe.db.set_value("Timesheet", name, field, file_url, update_modified=False)

	frappe.db.commit()
