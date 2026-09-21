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
	# NOTE: "AR Weekly Review" deliberately NOT listed here. A public workspace of
	# that name shadows the ar-weekly-review Page (frappe's router checks
	# frappe.workspaces[route[0]] before page routes, router.js:181) - but a
	# *private* stub of that name is what stops browsers with a stale
	# localStorage.current_page from popping "Workspace AR Weekly Review not
	# found" on every desk load. The stub is public=0 / for_user="__route-stub__",
	# so it stays out of get_workspace_sidebar_items()'s `pages` - the only list
	# frappe.workspaces is built from - and therefore cannot shadow the page.
	# Deleting it here would bring the dialog back on the next migrate.
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

# ── /app/ar-weekly-review ────────────────────────────────────────────────────

AR_WEEKLY_STUB = "AR Weekly Review"
# Not a real user, so the stub is nobody's private workspace and shows to no one.
AR_WEEKLY_STUB_USER = "__route-stub__"


def ensure_ar_weekly_review_stub():
    """Keep /app/ar-weekly-review rendering the Page, with no error dialog.

    Two separate failure modes, both of which have bitten live, and both of which
    this heals on every migrate:

    1. **No Workspace of that name at all** -> browsers that still hold
       ``localStorage.current_page = "AR Weekly Review"`` (set while a workspace of
       that name briefly existed) call get_desktop_page for it on every desk load.
       That raises DoesNotExistError; desktop.py catches the exception but the
       message has already been queued by frappe.throw, so the user gets a
       "Workspace AR Weekly Review not found" dialog forever. A doc of that name
       makes the call succeed quietly. localStorage is per browser and cannot be
       cleared from here, which is why the fix has to live server-side.

    2. **A *public* Workspace of that name** -> it shadows the Page completely.
       frappe's router tests frappe.workspaces[route[0]] before page routes
       (router.js:181), and frappe.workspaces is built only from the public
       ``pages`` list, so a public workspace wins the slug and the page becomes
       unreachable. This is what happened on 2026-09-19.

    So the invariant is: a doc named "AR Weekly Review" must EXIST and must NOT be
    public. Anything else gets corrected here.

    Note it must never be added to REMOVED_WORKSPACES - that would delete the stub
    and bring failure mode 1 back.
    """
    if frappe.db.exists("Workspace", AR_WEEKLY_STUB):
        # Present. Only thing that matters is that it is not public.
        if frappe.db.get_value("Workspace", AR_WEEKLY_STUB, "public"):
            # Demoted with db.set_value, not doc.save(): saving re-runs
            # validate_route_conflict, which compares slug(self.name) against
            # every Page name when the title is unchanged - and the Page already
            # owns "ar-weekly-review", so a normal save raises NameError.
            frappe.db.set_value(
                "Workspace",
                AR_WEEKLY_STUB,
                {"public": 0, "for_user": AR_WEEKLY_STUB_USER, "is_hidden": 1},
                update_modified=False,
            )
            frappe.db.commit()
            frappe.clear_cache()
            print(f"Demoted Workspace {AR_WEEKLY_STUB} to private so it stops shadowing the page")
        return

    frappe.get_doc(
        {
            "doctype": "Workspace",
            # name comes from `label` (autoname: field:label) - it is the exact
            # string the stale browser lookup asks for.
            "label": AR_WEEKLY_STUB,
            # The title must NOT slug to "ar-weekly-review" or
            # validate_route_conflict rejects the insert: the Page owns that route.
            "title": f"{AR_WEEKLY_STUB} (route stub)",
            "public": 0,
            "for_user": AR_WEEKLY_STUB_USER,
            "is_hidden": 1,
            "content": "[]",
            # Leave module empty: a module the caller cannot access makes
            # get_desktop_page raise PermissionError, i.e. a different dialog.
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.clear_cache()
    print(f"Created private route stub Workspace {AR_WEEKLY_STUB}")
