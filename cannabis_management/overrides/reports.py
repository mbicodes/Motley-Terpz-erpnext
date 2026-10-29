import frappe

CLAIMED_REPORTS = {
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
		if current.disabled:
			updates["disabled"] = 0
		if current.report_type != "Script Report":
			updates["report_type"] = "Script Report"

		if updates:
			frappe.db.set_value("Report", report_name, updates, update_modified=False)
			frappe.clear_cache(doctype="Report")
