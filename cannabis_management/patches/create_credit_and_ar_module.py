import frappe

from cannabis_management.credit_and_ar.masters import install_roles

MODULE_NAME = "Credit and AR"


def execute():
	if not frappe.db.exists("Module Def", MODULE_NAME):
		frappe.get_doc(
			{
				"doctype": "Module Def",
				"module_name": MODULE_NAME,
				"app_name": "cannabis_management",
			}
		).insert(ignore_permissions=True)

	install_roles()
