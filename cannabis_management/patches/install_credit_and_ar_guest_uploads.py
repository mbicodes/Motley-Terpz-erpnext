"""Let a public, anonymous applicant attach a file to the Credit Application
Web Form.

Frappe's file-upload endpoint (`frappe.handler.upload_file`) refuses Guest
uploads unless System Settings explicitly allows it, and the legacy inline
base64 attach path in `web_form.accept()` separately needs Guest to hold
"create" on File. Without both, the Web Form's onboarding-packet Attach field
throws a PermissionError on submit and the whole application fails to save —
not just the attachment.

Idempotent.
"""

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
