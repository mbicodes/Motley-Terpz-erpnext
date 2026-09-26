"""Keep report records this app has taken over pointing at this app.

A Report's name is its primary key, so an app cannot add a second report
called "Item-wise Sales Register" -- it can only claim the one record. Which
app's code actually runs is decided by Report.module: Frappe resolves a
Script Report to <module's app>/<module>/report/<scrubbed name>/.

Both apps ship a file for that record, so `bench migrate` syncs both and the
loser is whichever synced first. This runs from after_migrate, after every
app has had its turn, so the record is left pointing here regardless of the
order they ran in. It is the same trick the workspace and notification
repairs in hooks.py use.

Disabling ERPNext's copy is not an option and not needed: there is one
record, not two, and the file it would disable is the same one this app is
claiming. Re-pointing the module is what takes the core version out of use.
"""

import frappe

CLAIMED_REPORTS = {
	# report name -> the module in this app that owns it
	"Item-wise Sales Register": "Cannabis Management",
}


def install():
	for report_name, module in CLAIMED_REPORTS.items():
		if not frappe.db.exists("Report", report_name):
			continue

		current = frappe.db.get_value(
			"Report", report_name, ["module", "disabled", "report_type"], as_dict=True
		)
		updates = {}
		if current.module != module:
			updates["module"] = module
		# A disabled record would hide this app's version too, since it is the
		# same record -- make sure nothing left it switched off.
		if current.disabled:
			updates["disabled"] = 0
		if current.report_type != "Script Report":
			updates["report_type"] = "Script Report"

		if updates:
			frappe.db.set_value("Report", report_name, updates, update_modified=False)
			frappe.clear_cache(doctype="Report")
