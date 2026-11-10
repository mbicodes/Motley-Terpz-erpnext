import frappe

ROLE = "Lab Dashboard"
OLD_ROLE = "Operations Scorecard"
OLD_PAGE = "operations-scorecard"
SAMPLES_TYPE = "Samples"


def execute():
	if frappe.db.exists("Role", OLD_ROLE) and not frappe.db.exists("Role", ROLE):
		frappe.rename_doc("Role", OLD_ROLE, ROLE, force=True)
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	if not frappe.db.exists("Warehouse Type", SAMPLES_TYPE):
		frappe.get_doc({
			"doctype": "Warehouse Type",
			"description": "Samples held for partners; shown on Matt's Lab Dashboard",
		}).insert(ignore_permissions=True, set_name=SAMPLES_TYPE)
	if frappe.db.exists("Page", OLD_PAGE):
		frappe.delete_doc("Page", OLD_PAGE, force=True, ignore_permissions=True)
