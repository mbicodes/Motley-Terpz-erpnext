import frappe

JOB = "cannabis_management.drive_backup.upload_fresh_backup"


def upload_every_8_hours():
	if not frappe.db.get_single_value("Google Drive", "enable"):
		return
	frappe.enqueue(
		JOB,
		queue="long",
		timeout=1500,
		job_id=f"{frappe.local.site}::google-drive-backup-8h",
		deduplicate=True,
	)


def upload_fresh_backup():
	from frappe.integrations.doctype.google_drive.google_drive import upload_system_backup_to_google_drive
	from frappe.utils.backups import new_backup

	with_files = frappe.db.get_single_value("Google Drive", "file_backup")
	new_backup(ignore_files=not with_files, force=True)
	frappe.flags.create_new_backup = True
	try:
		upload_system_backup_to_google_drive()
	finally:
		frappe.flags.create_new_backup = False
