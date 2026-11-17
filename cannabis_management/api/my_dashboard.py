"""My Dashboard — a per-user page of shortcuts that an administrator picks.

Two halves:

* **Setup** (`my-dashboard-setup` page, System Manager only): pick a user, then
  choose from every workspace, dashboard, page, report and DocType on the site —
  ours and the ones ERPNext ships — plus free-form links.
* **My Dashboard** (public workspace of that name, in everyone's sidebar): shows
  the signed-in user the shortcuts chosen for them.

Unlike the Home hub (`api/home_hub.py`), which lists only what this bench built,
the catalogue here is deliberately *everything*: the administrator is choosing a
handful of items per person, so the breadth is the point.

Picking a shortcut does **not** grant access. A tile whose target the user cannot
open is left off their dashboard, and the setup page flags it so the administrator
knows a role is missing. All access checks take an explicit user, because the
setup page asks "can *that* user open this?" while signed in as someone else —
which Frappe's own helpers (`get_allowed_pages` and friends) cannot answer, since
they only ever look at the session user.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, get_fullname, quoted

from cannabis_management.api.home_hub import is_custom

SETUP_DOCTYPE = "My Dashboard Setup"
WORKSPACE = "My Dashboard"
SETUP_PAGE = "my-dashboard-setup"

# Display order of the groups on a user's dashboard.
TYPES = ["Workspace", "Dashboard", "Page", "Report", "DocType", "URL"]
GROUP_LABELS = {
	"Workspace": "Workspaces",
	"Dashboard": "Dashboards",
	"Page": "Pages",
	"Report": "Reports",
	"DocType": "Lists & Forms",
	"URL": "Links",
}

# Never offered as shortcuts: the dashboard itself and Frappe's onboarding stub.
EXCLUDED_WORKSPACES = {WORKSPACE, "Welcome Workspace"}

MANAGER_ROLES = {"System Manager", "Workspace Manager"}


def _slug(name: str) -> str:
	"""Same rule as `frappe.router.slug` on the client."""
	return (name or "").lower().replace(" ", "-")


def _can_setup(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def _only_admin():
	if not _can_setup():
		frappe.throw(_("Only an administrator can set up dashboards."), frappe.PermissionError)


# ── catalogue ────────────────────────────────────────────────────────────────


def _catalog() -> dict:
	"""Every linkable thing on the site, keyed by (type, name).

	Built once per request: both the setup page and a user's dashboard resolve
	labels and routes through it.
	"""
	if hasattr(frappe.local, "_my_dashboard_catalog"):
		return frappe.local._my_dashboard_catalog

	catalog: dict = {}

	def add(item_type, name, label, route, module, sub=None, **extra):
		catalog[(item_type, name)] = {
			"type": item_type,
			"name": name,
			"label": label or name,
			"route": route,
			"module": module or "",
			"sub": sub,
			"custom": is_custom(module),
			**extra,
		}

	for row in frappe.get_all(
		"Workspace",
		filters={"public": 1},
		fields=["name", "title", "module", "is_hidden"],
		ignore_permissions=True,
	):
		if row.name in EXCLUDED_WORKSPACES:
			continue
		add(
			"Workspace",
			row.name,
			row.title or row.name,
			"/app/" + _slug(row.title or row.name),
			row.module,
			sub=_("Hidden") if row.is_hidden else None,
			hidden=cint(row.is_hidden),
		)

	for row in frappe.get_all(
		"Dashboard", fields=["name", "dashboard_name", "module"], ignore_permissions=True
	):
		add(
			"Dashboard",
			row.name,
			row.dashboard_name or row.name,
			"/app/dashboard-view/" + quoted(row.name),
			row.module,
		)

	for row in frappe.get_all("Page", fields=["name", "title", "module"], ignore_permissions=True):
		add("Page", row.name, row.title or row.name, "/app/" + row.name, row.module)

	for row in frappe.get_all(
		"Report",
		filters={"disabled": 0},
		fields=["name", "report_type", "ref_doctype", "module"],
		ignore_permissions=True,
	):
		if row.report_type == "Report Builder":
			if not row.ref_doctype:
				continue
			route = "/app/{0}/view/report/{1}".format(_slug(row.ref_doctype), quoted(row.name))
		else:
			route = "/app/query-report/" + quoted(row.name)
		add(
			"Report",
			row.name,
			row.name,
			route,
			row.module,
			sub=row.report_type,
			ref_doctype=row.ref_doctype,
		)

	for row in frappe.get_all(
		"DocType",
		filters={"istable": 0},
		fields=["name", "module", "issingle"],
		ignore_permissions=True,
	):
		add(
			"DocType",
			row.name,
			row.name,
			"/app/" + _slug(row.name),
			row.module,
			sub=_("Settings") if row.issingle else None,
		)

	frappe.local._my_dashboard_catalog = catalog
	return catalog


@frappe.whitelist()
def get_catalog():
	"""Everything an administrator can pick from."""
	_only_admin()
	items = sorted(_catalog().values(), key=lambda item: (TYPES.index(item["type"]), item["label"].lower()))
	return {
		"types": [{"key": key, "label": _(GROUP_LABELS[key])} for key in TYPES if key != "URL"],
		"items": [
			{key: item.get(key) for key in ("type", "name", "label", "module", "sub", "custom")}
			for item in items
		],
	}


# ── access, for an explicit user ─────────────────────────────────────────────


class Access:
	"""Can `user` open a given item? Mirrors Frappe's own rules per type.

	Lookups are loaded lazily and once, so checking a whole dashboard costs a
	handful of queries however many tiles it has.
	"""

	def __init__(self, user: str):
		self.user = user
		self.is_admin = user == "Administrator"
		self.roles = set(frappe.get_roles(user))
		self._has_role = None
		self._custom_roles = None
		self._blocked_modules = None
		self._doctype_perm: dict = {}
		self._chart_ok: dict | None = None

	# lookups ---------------------------------------------------------------

	def _load_roles(self):
		if self._has_role is not None:
			return
		self._has_role = {}
		for row in frappe.get_all(
			"Has Role",
			filters={"parenttype": ("in", ["Page", "Report", "Workspace", "Custom Role"])},
			fields=["parent", "parenttype", "role"],
			ignore_permissions=True,
		):
			self._has_role.setdefault((row.parenttype, row.parent), set()).add(row.role)

		# A Custom Role record replaces the standard role table of its page/report.
		self._custom_roles = {}
		for row in frappe.get_all("Custom Role", fields=["name", "page", "report"], ignore_permissions=True):
			roles = self._has_role.get(("Custom Role", row.name), set())
			if row.page:
				self._custom_roles.setdefault(("Page", row.page), set()).update(roles)
			if row.report:
				self._custom_roles.setdefault(("Report", row.report), set()).update(roles)

	def _role_table_allows(self, parenttype: str, name: str) -> bool:
		"""`frappe.boot.get_user_pages_or_reports`, for one item and any user."""
		self._load_roles()
		standard = self._has_role.get((parenttype, name), set())
		if not standard:
			return True  # nothing configured means open to everyone
		custom = self._custom_roles.get((parenttype, name))
		if custom is not None:
			return bool(custom & self.roles)
		return bool(standard & self.roles)

	def _can(self, doctype: str, ptype: str = "read") -> bool:
		key = (doctype, ptype)
		if key not in self._doctype_perm:
			try:
				self._doctype_perm[key] = bool(frappe.has_permission(doctype, ptype, user=self.user))
			except Exception:
				self._doctype_perm[key] = False
		return self._doctype_perm[key]

	# per type --------------------------------------------------------------

	def allowed(self, entry: dict) -> bool:
		if self.is_admin:
			return True
		check = getattr(self, "_" + entry["type"].lower(), None)
		try:
			return bool(check(entry)) if check else True
		except Exception:
			frappe.log_error(frappe.get_traceback(), "My Dashboard access check failed")
			return False

	def _url(self, entry):
		return True

	def _page(self, entry):
		return self._role_table_allows("Page", entry["name"])

	def _report(self, entry):
		if not self._can("Report"):
			return False
		if not self._role_table_allows("Report", entry["name"]):
			return False
		ref_doctype = entry.get("ref_doctype")
		return self._can(ref_doctype, "report") if ref_doctype else True

	def _doctype(self, entry):
		return self._can(entry["name"])

	def _workspace(self, entry):
		# Frappe leaves hidden workspaces out of the sidebar payload for everyone
		# except workspace managers, so for anyone else the route does not exist.
		if entry.get("hidden") and not (self.roles & MANAGER_ROLES):
			return False

		if self._blocked_modules is None:
			self._blocked_modules = set(
				frappe.get_all("Block Module", filters={"parent": self.user}, pluck="module", ignore_permissions=True)
			)
		if entry.get("module") and entry["module"] in self._blocked_modules:
			return False

		self._load_roles()
		allowed = set(self._has_role.get(("Workspace", entry["name"]), set()))
		allowed |= self._custom_roles.get(("Page", entry["name"]), set())
		return not allowed or bool(allowed & self.roles)

	def _dashboard(self, entry):
		"""Readable only if the data behind at least one of its charts is."""
		if not self._can("Dashboard"):
			return False

		charts = frappe.get_all(
			"Dashboard Chart Link",
			filters={"parent": entry["name"], "parenttype": "Dashboard"},
			pluck="chart",
			ignore_permissions=True,
		)
		if not charts:
			return True
		return any(self._chart_allowed(chart) for chart in charts)

	def _chart_allowed(self, chart: str) -> bool:
		if self._chart_ok is None:
			self._chart_ok = {
				row.name: row
				for row in frappe.get_all(
					"Dashboard Chart",
					fields=["name", "document_type", "chart_type", "report_name"],
					ignore_permissions=True,
				)
			}
		row = self._chart_ok.get(chart)
		if not row:
			return False
		# Most charts on this site are built on a report, not a DocType.
		if row.chart_type == "Report" or (not row.document_type and row.report_name):
			report = _catalog().get(("Report", row.report_name))
			return bool(report) and self._report(report)
		if not row.document_type:
			return True
		return self._can(row.document_type)


# ── reading a setup ──────────────────────────────────────────────────────────


def _stored_items(user: str) -> list[dict]:
	if not frappe.db.exists(SETUP_DOCTYPE, user):
		return []
	return frappe.get_all(
		"My Dashboard Item",
		filters={"parent": user, "parenttype": SETUP_DOCTYPE},
		fields=["item_type", "link_name", "label", "pinned_by_user"],
		order_by="idx asc",
		ignore_permissions=True,
	)


def _resolve(row: dict, access: Access) -> dict:
	"""A stored row plus where it leads and whether this user can open it."""
	resolved = _resolve_row(row, access)
	resolved["pinned"] = cint(row.get("pinned_by_user"))
	return resolved


def _resolve_row(row: dict, access: Access) -> dict:
	item_type, name = row["item_type"], row["link_name"]

	if item_type == "URL":
		return {
			"type": "URL",
			"name": name,
			"label": row.get("label") or name,
			"custom_label": row.get("label") or "",
			"route": name,
			"module": "",
			"sub": None,
			"exists": True,
			"allowed": True,
		}

	entry = _catalog().get((item_type, name))
	if not entry:
		# Renamed, deleted or disabled since it was picked.
		return {
			"type": item_type,
			"name": name,
			"label": row.get("label") or name,
			"custom_label": row.get("label") or "",
			"route": None,
			"module": "",
			"sub": None,
			"exists": False,
			"allowed": False,
		}

	return {
		"type": item_type,
		"name": name,
		"label": row.get("label") or entry["label"],
		"custom_label": row.get("label") or "",
		"default_label": entry["label"],
		"route": entry["route"],
		"module": entry["module"],
		"sub": entry["sub"],
		"exists": True,
		"allowed": access.allowed(entry),
	}


@frappe.whitelist()
def get_my_dashboard():
	"""The signed-in user's shortcuts, grouped by type, minus what they cannot open."""
	user = frappe.session.user
	access = Access(user)
	stored = _stored_items(user)
	resolved = [_resolve(row, access) for row in stored]
	usable = [item for item in resolved if item["exists"] and item["allowed"]]

	groups = []
	for item_type in TYPES:
		items = [
			{key: item[key] for key in ("label", "route", "module", "sub", "type", "name", "pinned")}
			for item in usable
			if item["type"] == item_type
		]
		if items:
			groups.append({"key": item_type, "label": _(GROUP_LABELS[item_type]), "items": items})

	return {
		"user": user,
		"full_name": get_fullname(user),
		"can_setup": _can_setup(user),
		"setup_route": "/app/" + SETUP_PAGE,
		"configured": bool(stored),
		"groups": groups,
	}


# ── setup page ───────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_users():
	"""Desk users, with how many shortcuts each already has."""
	_only_admin()

	counts = dict(
		frappe.db.sql(
			"""select parent, count(*) from `tabMy Dashboard Item`
			where parenttype = %s group by parent""",
			SETUP_DOCTYPE,
		)
	)
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ("not in", ["Guest"])},
		fields=["name", "full_name", "user_image", "role_profile_name"],
		order_by="full_name asc",
		ignore_permissions=True,
	)
	for user in users:
		user["count"] = cint(counts.get(user.name))
	return users


@frappe.whitelist()
def get_setup(user: str):
	"""One user's shortcuts, each flagged with whether that user can open it."""
	_only_admin()
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} not found").format(user))

	access = Access(user)
	return {
		"user": user,
		"full_name": get_fullname(user),
		"items": [_resolve(row, access) for row in _stored_items(user)],
	}


@frappe.whitelist()
def check_access(user: str, items):
	"""Access flags for shortcuts that are picked but not yet saved."""
	_only_admin()
	access = Access(user)
	return [_resolve(row, access) for row in _clean(items)]


def _clean(items) -> list[dict]:
	"""Validate and de-duplicate rows coming from the browser."""
	if isinstance(items, str):
		items = json.loads(items or "[]")

	seen = set()
	cleaned = []
	for row in items or []:
		item_type = (row.get("item_type") or row.get("type") or "").strip()
		name = (row.get("link_name") or row.get("name") or "").strip()
		label = (row.get("label") or "").strip()

		if item_type not in TYPES:
			frappe.throw(_("Unknown shortcut type: {0}").format(item_type))
		if not name:
			continue
		if item_type == "URL" and not (name.startswith("/") or name.startswith(("http://", "https://"))):
			frappe.throw(_("Link {0} must start with / or http(s)://").format(name))
		if (item_type, name) in seen:
			continue

		seen.add((item_type, name))
		cleaned.append(
			{
				"item_type": item_type,
				"link_name": name,
				"label": label,
				"pinned_by_user": cint(row.get("pinned_by_user") or row.get("pinned")),
			}
		)
	return cleaned


def _write(user: str, rows: list[dict]):
	exists = frappe.db.exists(SETUP_DOCTYPE, user)
	if not rows:
		if exists:
			frappe.delete_doc(SETUP_DOCTYPE, user, ignore_permissions=True)
		return

	doc = frappe.get_doc(SETUP_DOCTYPE, user) if exists else frappe.new_doc(SETUP_DOCTYPE)
	doc.user = user
	doc.set("items", rows)
	doc.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def save_setup(user: str, items):
	"""Replace a user's shortcuts. An empty list clears their dashboard."""
	_only_admin()
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} not found").format(user))

	_write(user, _clean(items))
	return get_setup(user)


@frappe.whitelist(methods=["POST"])
def copy_setup(source: str, targets):
	"""Give other users the same shortcuts as `source`, replacing what they had."""
	_only_admin()
	if isinstance(targets, str):
		targets = json.loads(targets or "[]")

	rows = [dict(row) for row in _stored_items(source)]
	if not rows:
		frappe.throw(_("{0} has no saved shortcuts to copy. Save first.").format(source))

	done = []
	for target in targets or []:
		if target == source or not frappe.db.exists("User", target):
			continue
		_write(target, [dict(row) for row in rows])
		done.append(target)
	return done


# ── widgets ──────────────────────────────────────────────────────────────────
#
# The top of My Dashboard: a clock (drawn in the browser), the user's open tasks
# and recently visited pages. No business figures here by design: sales and AR
# numbers live on their own dashboards. Cached per user for a few minutes.

WIDGET_TTL = 300


def _todos(user) -> tuple[list[dict], int]:
	from frappe.utils import strip_html

	filters = {"allocated_to": user, "status": "Open"}
	total = frappe.db.count("ToDo", filters)
	rows = frappe.get_all(
		"ToDo",
		filters=filters,
		fields=["name", "description", "reference_type", "reference_name", "date", "priority"],
		order_by="date is null, date asc, creation desc",
		limit_page_length=6,
	)
	items = []
	for row in rows:
		if row.reference_type and row.reference_name:
			route = "/app/{0}/{1}".format(_slug(row.reference_type), quoted(row.reference_name))
		else:
			route = "/app/todo/" + row.name
		items.append(
			{
				"text": (strip_html(row.description or "") or row.reference_name or row.name).strip()[:120],
				"ref": " · ".join(filter(None, [row.reference_type, row.reference_name])),
				"date": str(row.date) if row.date else None,
				"priority": row.priority,
				"route": route,
			}
		)
	return items, total


def _recent(user) -> list[dict]:
	"""Distinct pages the user opened lately, newest first, from Route History."""
	rows = frappe.get_all(
		"Route History",
		filters={"user": user},
		fields=["route", "creation"],
		order_by="creation desc",
		limit_page_length=80,
	)
	seen, items = set(), []
	for row in rows:
		parts = (row.route or "").split("/")
		head = parts[0] if parts else ""
		item = None
		if head == "Form" and len(parts) >= 3:
			item = (parts[2], parts[1], "/app/{0}/{1}".format(_slug(parts[1]), quoted("/".join(parts[2:]))))
		elif head == "List" and len(parts) >= 2:
			view = parts[2] if len(parts) > 2 else "List"
			if view == "Report" and len(parts) > 3:
				item = (parts[3], _("Report"), "/app/{0}/view/report/{1}".format(_slug(parts[1]), quoted(parts[3])))
			else:
				item = (parts[1], _("List"), "/app/" + _slug(parts[1]))
		elif head == "query-report" and len(parts) > 1:
			item = (parts[1], _("Report"), "/app/query-report/" + quoted(parts[1]))
		elif head == "dashboard-view" and len(parts) > 1:
			item = (parts[1], _("Dashboard"), "/app/dashboard-view/" + quoted(parts[1]))
		elif head == "Workspaces" and len(parts) == 2 and parts[1] != WORKSPACE:
			item = (parts[1], _("Workspace"), "/app/" + _slug(parts[1]))
		elif len(parts) == 1 and head and head not in (SETUP_PAGE,):
			entry = _catalog().get(("Page", head))
			if entry:
				item = (entry["label"], _("Page"), entry["route"])
		if not item or item[2] in seen:
			continue
		seen.add(item[2])
		items.append({"label": item[0], "sub": item[1], "route": item[2]})
		if len(items) == 6:
			break
	return items


@frappe.whitelist()
def get_widgets(refresh: int = 0):
	"""Everything above the shortcuts on My Dashboard, for the session user."""
	user = frappe.session.user
	key = f"my_dashboard_widgets:v2::{user}"
	if not cint(refresh):
		cached = frappe.cache.get_value(key)
		if cached:
			return cached

	out = {"todos": [], "todo_total": 0, "recent": []}

	def safe(fn, *args):
		try:
			return fn(*args)
		except Exception:
			frappe.log_error(f"My Dashboard widget {fn.__name__}", frappe.get_traceback())
			return None

	todos = safe(_todos, user)
	if todos:
		out["todos"], out["todo_total"] = todos

	out["recent"] = safe(_recent, user) or []
	out["generated"] = frappe.utils.now()

	frappe.cache.set_value(key, out, expires_in_sec=WIDGET_TTL)
	return out


# ── pin button (any user, own dashboard only) ────────────────────────────────
#
# Every desk page carries a pin button (public/js/my_dashboard.js). Pinning adds
# the page to the signed-in user's own My Dashboard Setup; there is no way to
# touch anyone else's record from here. The client sends Frappe's route array;
# it is resolved to a typed shortcut (Report, Page, ...) where the route names
# one, so the tile gets the right group and icon, and otherwise kept as a link.

NOT_PINNABLE_PAGES = {SETUP_PAGE}


def _norm(path: str) -> str:
	"""How two routes are compared: decoded, no query string or trailing slash."""
	from urllib.parse import unquote

	return unquote(path or "").split("?")[0].split("#")[0].rstrip("/").lower()


def _route_to_item(route: list, path: str) -> tuple[str, str]:
	"""(item_type, link_name) for a desk route; URL when it is not a catalogue item."""
	catalog = _catalog()
	parts = [str(part) for part in (route or [])]
	head = parts[0] if parts else ""
	key = None

	if head == "query-report" and len(parts) > 1:
		key = ("Report", parts[1])
	elif head == "dashboard-view" and len(parts) > 1:
		key = ("Dashboard", parts[1])
	elif head == "Workspaces" and len(parts) == 2:
		title = parts[1]
		key = next(
			(k for k, entry in catalog.items() if k[0] == "Workspace" and title in (k[1], entry["label"])),
			None,
		)
	elif head == "List" and len(parts) > 1:
		view = parts[2] if len(parts) > 2 else "List"
		if view == "Report" and len(parts) > 3:
			key = ("Report", parts[3])
		elif view == "List":
			key = ("DocType", parts[1])
	elif head == "Form" and len(parts) == 3 and parts[1] == parts[2]:
		key = ("DocType", parts[1])  # a Single, such as Selling Settings
	elif len(parts) == 1:
		key = ("Page", parts[0])

	if key and key in catalog:
		return key
	return ("URL", path)


def _my_setup_doc():
	user = frappe.session.user
	if frappe.db.exists(SETUP_DOCTYPE, user):
		return frappe.get_doc(SETUP_DOCTYPE, user)
	doc = frappe.new_doc(SETUP_DOCTYPE)
	doc.user = user
	return doc


def _my_pins() -> list[str]:
	"""Normalised routes of everything on the session user's dashboard."""
	routes = []
	for row in _stored_items(frappe.session.user):
		if row.item_type == "URL":
			routes.append(_norm(row.link_name))
			continue
		entry = _catalog().get((row.item_type, row.link_name))
		if entry:
			routes.append(_norm(entry["route"]))
	return routes


@frappe.whitelist()
def get_my_pins():
	return _my_pins()


@frappe.whitelist(methods=["POST"])
def pin(route, path: str, title: str | None = None):
	"""Add the page the user is on to their own My Dashboard."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	if isinstance(route, str):
		route = json.loads(route or "[]")

	path = (path or "").split("#")[0]
	if not path.startswith("/app/"):
		frappe.throw(_("Only desk pages can be pinned."))
	if route and route[0] in NOT_PINNABLE_PAGES or (route and route[-1] == WORKSPACE):
		frappe.throw(_("This page cannot be pinned."))

	item_type, name = _route_to_item(route, path)

	if item_type != "URL":
		entry = _catalog()[(item_type, name)]
		if not Access(frappe.session.user).allowed(entry):
			frappe.throw(_("You do not have access to {0}.").format(entry["label"]), frappe.PermissionError)
		label = ""
	else:
		label = (title or "").strip()[:140] or path

	doc = _my_setup_doc()
	target = _norm(_catalog()[(item_type, name)]["route"] if item_type != "URL" else name)
	if target not in _my_pins():
		doc.append(
			"items",
			{"item_type": item_type, "link_name": name, "label": label, "pinned_by_user": 1},
		)
		doc.save(ignore_permissions=True)

	return _my_pins()


@frappe.whitelist(methods=["POST"])
def unpin(path: str | None = None, item_type: str | None = None, link_name: str | None = None):
	"""Remove a shortcut from the user's own My Dashboard, by route or by key."""
	if not frappe.db.exists(SETUP_DOCTYPE, frappe.session.user):
		return []

	doc = frappe.get_doc(SETUP_DOCTYPE, frappe.session.user)
	wanted = _norm(path) if path else None

	def matches(row):
		if item_type and link_name:
			return row.item_type == item_type and row.link_name == link_name
		if row.item_type == "URL":
			return _norm(row.link_name) == wanted
		entry = _catalog().get((row.item_type, row.link_name))
		return bool(entry) and _norm(entry["route"]) == wanted

	keep = [row for row in doc.items if not matches(row)]
	if len(keep) != len(doc.items):
		if keep:
			doc.set("items", keep)
			doc.save(ignore_permissions=True)
		else:
			frappe.delete_doc(SETUP_DOCTYPE, doc.name, ignore_permissions=True)

	return _my_pins()


# ── install ──────────────────────────────────────────────────────────────────

BLOCK_HTML = '<div class="my-dashboard-root"></div>'

# Kept to one line on purpose: the real code lives in public/js/my_dashboard.js,
# so it is versioned with the app instead of sitting in a database row.
BLOCK_SCRIPT = (
	"if (window.cannabis_management && cannabis_management.my_dashboard) {"
	" cannabis_management.my_dashboard.render(root_element); }"
)


def install():
	"""Create the My Dashboard workspace and its block. Safe to re-run.

	Records are created here rather than shipped as fixtures, so later edits made
	on the site (icon, position in the sidebar) are never overwritten.
	"""
	if not frappe.db.exists("Custom HTML Block", WORKSPACE):
		block = frappe.new_doc("Custom HTML Block")
		block.name = WORKSPACE
		block.private = 0
		block.html = BLOCK_HTML
		block.script = BLOCK_SCRIPT
		block.insert(ignore_permissions=True, set_name=WORKSPACE)
	else:
		frappe.db.set_value(
			"Custom HTML Block", WORKSPACE, {"html": BLOCK_HTML, "script": BLOCK_SCRIPT}
		)

	if not frappe.db.exists("Workspace", WORKSPACE):
		workspace = frappe.new_doc("Workspace")
		workspace.update(
			{
				"label": WORKSPACE,
				"title": WORKSPACE,
				"public": 1,
				"is_hidden": 0,
				"icon": "dashboard",
				# No module: a public workspace with a module is exported to an app
				# folder on every save in developer mode, and a user's Block Modules
				# could then hide it.
				"module": "",
				"sequence_id": 0.5,
				"content": json.dumps(
					[
						{
							"id": "my_dashboard_block",
							"type": "custom_block",
							"data": {"custom_block_name": WORKSPACE, "col": 12},
						}
					]
				),
			}
		)
		workspace.append("custom_blocks", {"custom_block_name": WORKSPACE, "label": WORKSPACE})
		workspace.insert(ignore_permissions=True)

	frappe.db.commit()
