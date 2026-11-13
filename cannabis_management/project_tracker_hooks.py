"""Project Tracker wiring: cache busting, Project dates/defaults, install (settings, workspace shortcut).

Every handler here is best-effort: a failure is logged and never blocks the submit / save that triggered it.
"""
import json

import frappe
from frappe.utils import cint, flt, nowdate

PAGE = "project-tracker"
TRACKER = "cannabis_management.project_tracker_hooks"
CACHE_VER_KEY = "project_tracker:ver"

# submit / cancel of these changes figures on the page
_BUMP = {"on_submit": [f"{TRACKER}.on_doc_change"], "on_cancel": [f"{TRACKER}.on_doc_change"]}
DOC_EVENTS = {
	"Stock Entry": _BUMP,
	"Purchase Receipt": _BUMP,
	"Conversion Entry": _BUMP,
	"Purchase Invoice": _BUMP,
	"Journal Entry": _BUMP,
	"Rosin Recording": _BUMP,
	"Project": {"validate": [f"{TRACKER}.project_validate"], "on_update": [f"{TRACKER}.bump_cache"]},
}


def extend_doc_events(doc_events):
	"""Append (never replace) the tracker handlers; hooks.py keys may hold a string or a list."""
	for doctype, events in DOC_EVENTS.items():
		target = doc_events.setdefault(doctype, {})
		for event, handlers in events.items():
			existing = target.get(event, [])
			if isinstance(existing, str):
				existing = [existing]
			target[event] = list(existing) + [h for h in handlers if h not in existing]
	return doc_events


def bump_cache(*args, **kwargs):
	try:
		frappe.cache().set_value(CACHE_VER_KEY, frappe.generate_hash(length=10))
	except Exception:
		pass


def _projects_of(doc):
	names = set()
	if doc.get("project"):
		names.add(doc.project)
	for table in ("items", "accounts"):
		for r in doc.get(table) or []:
			if r.get("project"):
				names.add(r.project)
	ce = doc.get("custom_conversion_entry_reference")
	if ce:
		p = frappe.db.get_value("Conversion Entry", ce, "project")
		if p:
			names.add(p)
	if doc.doctype == "Rosin Recording" and doc.get("batch"):
		names.add(doc.batch)
	return names


def on_doc_change(doc, method=None):
	bump_cache()
	if doc.doctype not in ("Stock Entry", "Purchase Receipt"):
		return
	try:
		from cannabis_management.cannabis_management.page.project_tracker.project_tracker import refresh_project_dates

		for name in _projects_of(doc):
			if frappe.db.get_value("Project", name, "custom_processing_type"):
				refresh_project_dates(name)
	except Exception:
		frappe.log_error(title=f"Project Tracker: dispatch date for {doc.doctype} {doc.name}")


def project_validate(doc, method=None):
	try:
		ptype = doc.get("custom_processing_type")
		if ptype == "In-house":
			doc.custom_toll_partner = None
		if ptype == "Toll" and doc.get("custom_toll_partner") and not doc.get("custom_partner_warehouse"):
			doc.custom_partner_warehouse = frappe.db.get_value("Supplier", doc.custom_toll_partner, "custom_toll_warehouse")
		if ptype:
			if not flt(doc.get("custom_expected_hash_pct")) or not flt(doc.get("custom_expected_rosin_pct")):
				s = frappe.get_cached_doc("Project Tracker Settings")
				if not flt(doc.get("custom_expected_hash_pct")):
					doc.custom_expected_hash_pct = flt(s.default_hash_target) or 2.5
				if not flt(doc.get("custom_expected_rosin_pct")):
					doc.custom_expected_rosin_pct = flt(s.default_rosin_target) or 75
		if doc.status == "Completed" and not doc.get("custom_return_completed_on"):
			doc.custom_return_completed_on = nowdate()
		elif doc.status != "Completed" and doc.get("custom_return_completed_on"):
			doc.custom_return_completed_on = None
	except Exception:
		frappe.log_error(title=f"Project Tracker: Project {doc.name} defaults")


# ---------------------------------------------------------------- install (after_migrate)

DEFAULT_GROUPS = {"hash_item_groups": ["Bubble Hash"], "rosin_item_groups": ["Rosins", "Rosin"]}


def install():
	try:
		_seed_settings()
		add_workspace_shortcut()
	except Exception:
		frappe.log_error(title="Project Tracker install")


def _seed_settings():
	if not frappe.db.exists("DocType", "Project Tracker Settings"):
		return
	s = frappe.get_doc("Project Tracker Settings")
	changed = False
	for f in s.meta.fields:
		if f.default and f.fieldtype in ("Percent", "Int", "Link") and not s.get(f.fieldname):
			if f.fieldtype == "Link" and not frappe.db.exists(f.options, f.default):
				continue
			s.set(f.fieldname, f.default)
			changed = True
	for field, groups in DEFAULT_GROUPS.items():
		if not s.get(field):
			for g in groups:
				if frappe.db.exists("Item Group", g):
					s.append(field, {"item_group": g})
					changed = True
	if changed:
		s.flags.ignore_mandatory = True
		s.save(ignore_permissions=True)


def add_workspace_shortcut():
	"""Project Tracker shortcut on the Manufacturing workspace, after the Press Plan Board. Re-run after every
	migrate because the standard workspace is re-imported from ERPNext."""
	if not frappe.db.exists("Workspace", "Manufacturing") or not frappe.db.exists("Page", PAGE):
		return
	ws = frappe.get_doc("Workspace", "Manufacturing")
	if any(s.link_to == PAGE for s in ws.shortcuts):
		return
	ws.append("shortcuts", {"label": "Project Tracker", "type": "Page", "link_to": PAGE, "color": "Blue"})
	content = json.loads(ws.content or "[]")
	at = next((i + 1 for i, b in enumerate(content) if b.get("id") in ("press-plan-board", "wash-plan-board")), 0)
	for i, b in enumerate(content):
		if b.get("id") == "press-plan-board":
			at = i + 1
	content.insert(at, {"id": PAGE, "type": "shortcut", "data": {"shortcut_name": "Project Tracker", "col": 3}})
	ws.content = json.dumps(content)
	ws.flags.ignore_permissions = True
	ws.save()
	frappe.db.commit()
