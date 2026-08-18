"""The Home hub — one landing page listing everything a user is allowed to open.

Built dynamically rather than as a wall of static Workspace Shortcuts, for three
reasons:

* **Scale.** The site carries ~260 reports, ~46 pages, ~59 workspaces and ~16
  dashboards. Pinning those as shortcuts means a 380-entry `content` blob that
  nobody will maintain, and every new report would need adding by hand.
* **Permissions.** Frappe filters `DocType`, `Page` and `Report` shortcuts, but
  **`Dashboard` and `URL` shortcuts are never filtered** — and a Workspace can
  only be linked as a `URL`. A static list would therefore show every user every
  workspace on the site, which is the opposite of what was asked for.
* **Freshness.** This reads the live permission tables on every load, so a role
  change is reflected immediately.

Administrator sees everything **that this bench built** — the permission layer
short-circuits for it, but the custom-only filter below still applies, because
the point of the hub is our own tooling rather than the whole ERPNext catalogue.

**Only custom work is listed.** An item counts as ours when its module belongs to
an app in `CUSTOM_APPS`, or when it has no module at all (built in the UI, so it
was made here by definition). Everything shipped by frappe, erpnext, hrms, crm
and friends is left out — those are reachable from their own workspaces and would
bury the handful of things people actually came here for. On this site that is
the difference between ~420 entries and ~90.

Note that `is_standard` is *not* the discriminator: the Credit & AR reports are
standard files inside our own app, so they carry `is_standard = "Yes"` and would
be wrongly dropped.
"""

import frappe
from frappe import _
from frappe.boot import get_allowed_pages, get_allowed_reports
from frappe.desk.desktop import Workspace

# The hub itself, and Frappe's onboarding placeholder, are never listed.
EXCLUDED_WORKSPACES = {"Home", "Welcome Workspace"}

# Apps whose work is "ours". Add to this if another custom app is installed.
CUSTOM_APPS = {"cannabis_management", "ai_sales_dashboard"}

REPORT_ROUTE = {
	"Query Report": "/app/query-report/{name}",
	"Script Report": "/app/query-report/{name}",
	"Custom Report": "/app/query-report/{name}",
}


def _custom_modules() -> tuple[set[str], set[str]]:
    """(modules owned by our apps, every module the bench knows about)."""
    rows = frappe.get_all("Module Def", fields=["name", "app_name"])
    owned = {row.name for row in rows if row.app_name in CUSTOM_APPS}
    known = {row.name for row in rows}
    return owned, known


def is_custom(module: str | None) -> bool:
    """Was this built here, rather than shipped by a vendor app?

    No module at all means it was created in the UI — which only happens on this
    site, so it is ours. A module with no `Module Def` is an orphan left behind
    by something built here too.
    """
    owned, known = _module_cache()
    if not module:
        return True
    if module not in known:
        return True
    return module in owned


def _module_cache():
    """Computed once per request — the hub touches it a few hundred times."""
    if not hasattr(frappe.local, "_home_hub_modules"):
        frappe.local._home_hub_modules = _custom_modules()
    return frappe.local._home_hub_modules


@frappe.whitelist()
def get_home_items():
	"""Everything the session user may open, grouped for the hub."""
	return {
		"user": frappe.session.user,
		"full_name": frappe.utils.get_fullname(frappe.session.user),
		"is_administrator": frappe.session.user == "Administrator",
		"groups": [
			{"key": "workspaces", "label": _("Workspaces"), "items": _workspaces()},
			{"key": "dashboards", "label": _("Dashboards"), "items": _dashboards()},
			{"key": "pages", "label": _("Pages"), "items": _pages()},
			{"key": "reports", "label": _("Reports"), "items": _reports()},
		],
	}


# ── workspaces ───────────────────────────────────────────────────────────────


def _workspaces() -> list[dict]:
	"""Mirrors Frappe's own sidebar rule: blocked modules out, roles honoured."""
	user = frappe.get_cached_doc("User", frappe.session.user)
	blocked = set(user.get_blocked_modules() or [])

	rows = frappe.get_all(
		"Workspace",
		fields=[
			"name",
			"title",
			"public",
			"module",
			"icon",
			"indicator_color",
			"for_user",
			"is_hidden",
			"parent_page",
			"sequence_id",
		],
		order_by="sequence_id asc, title asc",
		ignore_permissions=True,
	)

	items = []
	for row in rows:
		if row.name in EXCLUDED_WORKSPACES:
			continue
		if not is_custom(row.module):
			continue
		if row.module and row.module in blocked:
			continue
		if row.public and row.is_hidden:
			continue
		if not row.public and row.for_user != frappe.session.user:
			continue

		try:
			if not Workspace(row, True).is_permitted():
				continue
		except frappe.PermissionError:
			continue
		except Exception:
			# A malformed workspace must not take the whole hub down.
			frappe.log_error(frappe.get_traceback(), f"Home hub: workspace {row.name}")
			continue

		items.append(
			{
				"label": row.title or row.name,
				"route": "/app/{0}{1}".format(
					"" if row.public else "private/", frappe.scrub(row.title or row.name).replace("_", "-")
				),
				"module": row.module or _("General"),
				"icon": row.icon,
				"colour": row.indicator_color,
				"sub": _("under {0}").format(row.parent_page) if row.parent_page else None,
			}
		)

	return items


# ── pages ────────────────────────────────────────────────────────────────────


def _pages() -> list[dict]:
	allowed = get_allowed_pages(cache=True) or {}
	if not allowed:
		return []

	rows = frappe.get_all(
		"Page",
		filters={"name": ("in", list(allowed))},
		fields=["name", "title", "module"],
		ignore_permissions=True,
	)
	rows = [row for row in rows if is_custom(row.module)]

	return sorted(
		[
			{
				"label": row.title or row.name,
				"route": f"/app/{row.name}",
				"module": row.module or _("General"),
			}
			for row in rows
		],
		key=lambda item: item["label"].lower(),
	)


# ── reports ──────────────────────────────────────────────────────────────────


def _reports() -> list[dict]:
	allowed = get_allowed_reports(cache=True) or {}
	if not allowed:
		return []

	rows = frappe.get_all(
		"Report",
		filters={"name": ("in", list(allowed)), "disabled": 0},
		fields=["name", "report_name", "report_type", "ref_doctype", "module"],
		ignore_permissions=True,
	)

	items = []
	for row in rows:
		if not is_custom(row.module):
			continue
		# A report is only useful if its underlying DocType is readable.
		if row.ref_doctype and not frappe.has_permission(row.ref_doctype, "report"):
			continue

		route = REPORT_ROUTE.get(row.report_type)
		if route:
			target = route.format(name=frappe.utils.quoted(row.name))
		elif row.ref_doctype:
			target = "/app/{0}/view/report?report_name={1}".format(
				frappe.scrub(row.ref_doctype).replace("_", "-"), frappe.utils.quoted(row.name)
			)
		else:
			continue

		items.append(
			{
				"label": row.report_name or row.name,
				"route": target,
				"module": row.module or row.ref_doctype or _("General"),
				"sub": row.report_type,
			}
		)

	return sorted(items, key=lambda item: item["label"].lower())


# ── dashboards and charts ────────────────────────────────────────────────────


def _dashboards() -> list[dict]:
	"""Frappe never permission-filters Dashboard shortcuts, so it is done here.

	A dashboard is only listed when the user can actually read the data behind
	at least one of its charts. Reading the `Dashboard` DocType is not the same
	as being allowed to see what the charts are made of.
	"""
	if frappe.session.user == "Administrator":
		readable = None  # everything
	elif not frappe.has_permission("Dashboard", "read"):
		return []
	else:
		readable = _readable_chart_names()
		if not readable:
			return []

	rows = frappe.get_all(
		"Dashboard", fields=["name", "dashboard_name", "module"], ignore_permissions=True
	)

	links = frappe.get_all(
		"Dashboard Chart Link",
		fields=["parent", "chart"],
		filters={"parenttype": "Dashboard"},
		ignore_permissions=True,
	)
	charts_by_dashboard: dict[str, list[str]] = {}
	for link in links:
		charts_by_dashboard.setdefault(link.parent, []).append(link.chart)

	items = []
	for row in rows:
		if not is_custom(row.module):
			continue
		if readable is not None:
			charts = charts_by_dashboard.get(row.name) or []
			if not any(chart in readable for chart in charts):
				continue

		items.append(
			{
				"label": row.dashboard_name or row.name,
				"route": "/app/dashboard-view/{0}".format(frappe.utils.quoted(row.name)),
				"module": row.module or _("General"),
			}
		)

	return sorted(items, key=lambda item: item["label"].lower())


def _readable_chart_names() -> set[str]:
	"""Charts whose underlying DocType the user may read."""
	rows = frappe.get_all(
		"Dashboard Chart", fields=["name", "document_type"], ignore_permissions=True
	)

	allowed_doctypes: dict[str, bool] = {}
	names = set()
	for row in rows:
		doctype = row.document_type
		if not doctype:
			names.add(row.name)
			continue
		if doctype not in allowed_doctypes:
			allowed_doctypes[doctype] = frappe.has_permission(doctype, "read")
		if allowed_doctypes[doctype]:
			names.add(row.name)

	return names
