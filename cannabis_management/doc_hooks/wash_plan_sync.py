"""Sync Material Request / Work Order / Stock Entry events back into Wash Production Plan rows.

Idempotent: every handler recomputes from Work Order values, never adds increments.
"""
import frappe
from frappe.utils import flt

from cannabis_management.cannabis_management.doctype.wash_production_plan.wash_production_plan import (
    get_settings, recompute,
)


def _row_for_mr(mr_name):
    mr = frappe.db.get_value("Material Request", mr_name, ["custom_wash_production_plan", "custom_wash_plan_row"], as_dict=1)
    if mr and mr.custom_wash_production_plan and mr.custom_wash_plan_row:
        return mr.custom_wash_production_plan, mr.custom_wash_plan_row
    return None, None


def _kind(wo_item):
    grp = frappe.db.get_value("Item", wo_item, "item_group")
    s = get_settings()
    return "hash" if grp == s.bubble_hash_item_group else "rosin" if grp == s.rosin_item_group else None


def work_order_after_insert(doc, method=None):
    if not doc.get("material_request"):
        return
    plan, row = _row_for_mr(doc.material_request)
    kind = _kind(doc.production_item)
    if row and kind:
        frappe.db.set_value("Wash Production Plan Item", row, f"{kind}_work_order", doc.name, update_modified=False)


def stock_entry_sync(doc, method=None):
    if doc.purpose != "Manufacture" or not doc.work_order:
        return
    wo = frappe.db.get_value("Work Order", doc.work_order, ["material_request", "production_item", "produced_qty"], as_dict=1)
    if not wo or not wo.material_request:
        return
    plan, row = _row_for_mr(wo.material_request)
    kind = _kind(wo.production_item)
    if not row or not kind:
        return
    r = frappe.db.get_value("Wash Production Plan Item", row, ["planned_qty_grams", "actual_hash_g"], as_dict=1)
    produced = flt(wo.produced_qty)
    if kind == "hash":
        upd = {
            "actual_hash_g": produced,
            "actual_hash_yield": produced / flt(r.planned_qty_grams) * 100 if flt(r.planned_qty_grams) else 0,
            "row_status": "Washed" if produced > 0 else "MR Created",
        }
    else:
        upd = {
            "actual_rosin_g": produced,
            "actual_rosin_yield": produced / flt(r.actual_hash_g) * 100 if flt(r.actual_hash_g) else 0,
            "row_status": "Completed" if produced > 0 else "Washed",
        }
    frappe.db.set_value("Wash Production Plan Item", row, upd, update_modified=False)
    recompute(plan)


def material_request_unlink(doc, method=None):
    plan, row = _row_for_mr(doc.name)
    if not row:
        return
    frappe.db.set_value("Wash Production Plan Item", row, {
        "material_request": None, "hash_work_order": None, "rosin_work_order": None,
        "row_status": "Planned", "actual_hash_g": 0, "actual_hash_yield": 0, "actual_rosin_g": 0, "actual_rosin_yield": 0,
    }, update_modified=False)
    recompute(plan)
