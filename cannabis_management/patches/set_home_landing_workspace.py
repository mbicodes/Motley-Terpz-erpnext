import frappe

from cannabis_management.home_hub_block import WORKSPACE, install_home_hub

OLD_DEFAULT = "USA Payroll"
SERVER_SCRIPT = "Default Workspace"


def execute():
	install_home_hub()

	if frappe.db.exists("Server Script", SERVER_SCRIPT):
		script = frappe.get_doc("Server Script", SERVER_SCRIPT)
		if f'"{OLD_DEFAULT}"' in (script.script or ""):
			script.script = script.script.replace(f'"{OLD_DEFAULT}"', f'"{WORKSPACE}"')
			script.save(ignore_permissions=True)

	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User"},
		fields=["name", "default_workspace"],
	)
	for user in users:
		if (user.default_workspace or "") in ("", OLD_DEFAULT):
			frappe.db.set_value("User", user.name, "default_workspace", WORKSPACE, update_modified=False)
	frappe.clear_cache()
