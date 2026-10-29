import frappe

from cannabis_management.home_hub_block import install_home_hub, set_default_workspace_for_users


def execute():
	install_home_hub()
	count = set_default_workspace_for_users()
	frappe.logger("home_hub").info(f"Home hub installed; default workspace set for {count} users.")
