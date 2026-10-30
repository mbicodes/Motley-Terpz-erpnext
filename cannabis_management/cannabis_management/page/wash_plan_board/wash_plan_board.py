"""Server side of the Wash Plan Board page.

Every business rule (period, allocation, project from stock, eligibility, Material Request
building) lives in the Wash Production Plan controller; this module only loads a plan, applies
one change through the normal document save, and shapes the result for the page.
"""
import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from cannabis_management.cannabis_management.doctype.wash_production_plan import wash_production_plan as w

LBS_TO_GRAM = w.LBS_TO_GRAM
EDITABLE = ("planned_qty_lbs", "source_freezer", "project", "planned_date", "expected_hash_yield", "expected_rosin_yield")


def _plan(name, write=False):
    doc = frappe.get_doc("Wash Production Plan", name)
    doc.check_permission("write" if write else "read")
    return doc


def _row(doc, row):
    r = doc.get("items", {"name": row})
    if not r:
        frappe.throw(_("Row {0} was not found in {1}.").format(row, doc.name))
    return r[0]


@frappe.whitelist()
def list_plans():
    return frappe.get_list("Wash Production Plan", filters={"status": ["in", ["Draft", "In Progress"]]},
                           fields=["name", "plan_type", "from_date", "to_date", "status", "total_washes"],
                           order_by="from_date desc, creation desc", limit_page_length=100)


@frappe.whitelist()
def new_plan(plan_type, from_date, to_date=None):
    doc = frappe.new_doc("Wash Production Plan")
    doc.update({"plan_type": plan_type, "from_date": from_date, "to_date": to_date or from_date})
    doc.insert()
    return doc.name


@frappe.whitelist()
def update_period(plan, plan_type, from_date, to_date=None):
    doc = _plan(plan, True)
    doc.update({"plan_type": plan_type, "from_date": from_date, "to_date": to_date or from_date})
    doc.save()
    return doc.name


def _auto_project(item, freezer):
    """Project of the stock for item + freezer: the only one when there is one, else blank (user picks)."""
    projects = w.get_stock_projects(item, freezer)
    return projects[0].project if len(projects) == 1 else ""


@frappe.whitelist()
def add_row(plan, planned_date, item, freezer, lbs, project=None):
    doc = _plan(plan, True)
    s = w.get_settings()
    sug = w.suggest_finished_items(item)
    doc.append("items", {
        "planned_date": planned_date, "fresh_frozen_item": item, "source_freezer": freezer,
        "planned_qty_lbs": flt(lbs), "project": project if project is not None else _auto_project(item, freezer),
        "bubble_hash_item": sug.get("bubble_hash_item"), "rosin_item": sug.get("rosin_item"),
        "expected_hash_yield": s.default_hash_yield, "expected_rosin_yield": s.default_rosin_yield,
    })
    doc.save()
    return doc.items[-1].name


@frappe.whitelist()
def update_row(plan, row, values):
    doc = _plan(plan, True)
    r = _row(doc, row)
    values = {k: v for k, v in frappe.parse_json(values).items() if k in EDITABLE}
    freezer_changed = "source_freezer" in values and values["source_freezer"] != r.source_freezer
    r.update(values)
    if freezer_changed and "project" not in values:
        r.project = _auto_project(r.fresh_frozen_item, r.source_freezer)
    doc.save()
    return row


@frappe.whitelist()
def remove_row(plan, row):
    doc = _plan(plan, True)
    r = _row(doc, row)
    if r.row_status != "Planned":
        frappe.throw(_("Row {0}: only rows in Planned status can be deleted.").format(r.idx))
    doc.remove(r)
    for i, x in enumerate(doc.items, 1):
        x.idx = i
    doc.save()
    return row


@frappe.whitelist()
def create_finished_item(plan, row, kind):
    doc = _plan(plan, True)
    r = _row(doc, row)
    base = w.base_name(r.item_name or frappe.db.get_value("Item", r.fresh_frozen_item, "item_name"))
    code = w.create_finished_item(base, kind)
    r.set("bubble_hash_item" if kind == "bubble_hash" else "rosin_item", code)
    doc.save()
    return code


@frappe.whitelist()
def preview_row(item, freezer, project=None, lbs=0, plan=None):
    s = w.get_settings()
    row = frappe._dict(planned_qty_lbs=flt(lbs), expected_hash_yield=s.default_hash_yield, expected_rosin_yield=s.default_rosin_yield)
    w.row_math(row, s)
    av = w.get_row_availability(item, freezer, project or "", plan=plan)
    sug = w.suggest_finished_items(item)
    for k in ("bubble_hash_item", "rosin_item"):
        sug[k + "_name"] = frappe.db.get_value("Item", sug[k], "item_name") if sug.get(k) else None
    return {"expected_hash_g": row.expected_hash_g, "expected_rosin_g": row.expected_rosin_g, "free": av["available"],
            "holders": av["holders"], "projects": w.get_stock_projects(item, freezer), "suggest": sug}


@frappe.whitelist()
def get_item_options(item):
    """Freezers holding the item (with qty) and, per freezer, the projects holding it."""
    out = []
    for f in w.get_item_freezers(item):
        f["projects"] = w.get_stock_projects(item, f["warehouse"])
        out.append(f)
    return out


def _fg_rows(r):
    s = w.get_settings()
    done = r.row_status in ("Washed", "Completed")
    rosin_done = r.row_status == "Completed"
    out = []
    for op, item, grp, y, g, ay, ag, ok in (
        ("Hash Processing", r.bubble_hash_item, s.bubble_hash_item_group, r.expected_hash_yield, r.expected_hash_g,
         r.actual_hash_yield, r.actual_hash_g, done),
        ("Rosin Pressing", r.rosin_item, s.rosin_item_group, r.expected_rosin_yield, r.expected_rosin_g,
         r.actual_rosin_yield, r.actual_rosin_g, rosin_done),
    ):
        out.append({"operation": op, "item": item, "item_name": frappe.db.get_value("Item", item, "item_name") if item else None,
                    "item_group": grp, "expected_yield": y, "expected_g": g,
                    "actual_yield": ay if ok else None, "actual_g": ag if ok else None,
                    "kind": "bubble_hash" if op == "Hash Processing" else "rosin"})
    return out


@frappe.whitelist()
def get_board(plan):
    doc = _plan(plan)
    remaining, holders = doc.allocate()
    rows, cache = [], {}
    for r in sorted(doc.items, key=lambda x: (str(x.planned_date), x.idx)):
        opts = cache.setdefault(r.fresh_frozen_item, get_item_options(r.fresh_frozen_item))
        planned = r.row_status == "Planned"
        gap = flt(r.planned_qty_lbs) - remaining[r.name] if planned else 0
        rows.append({
            "name": r.name, "idx": r.idx, "planned_date": str(r.planned_date), "item": r.fresh_frozen_item,
            "item_name": r.item_name, "freezer": r.source_freezer, "project": r.project or "",
            "project_name": frappe.db.get_value("Project", r.project, "project_name") if r.project else "",
            "available": remaining[r.name], "over_by": max(gap, 0), "held_by": holders[r.name],
            "lbs": r.planned_qty_lbs, "expected_hash_g": r.expected_hash_g, "expected_rosin_g": r.expected_rosin_g,
            "status": r.row_status, "mr": r.material_request, "hash_wo": r.hash_work_order, "rosin_wo": r.rosin_work_order,
            "actual_hash_g": r.actual_hash_g, "block_reason": w.block_reason(r, remaining), "freezers": opts,
            "finished_goods": _fg_rows(r),
        })
    s = w.get_settings()
    return {
        "plan": {"name": doc.name, "plan_type": doc.plan_type, "from_date": str(doc.from_date), "to_date": str(doc.to_date),
                 "status": doc.status, "writable": frappe.has_permission("Wash Production Plan", "write", doc=doc)},
        "defaults": {"hash": s.default_hash_yield, "rosin": s.default_rosin_yield, "ff_group": s.fresh_frozen_item_group},
        "rows": rows, "summary": _summary(doc), "stock": _freezer_stock(doc),
    }


def _summary(doc):
    groups = {}
    for r in doc.items:
        g = groups.setdefault(r.project or "", {"project": r.project or "", "washes": 0, "lbs": 0, "hash": 0, "rosin": 0,
                                                "name": frappe.db.get_value("Project", r.project, "project_name") if r.project else ""})
        g["washes"] += 1; g["lbs"] += flt(r.planned_qty_lbs); g["hash"] += flt(r.expected_hash_g); g["rosin"] += flt(r.expected_rosin_g)
    return sorted(groups.values(), key=lambda x: (x["project"] == "", x["project"]))


def _freezer_stock(doc):
    """Per freezer, per item and project: stock-ledger balance against what this plan books."""
    s = w.get_settings()
    groups = frappe.db.get_descendants("Item Group", s.fresh_frozen_item_group) + [s.fresh_frozen_item_group]
    booked = {}
    for r in doc.items:
        if r.row_status in ("Planned", "MR Created"):
            k = (r.source_freezer, r.fresh_frozen_item, r.project or "")
            booked[k] = booked.get(k, 0) + flt(r.planned_qty_lbs)
    out = []
    for f in s.freezers:
        rows = frappe.db.sql(
            """select sle.item_code, i.item_name, ifnull(sle.project, '') project, sum(sle.actual_qty) qty
            from `tabStock Ledger Entry` sle join tabItem i on i.name = sle.item_code
            where sle.warehouse = %s and sle.is_cancelled = 0 and i.item_group in %s
            group by sle.item_code, ifnull(sle.project, '') having sum(sle.actual_qty) > 0.0001
            order by i.item_name, project""", (f.warehouse, groups), as_dict=True)
        seen = {(f.warehouse, x.item_code, x.project) for x in rows}
        items = [{"item": x.item_code, "item_name": x.item_name, "project": x.project, "balance": x.qty,
                  "booked": booked.get((f.warehouse, x.item_code, x.project), 0)} for x in rows]
        for (wh, it, pr), q in booked.items():
            if wh == f.warehouse and (wh, it, pr) not in seen:
                items.append({"item": it, "item_name": frappe.db.get_value("Item", it, "item_name"), "project": pr, "balance": 0, "booked": q})
        out.append({"freezer": f.warehouse, "balance": sum(i["balance"] for i in items), "booked": sum(i["booked"] for i in items), "items": items})
    return out
