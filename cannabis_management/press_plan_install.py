"""Install hook for Press Production Plan: Press Plan Settings defaults and the Manufacturing workspace shortcut.

Idempotent; seeds only what is empty and never overwrites what the user configured.
"""
import json

import frappe

DEFAULT_MICRON_GROUPS = (("150u", 76), ("120u - 73u", 73), ("45u", 59))


def boot_session(bootinfo):
    """Non-admins plan pressing on the Press Plan Board only: keep the DocType out of their desk search
    (List / New entries). It stays readable and writable, because the Board saves through it."""
    if "System Manager" in frappe.get_roles():
        return
    user = bootinfo.get("user") or {}
    for key in ("can_search", "can_create"):
        if isinstance(user.get(key), list):
            user[key] = [d for d in user[key] if d != "Press Production Plan"]


def install():
    add_workspace_shortcut()
    if not frappe.db.exists("DocType", "Press Plan Settings"):
        return
    s = frappe.get_doc("Press Plan Settings")
    changed = False
    for f in s.meta.fields:
        if f.default and f.fieldtype in ("Link", "Int", "Data") and not s.get(f.fieldname):
            if f.fieldtype == "Link" and not frappe.db.exists(f.options, f.default):
                continue
            s.set(f.fieldname, f.default)
            changed = True
    if not s.micron_groups:
        for label, pct in DEFAULT_MICRON_GROUPS:
            s.append("micron_groups", {"micron_label": label, "expected_yield": pct})
        changed = True
    if changed:
        s.flags.ignore_mandatory = True
        s.save(ignore_permissions=True)


def add_workspace_shortcut():
    """Press Plan Board shortcut on the Manufacturing workspace (next to the Wash Plan Board), and every workspace
    link to the Press Production Plan DocType pointed at the Board instead. Runs after every migrate because the
    standard workspace is re-imported from ERPNext."""
    for s in frappe.get_all("Workspace Shortcut", filters={"type": "DocType", "link_to": "Press Production Plan"}, pluck="name"):
        frappe.db.set_value("Workspace Shortcut", s, {"type": "Page", "link_to": "press-plan-board"})
    for l in frappe.get_all("Workspace Link", filters={"link_type": "DocType", "link_to": "Press Production Plan"}, pluck="name"):
        frappe.db.set_value("Workspace Link", l, {"link_type": "Page", "link_to": "press-plan-board"})

    if not frappe.db.exists("Workspace", "Manufacturing") or not frappe.db.exists("Page", "press-plan-board"):
        return
    ws = frappe.get_doc("Workspace", "Manufacturing")
    if any(s.link_to == "press-plan-board" for s in ws.shortcuts):
        return
    ws.append("shortcuts", {"label": "Press Plan Board", "type": "Page", "link_to": "press-plan-board", "color": "Purple"})
    content = json.loads(ws.content or "[]")
    at = next((i + 1 for i, b in enumerate(content) if b.get("id") == "wash-plan-board"), 0)
    content.insert(at, {"id": "press-plan-board", "type": "shortcut", "data": {"shortcut_name": "Press Plan Board", "col": 3}})
    ws.content = json.dumps(content)
    ws.flags.ignore_permissions = True
    ws.save()
    frappe.db.commit()
