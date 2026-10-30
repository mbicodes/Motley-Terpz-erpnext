"""Install hook for Wash Production Plan: MR link fields and Wash Plan Settings defaults.

Code, not fixtures: the app's Custom Field fixture is unfiltered, so a fixture export
would drag in unrelated fields. Idempotent.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


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
    """Wash Plan Board shortcut on the Manufacturing workspace. Idempotent; runs after every
    migrate because the standard workspace is re-imported from ERPNext."""
    import json

    if not frappe.db.exists("Workspace", "Manufacturing"):
        return
    ws = frappe.get_doc("Workspace", "Manufacturing")
    if any(s.label == "Wash Plan Board" for s in ws.shortcuts):
        return
    ws.append("shortcuts", {"label": "Wash Plan Board", "type": "Page", "link_to": "wash-plan-board", "color": "Grey"})
    content = json.loads(ws.content or "[]")
    content.insert(0, {"id": "wash-plan-board", "type": "shortcut", "data": {"shortcut_name": "Wash Plan Board", "col": 3}})
    ws.content = json.dumps(content)
    ws.flags.ignore_permissions = True
    ws.save()


def verify():
    import frappe

    ok = True

    def check(label, passed, detail=""):
        nonlocal ok
        ok = ok and bool(passed)
        print(("PASS " if passed else "FAIL ") + label + (f"  [{detail}]" if detail else ""))

    for dt in ("Wash Plan Settings", "Wash Plan Freezer", "Wash Production Plan", "Wash Production Plan Item"):
        check(f"DocType {dt}", frappe.db.exists("DocType", dt))
    check("Page wash-plan-board", frappe.db.exists("Page", "wash-plan-board"))
    check("Report Wash Plan vs Actual", frappe.db.exists("Report", "Wash Plan vs Actual"))
    for f in ("custom_wash_production_plan", "custom_wash_plan_row"):
        check(f"Material Request.{f}", frappe.db.exists("Custom Field", f"Material Request-{f}"))
    cp = frappe.db.get_value("Custom Field", "Material Request-custom_project", ["reqd", "mandatory_depends_on"], as_dict=1) or {}
    check("MR custom_project mandatory only for manual MRs",
          not cp.get("reqd") and cp.get("mandatory_depends_on") == "eval:!doc.custom_wash_production_plan", str(cp))
    hooks = frappe.get_hooks("doc_events")
    for dt, ev in (("Material Request", "on_cancel"), ("Material Request", "on_trash"), ("Stock Entry", "on_submit"),
                   ("Stock Entry", "on_cancel"), ("Work Order", "after_insert")):
        fns = hooks.get(dt, {}).get(ev, [])
        fns = [fns] if isinstance(fns, str) else fns
        check(f"hook {dt}.{ev}", any("wash_plan_sync" in x for x in fns))
    if frappe.db.exists("DocType", "Wash Plan Settings"):
        s = frappe.get_doc("Wash Plan Settings")
        have = {f.warehouse for f in s.freezers}
        wanted = ["Freezer - MTM", "Freezer 2 - MTM", "Freezer 3 - MTM", "Freezer 4 - MTM"]
        missing = [w for w in wanted if w not in have and frappe.db.exists("Warehouse", w)]
        check("Settings freezers", have, ", ".join(sorted(have)) or "none")
        if missing:
            print("TODO add to Wash Plan Settings > Freezers: " + ", ".join(missing))
        for fld in ("default_company", "routing", "fresh_frozen_item_group", "bubble_hash_item_group", "rosin_item_group"):
            check(f"Settings.{fld}", s.get(fld), str(s.get(fld)))
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    return ok
