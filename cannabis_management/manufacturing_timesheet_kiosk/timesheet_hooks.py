import frappe
from frappe import _

from cannabis_management.manufacturing_timesheet_kiosk.custom_fields import (
	PHOTO_PERMLEVEL,
	TIMESHEET_FIELDS,
)

PHOTO_FIELDS = tuple(
	field["fieldname"]
	for field in TIMESHEET_FIELDS
	if field.get("permlevel") == PHOTO_PERMLEVEL
)


def on_trash(doc, method=None):
	if doc.doctype != "Timesheet":
		return

	for field in PHOTO_FIELDS:
		if not doc.get(field):
			continue
		for name in frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Timesheet",
				"attached_to_name": doc.name,
				"attached_to_field": field,
			},
			pluck="name",
		):
			frappe.delete_doc("File", name, ignore_permissions=True, force=True)


def on_trash_file(doc, method=None):
	return
