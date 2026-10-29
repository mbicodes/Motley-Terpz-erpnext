import frappe
from frappe.permissions import add_permission, update_permission_property


def execute():
	frappe.db.set_value(
		"System Settings", "System Settings", "allow_guests_to_upload_files", 1
	)

	if not frappe.db.exists("Custom DocPerm", {"parent": "File", "role": "Guest"}):
		add_permission("File", "Guest", 0)

	update_permission_property("File", "Guest", 0, "create", 1)
	update_permission_property("File", "Guest", 0, "read", 0)
