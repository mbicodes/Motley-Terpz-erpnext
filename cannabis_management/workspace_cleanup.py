"""Keep unwanted standard workspaces out of the desk sidebar.

`is_hidden` is not enough: `get_workspace_sidebar_items()` in
frappe/desk/desktop.py drops all filters (including is_hidden) for users with
`has_access` (System Manager / Workspace Manager), so hidden standard pages keep
showing up for admins.  The only thing that actually removes them is deleting
the Workspace record.

Standard workspaces ship as JSON fixtures inside their app
(<app>/<module>/workspace/<name>/<name>.json) and `frappe.model.sync` re-imports
them on every `bench migrate`, which resurrects anything we delete.  Hence the
after_migrate hook that re-runs this cleanup.
"""

import frappe

# Workspace docnames to keep out of the sidebar.
REMOVED_WORKSPACES = [
	# A DB-only workspace with this exact name was created on live on 2026-09-19
	# and SHADOWED the ar-weekly-review Page: frappe's router checks
	# frappe.workspaces[route[0]] before page routes (router.js:181), so
	# /app/ar-weekly-review rendered a card of shortcuts instead of the page.
	# Listed here so it cannot come back and hide the page again.
	"AR Weekly Review",
	"Stock",
	"Assets",
	"Projects",
	"Users",
	"Payroll",
	"Website",
	"Tools",
	"ERPNext Settings",
	"Integrations",
	"ERPNext Integrations",
]


def remove_unwanted_workspaces():
	"""Delete the workspaces listed in REMOVED_WORKSPACES, if present."""
	deleted = []

	for name in REMOVED_WORKSPACES:
		if not frappe.db.exists("Workspace", name):
			continue
		try:
			frappe.delete_doc("Workspace", name, ignore_permissions=True, force=True)
			deleted.append(name)
		except Exception:
			frappe.log_error(
				title="Workspace cleanup failed", message=f"Could not delete Workspace {name}"
			)

	if deleted:
		frappe.db.commit()
		frappe.clear_cache()
		print(f"Removed workspaces from sidebar: {', '.join(deleted)}")

	return deleted
