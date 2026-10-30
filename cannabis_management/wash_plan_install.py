"""Install hook for Wash Production Plan: MR link fields and Wash Plan Settings defaults.

Code, not fixtures: the app's Custom Field fixture is unfiltered, so a fixture export
would drag in unrelated fields. Idempotent.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def boot_session(bootinfo):
    """Non-admins plan washes on the Wash Plan Board only: keep the DocType out of their desk search
    (List / New entries). It stays readable and writable, because the Board saves through it."""
    if "System Manager" in frappe.get_roles():
        return
    user = bootinfo.get("user") or {}
    for key in ("can_search", "can_create"):
        if isinstance(user.get(key), list):
            user[key] = [d for d in user[key] if d != "Wash Production Plan"]


def install():
    create_custom_fields({
        "Material Request": [
            {"fieldname": "custom_wash_production_plan", "label": "Wash Production Plan", "fieldtype": "Link",
             "options": "Wash Production Plan", "read_only": 1, "insert_after": "custom_routing", "no_copy": 1},
            {"fieldname": "custom_wash_plan_row", "label": "Wash Plan Row", "fieldtype": "Data",
             "read_only": 1, "hidden": 1, "no_copy": 1, "insert_after": "custom_wash_production_plan"},
        ]
    }, update=True)
    add_workspace_shortcut()
    if not frappe.db.exists("DocType", "Wash Plan Settings"):
        return
    s = frappe.get_doc("Wash Plan Settings")
    if s.freezers:
        return  # seed only when empty; never overwrite what the user configured
    for w in ("Freezer - MTM", "Freezer 2 - MTM", "Freezer 3 - MTM", "Freezer 4 - MTM"):
        if frappe.db.exists("Warehouse", w):
            s.append("freezers", {"warehouse": w})
    s.flags.ignore_mandatory = True
    s.save(ignore_permissions=True)


def add_workspace_shortcut():
    """Wash Plan Board shortcut on the Manufacturing workspace, and every workspace link to the
    Wash Production Plan DocType pointed at the Board instead. Idempotent; runs after every
    migrate because the standard workspace is re-imported from ERPNext."""
    import json

    for s in frappe.get_all("Workspace Shortcut", filters={"type": "DocType", "link_to": "Wash Production Plan"}, fields=["name", "parent"]):
        frappe.db.set_value("Workspace Shortcut", s.name, {"type": "Page", "link_to": "wash-plan-board"})
    for l in frappe.get_all("Workspace Link", filters={"link_type": "DocType", "link_to": "Wash Production Plan"}, pluck="name"):
        frappe.db.set_value("Workspace Link", l, {"link_type": "Page", "link_to": "wash-plan-board"})

    if not frappe.db.exists("Workspace", "Manufacturing"):
        return
    ws = frappe.get_doc("Workspace", "Manufacturing")
    if any(s.link_to == "wash-plan-board" for s in ws.shortcuts):
        return
    ws.append("shortcuts", {"label": "Wash Plan Board", "type": "Page", "link_to": "wash-plan-board", "color": "Green"})
    content = json.loads(ws.content or "[]")
    content.insert(0, {"id": "wash-plan-board", "type": "shortcut", "data": {"shortcut_name": "Wash Plan Board", "col": 3}})
    ws.content = json.dumps(content)
    ws.flags.ignore_permissions = True
    ws.save()
    frappe.db.commit()
