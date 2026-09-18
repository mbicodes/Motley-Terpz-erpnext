"""Production rollout for the 30-minutes-before-cutoff warning + early overtime
request feature (see api.py's module docstring for what the feature itself does).

    bench --site <site> execute cannabis_management.manufacturing_timesheet_kiosk.deploy_overtime_warning.run

Safe to re-run: every step is idempotent (create_custom_fields(update=True) inside
custom_fields.install, reload_doc with force=True).

Does two things a plain `bench migrate` would otherwise be relied on for, done
explicitly here in case this site's migrate is being avoided for unrelated reasons
(see this app's own bench-quirks notes elsewhere in the repo):
	1. Reloads the Kiosk Overtime Request / Kiosk Access Log doctypes from their JSON
	   so their tables actually exist - found missing entirely on moltey.local before
	   this script was written, which would have made every overtime request fail.
	2. Re-applies this module's custom fields (custom_fields.install), including the
	   new custom_overtime_warning_sent field the warning feature reads/writes.

After this runs, the new cron job itself (send_upcoming_cutoff_warnings, wired in
hooks.py's scheduler_events) only starts firing once this site's scheduler process is
restarted - hooks.py is cached in memory by whatever long-running process reads it, a
plain migrate does not touch that. Restart it with whatever mechanism this site's
deploy already uses for a hooks.py change (bench restart / supervisorctl restart -
same gotcha this module's README documents for custom_fields/doc_events changes).
"""

import frappe

from cannabis_management.manufacturing_timesheet_kiosk import custom_fields

MODULE = "Manufacturing Timesheet Kiosk"
DOCTYPES = ["kiosk_overtime_request", "kiosk_access_log"]


def run():
	frappe.set_user("Administrator")

	for dt in DOCTYPES:
		frappe.reload_doc(MODULE, "doctype", dt, force=True)
		print(f"reloaded doctype: {dt}")

	custom_fields.install()
	print("custom fields installed/updated")

	frappe.db.commit()
	print("Done. Restart the scheduler process for send_upcoming_cutoff_warnings to start firing.")
