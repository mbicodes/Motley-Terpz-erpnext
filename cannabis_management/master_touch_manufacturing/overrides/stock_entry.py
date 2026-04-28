"""
Stock Entry override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Stock Entry"]["before_submit"]
    doc_events["Stock Entry"]["on_submit"]

Responsibilities (Manufacture entries only):
- before_submit:
    * Enforce 2.5% yield threshold if linked to a Wash Batch.
    * Toll BOM override: zero out customer-owned raw material rows so
      those materials post at $0 in the stock ledger.
- on_submit:
    * Auto-create ERPNext Batch records for each finished-goods line.
    * Compute actual cost_per_gram (material + Job Card labour).
    * Stamp cost_per_gram on each finished-goods Batch record.
    * Write cost_per_gram_bubble / cost_per_gram_rosin back to the
      parent Production Batch Group.
"""

import frappe
from frappe.utils import flt, now_datetime

BUBBLE_YIELD_THRESHOLD_PCT = 2.5


def before_submit(doc, method=None):
    """Yield threshold check + toll BOM $0 override."""
    if doc.stock_entry_type != "Manufacture":
        return
    _check_yield_on_manufacture(doc)
    _apply_toll_bom_zero_cost(doc)


def on_submit(doc, method=None):
    """Auto-create Batch records; stamp and roll-up cost_per_gram."""
    if doc.stock_entry_type != "Manufacture":
        return
    _auto_create_batches(doc)
    _stamp_cost_per_gram(doc)


# ── helpers ────────────────────────────────────────────────────────────────

def _check_yield_on_manufacture(doc):
    """
    If this SE is linked to a Wash Batch, verify the fg_completed_qty
    meets the minimum 2.5% threshold against the raw material input.
    """
    pbg_name = doc.get("custom_production_batch_group")
    if not pbg_name:
        return

    # Find the FF raw material row
    ff_qty_g = 0.0
    fg_qty_g = 0.0
    for row in doc.items or []:
        item_group = frappe.db.get_value("Item", row.item_code, "item_group") or ""
        if "Fresh Frozen" in item_group:
            # Convert LBS → g if UOM is LBS
            if (row.uom or "").upper() == "LBS":
                ff_qty_g += flt(row.qty) * 453.592
            else:
                ff_qty_g += flt(row.qty)
        if row.is_finished_item:
            fg_qty_g += flt(row.qty)

    if ff_qty_g <= 0:
        return  # Nothing to check

    yield_pct = (fg_qty_g / ff_qty_g) * 100

    if yield_pct < BUBBLE_YIELD_THRESHOLD_PCT:
        # Check if supervisor has approved via the linked Wash Batch
        approved = False
        wash_batches = frappe.get_all(
            "Wash Batch",
            filters={"production_batch_group": pbg_name, "docstatus": 1},
            fields=["supervisor_approved"],
        )
        if wash_batches and all(wb.supervisor_approved for wb in wash_batches):
            approved = True

        if not approved:
            frappe.throw(
                f"Manufacture yield is {yield_pct:.2f}% — below the minimum "
                f"{BUBBLE_YIELD_THRESHOLD_PCT}%. A Lab Supervisor must approve the "
                "linked Wash Batch before this Stock Entry can be submitted.",
                title="Yield Below Threshold"
            )


def _auto_create_batches(doc):
    """
    For each finished-goods item row in a Manufacture SE that doesn't already
    have an ERPNext Batch, create one and back-link it.
    """
    for row in doc.items or []:
        if not row.is_finished_item:
            continue
        if row.batch_no:
            continue  # Batch already assigned

        item = frappe.get_doc("Item", row.item_code)
        if not item.has_batch_no:
            continue

        # Create a new Batch
        batch = frappe.new_doc("Batch")
        batch.item = row.item_code
        batch.batch_qty = flt(row.qty)
        batch.manufacturing_date = doc.posting_date
        batch.expiry_date = None

        # MTM custom fields
        pbg = doc.get("custom_production_batch_group")
        if pbg:
            batch.custom_production_batch_group = pbg
        batch.custom_work_order_ref = doc.work_order
        batch.custom_batch_type = _infer_batch_type(row.item_code)
        batch.custom_net_weight_g = flt(row.qty)

        batch.insert(ignore_permissions=True)

        # Write batch back to the SE row
        frappe.db.set_value(
            "Stock Entry Detail", row.name, "batch_no", batch.name
        )

        # Also store in SE header for quick reference (first FG only)
        if not doc.custom_erpnext_batch_created:
            frappe.db.set_value(
                "Stock Entry", doc.name, "custom_erpnext_batch_created", batch.name
            )


def _infer_batch_type(item_code):
    """Map item group to Batch Type select value."""
    item_group = frappe.db.get_value("Item", item_code, "item_group") or ""
    if "Fresh Frozen" in item_group:
        return "Fresh Frozen"
    if item_group in ("Primes", "Subprimes", "Full Spec", "Food Grade"):
        return "Bubble Hash"
    if item_group == "Rosin":
        return "Rosin"
    return ""


# ── Phase 9: Toll BOM $0 override ─────────────────────────────────────────────

def _apply_toll_bom_zero_cost(doc):
    """
    If the Work Order's BOM has custom_is_toll_bom = 1, zero out the
    customer-owned raw material rows (Fresh Frozen or Bubble Hash) so
    those materials post to the stock ledger at $0.
    Also recompute the finished-goods row basic_rate using only the
    non-zeroed costs (consumables + labour from Job Cards).
    """
    wo_name = doc.work_order
    if not wo_name:
        return

    bom_name = frappe.db.get_value("Work Order", wo_name, "bom_no")
    if not bom_name:
        return

    bom_data = frappe.db.get_value(
        "BOM", bom_name, ["custom_is_toll_bom", "custom_toll_fee_g"], as_dict=True
    )
    if not (bom_data and bom_data.custom_is_toll_bom):
        return

    # Customer-owned material item groups — zero these rows out
    toll_groups = {"Fresh Frozen", "Primes", "Subprimes", "Full Spec", "Food Grade",
                   "Fresh Frozen - SHO", "Fresh Frozen - BHO"}

    zeroed_cost = 0.0
    for row in doc.items or []:
        if row.is_finished_item or row.is_scrap_item:
            continue
        if not row.s_warehouse:
            continue
        item_group = frappe.db.get_value("Item", row.item_code, "item_group") or ""
        if item_group in toll_groups:
            zeroed_cost += flt(row.basic_amount)
            row.basic_rate = 0.0
            row.basic_amount = 0.0
            row.rate = 0.0
            row.amount = 0.0
            frappe.db.set_value(
                "Stock Entry Detail", row.name,
                {"basic_rate": 0, "basic_amount": 0, "rate": 0, "amount": 0}
            )

    if zeroed_cost <= 0:
        return  # nothing was zeroed, skip recompute

    # Recompute FG row basic_rate = (remaining material cost) / fg_qty
    remaining_material = sum(
        flt(r.basic_amount)
        for r in (doc.items or [])
        if not r.is_finished_item and not r.is_scrap_item and r.s_warehouse
    )
    # Add actual Job Card labour cost
    # jc_cost = flt(frappe.db.sql(
    #     "SELECT IFNULL(SUM(actual_operating_cost),0) FROM `tabJob Card` "
    #     "WHERE work_order=%s AND docstatus=1", wo_name
    # )[0][0])
    # total_cost = remaining_material + jc_cost
    total_cost = remaining_material
    fg_qty = sum(flt(r.qty) for r in (doc.items or []) if r.is_finished_item)
    if fg_qty <= 0:
        return

    new_rate = total_cost / fg_qty
    for row in doc.items or []:
        if row.is_finished_item:
            row.basic_rate = new_rate
            row.basic_amount = new_rate * flt(row.qty)
            frappe.db.set_value(
                "Stock Entry Detail", row.name,
                {"basic_rate": new_rate, "basic_amount": new_rate * flt(row.qty)}
            )


# ── Phase 9: Cost computation + PBG rollup ────────────────────────────────────

def _stamp_cost_per_gram(doc):
    """
    After submit, compute actual cost_per_gram and:
    - stamp it on each finished-goods Batch (custom_cost_per_gram)
    - update Production Batch Group cost_per_gram_bubble / cost_per_gram_rosin
    """
    wo_name = doc.work_order
    pbg_name = doc.get("custom_production_batch_group")

    # Sum non-FG source rows at posted valuation
    material_cost = sum(
        flt(r.basic_amount)
        for r in (doc.items or [])
        if not r.is_finished_item and not r.is_scrap_item and r.s_warehouse
    )

    # Add actual Job Card labour
    # jc_cost = 0.0
    # if wo_name:
        # jc_cost = flt(frappe.db.sql(
        #     "SELECT IFNULL(SUM(actual_operating_cost),0) FROM `tabJob Card` "
        #     "WHERE work_order=%s AND docstatus=1", wo_name
        # )[0][0])

    # total_cost = material_cost + jc_cost
    total_cost = material_cost

    fg_qty = sum(flt(r.qty) for r in (doc.items or []) if r.is_finished_item)
    if fg_qty <= 0:
        return

    cost_per_gram = total_cost / fg_qty

    # Determine product type from FG item group
    batch_type = ""
    for row in doc.items or []:
        if row.is_finished_item:
            ig = frappe.db.get_value("Item", row.item_code, "item_group") or ""
            batch_type = _infer_batch_type(row.item_code)
            break

    # Stamp each finished-goods Batch
    for row in doc.items or []:
        if not row.is_finished_item:
            continue
        batch_no = row.batch_no
        if not batch_no:
            # Try to find batch just created in _auto_create_batches
            batch_no = frappe.db.get_value(
                "Stock Entry Detail", row.name, "batch_no"
            )
        if batch_no and frappe.db.exists("Batch", batch_no):
            # Add custom_cost_per_gram if the field exists
            if frappe.db.has_column("Batch", "custom_cost_per_gram"):
                frappe.db.set_value("Batch", batch_no, "custom_cost_per_gram", cost_per_gram)

    # Roll up to Production Batch Group
    if not pbg_name:
        return

    if batch_type == "Bubble Hash":
        frappe.db.set_value(
            "Production Batch Group", pbg_name, "cost_per_gram_bubble", cost_per_gram
        )
    elif batch_type == "Rosin":
        frappe.db.set_value(
            "Production Batch Group", pbg_name, "cost_per_gram_rosin", cost_per_gram
        )

    # Also update total cost fields on PBG
    frappe.db.set_value(
        "Production Batch Group", pbg_name,
        {
            "total_material_cost": material_cost,
            "total_labor_cost": jc_cost,
        }
    )
