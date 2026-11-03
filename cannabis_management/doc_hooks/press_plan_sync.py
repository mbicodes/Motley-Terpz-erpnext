"""Sync press job cards, Manufacture stock entries and Rosin Work Orders back into Press Production Plan rows.

Idempotent: every handler recomputes the row from its source documents, never adds increments. The Wash
Production Plan sync (wash_plan_sync.py) is separate and unchanged.
"""
import frappe
from frappe.utils import flt

from cannabis_management.cannabis_management.doctype.press_production_plan.press_production_plan import (
    SLOTS, get_settings, groups, live_job_card, micron_note, micron_rows, press_state, recompute, row_math,
    split_microns, wash_job_cards, metrc_tag,
)


def _rows(work_order):
    if not work_order:
        return []
    try:  # plain SQL: needs no DocType meta, so a missing table is the only failure before the reload
        return frappe.db.sql("""select name, parent from `tabPress Plan Item`
            where rosin_work_order = %s and parenttype = 'Press Production Plan'""", work_order, as_dict=True)
    except Exception as e:
        if frappe.db.is_table_missing(e):  # code deployed before migrate created the tables
            return []
        raise


def refresh_row(row_name, s=None):
    """Recompute one plan row from its Work Order, press job card and wash job card. Returns the plan name."""
    s = s or get_settings()
    grps = groups(s)
    r = frappe.get_doc("Press Plan Item", row_name)
    wo = frappe.db.get_value("Work Order", r.rosin_work_order, ["docstatus", "status", "produced_qty"], as_dict=True)
    jc = live_job_card(r.rosin_work_order)
    sub_ops = frappe.get_all("Job Card Operation", filters={"parent": jc.name, "parenttype": "Job Card"},
                             fields=["sub_operation", "status"]) if jc else []

    wash_jc = wash_job_cards([r.hash_work_order]).get(r.hash_work_order) if r.hash_work_order else None
    rows = micron_rows([wash_jc, jc.name if jc else None])
    grams, unknown = split_microns(rows.get(wash_jc), grps)
    note = micron_note(wash_jc, grams, unknown, r.bh_actual_g, grps)
    act, act_unknown = split_microns(rows.get(jc.name) if jc else [], grps)
    if act_unknown:
        note = (note + " " if note else "") + frappe._(
            "Press job card {0} has micron size(s) {1} that are not set up in Press Plan Settings; those grams are left out.").format(
            jc.name, ", ".join(act_unknown))

    r.wash_job_card = wash_jc
    r.micron_note = note
    for slot in SLOTS:
        r.set("g_" + slot, grams[slot])
        r.set("act_rosin_" + slot, act[slot])
    # total = the job card's completed qty; the Work Order's produced qty only when the card has none
    r.actual_rosin_g = flt(jc.total_completed_qty) if jc and flt(jc.total_completed_qty) else flt(wo.produced_qty) if wo else 0
    r.job_card = jc.name if jc else None
    r.metrc_tag = metrc_tag(jc.custom_sub_op_notes, s) if jc else ""
    r.row_status = press_state(wo, jc, sub_ops, s)
    row_math(r)
    fields = ["wash_job_card", "micron_note", "actual_rosin_g", "job_card", "metrc_tag", "row_status", "expected_rosin_g", "actual_yield"]
    for slot in SLOTS:
        fields += ["g_" + slot, "exp_rosin_" + slot, "act_rosin_" + slot, "act_yield_" + slot]
    r.db_set({f: r.get(f) for f in fields}, update_modified=False)
    return r.parent


def sync_work_order(work_order):
    rows = _rows(work_order)
    if not rows:
        return
    s = get_settings()
    for plan in {refresh_row(r.name, s) for r in rows}:
        recompute(plan)


def job_card_sync(doc, method=None):
    sync_work_order(doc.work_order)


def stock_entry_sync(doc, method=None):
    if doc.purpose == "Manufacture" and doc.work_order:
        sync_work_order(doc.work_order)


def work_order_sync(doc, method=None):
    sync_work_order(doc.name)
