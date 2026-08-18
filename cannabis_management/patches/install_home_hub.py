"""Rebuild the Home workspace as a permission-aware landing hub.

Creates the `Home Hub` Custom HTML Block, points the public `Home` workspace at
it, and sets every desk user's `default_workspace` to Home so that is where they
land after login. Idempotent.
"""

import frappe

from cannabis_management.home_hub_block import install_home_hub, set_default_workspace_for_users


def execute():
	install_home_hub()
	count = set_default_workspace_for_users()
	frappe.logger("home_hub").info(f"Home hub installed; default workspace set for {count} users.")
