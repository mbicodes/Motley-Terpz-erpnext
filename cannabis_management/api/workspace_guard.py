from json import dumps, loads

import frappe
from frappe.desk.desktop import (
	Workspace,
	get_desktop_page as _original_get_desktop_page,
	get_workspace_sidebar_items as _original_sidebar_items,
)


@frappe.whitelist()
def get_desktop_page(page):
	data = _original_get_desktop_page(page)

	try:
		shortcuts = (data or {}).get("shortcuts") or {}
		items = shortcuts.get("items") or []
		if items:
			shortcuts["items"] = [item for item in items if _is_allowed(item)]
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Workspace shortcut guard failed")

	return data


def _is_allowed(item) -> bool:
	if frappe.session.user == "Administrator":
		return True

	item_type = (item.get("type") or "").lower()

	if item_type == "url":
		return _url_allowed(item.get("url") or "")
	if item_type == "dashboard":
		return _dashboard_allowed(item.get("link_to"))
	if item_type == "report":
		return _report_allowed(item.get("link_to"))

	return True


def _report_allowed(name: str | None) -> bool:
	if not name:
		return True

	ref_doctype = _report_ref_doctypes().get(name)
	if not ref_doctype:
		return True

	return bool(frappe.has_permission(ref_doctype, "report"))


def _report_ref_doctypes() -> dict:
	if hasattr(frappe.local, "_ws_guard_reports"):
		return frappe.local._ws_guard_reports

	rows = frappe.get_all(
		"Report", fields=["name", "ref_doctype"], ignore_permissions=True
	)
	frappe.local._ws_guard_reports = {row.name: row.ref_doctype for row in rows}
	return frappe.local._ws_guard_reports


def _url_allowed(url: str) -> bool:
	if not url.startswith("/app/"):
		return True

	slug = url[len("/app/") :].strip("/")
	if not slug or "/" in slug:
		return True

	target = _workspace_by_slug().get(slug.lower())
	if not target:
		return True

	return _workspace_permitted(target)


def _workspace_by_slug() -> dict:
	if hasattr(frappe.local, "_ws_guard_slugs"):
		return frappe.local._ws_guard_slugs

	rows = frappe.get_all(
		"Workspace",
		fields=["name", "title", "module", "public", "for_user", "is_hidden"],
		ignore_permissions=True,
	)
	slugs = {}
	for row in rows:
		slug = frappe.scrub(row.title or row.name).replace("_", "-").lower()
		slugs[slug] = row

	frappe.local._ws_guard_slugs = slugs
	return slugs


def _workspace_permitted(row) -> bool:
	if not row.public and row.for_user and row.for_user != frappe.session.user:
		return False

	blocked = frappe.get_cached_doc("User", frappe.session.user).get_blocked_modules() or []
	if row.module and row.module in blocked:
		return False

	try:
		return bool(Workspace(row, True).is_permitted())
	except frappe.PermissionError:
		return False
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Workspace guard: {row.name}")
		return False


def _dashboard_allowed(name: str | None) -> bool:
	if not name:
		return True
	if not frappe.has_permission("Dashboard", "read"):
		return False

	charts = frappe.get_all(
		"Dashboard Chart Link",
		filters={"parent": name, "parenttype": "Dashboard"},
		pluck="chart",
		ignore_permissions=True,
	)
	if not charts:
		return True

	return any(chart in _readable_charts() for chart in charts)


def _readable_charts() -> set:
	if hasattr(frappe.local, "_ws_guard_charts"):
		return frappe.local._ws_guard_charts

	rows = frappe.get_all(
		"Dashboard Chart",
		fields=["name", "document_type", "chart_type", "report_name"],
		ignore_permissions=True,
	)

	from frappe.boot import get_allowed_report_names

	allowed_reports = get_allowed_report_names(cache=True) or set()
	allowed_doctypes: dict = {}
	names = set()

	for row in rows:
		if row.chart_type == "Report" or (not row.document_type and row.report_name):
			if row.report_name and row.report_name in allowed_reports:
				names.add(row.name)
			continue

		doctype = row.document_type
		if not doctype:
			names.add(row.name)
			continue

		if doctype not in allowed_doctypes:
			allowed_doctypes[doctype] = frappe.has_permission(doctype, "read")
		if allowed_doctypes[doctype]:
			names.add(row.name)

	frappe.local._ws_guard_charts = names
	return names

SECTIONED_WORKSPACES = {"Home"}
SECTION_PREFIX = "home_h_"


@frappe.whitelist()
def get_workspace_sidebar_items():
	data = _original_sidebar_items()

	try:
		for page in (data or {}).get("pages") or []:
			if page.get("name") in SECTIONED_WORKSPACES:
				page["content"] = _prune_empty_sections(page)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Workspace section pruning failed")

	return data


def _prune_empty_sections(page) -> str:
	raw = page.get("content")
	if not raw:
		return raw

	blocks = loads(raw)
	visible = _visible_shortcut_labels(page)

	kept: list = []
	buffer: list = []
	heading = None
	has_visible = False

	def flush():
		if heading is not None and not has_visible:
			return
		if heading is not None:
			kept.append(heading)
		kept.extend(buffer)

	for block in blocks:
		is_section = (
			block.get("type") == "header"
			and str(block.get("id", "")).startswith(SECTION_PREFIX)
		)

		if is_section:
			flush()
			heading, buffer, has_visible = block, [], False
			continue

		if heading is None:
			kept.append(block)
			continue

		buffer.append(block)
		if block.get("type") == "shortcut":
			if (block.get("data") or {}).get("shortcut_name") in visible:
				has_visible = True
		else:
			has_visible = True

	flush()
	return dumps(kept)


def _visible_shortcut_labels(page) -> set:
	try:
		workspace = Workspace(frappe._dict(page))
		workspace.build_workspace()
		items = workspace.shortcuts.get("items") or []
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Workspace section pruning: build failed")
		return set()

	return {item.get("label") for item in items if _is_allowed(item)}
