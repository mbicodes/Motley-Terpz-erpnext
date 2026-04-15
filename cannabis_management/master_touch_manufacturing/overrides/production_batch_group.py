"""
Production Batch Group override for Masters Touch Manufacturing.

Fired by hooks.py:
    doc_events["Production Batch Group"]["on_update"]

Responsibilities:
- Batch Sequence Lock: prevent creating a new PBG for an entity/strain
  while a prior PBG is still open (status != Closed).
  Only Lab Supervisor or Production Manager can override.
- When status transitions to "Closed" and the linked BOM is a toll BOM,
  auto-create a draft Sales Invoice in Motley Terpz to bill the toll
  customer for the processing fee.
"""

import frappe
from frappe.utils import flt, today


def on_update(doc, method=None):
    _check_batch_sequence_lock(doc)
    if doc.status == "Closed":
        _create_toll_invoice(doc)


# ── Batch Sequence Lock ────────────────────────────────────────────────────────

def on_before_insert(doc, method=None):
    """Block new PBG if a prior open PBG exists for the same source entity."""
    _check_batch_sequence_lock(doc)


def _check_batch_sequence_lock(doc):
    """
    A new (or re-opened) PBG cannot be submitted for a given source_entity
    while another PBG for that entity is not Closed.
    Lab Supervisor / Production Manager can bypass.
    """
    if not doc.source_entity:
        return

    bypass_roles = {"Lab Supervisor", "Production Manager", "System Manager"}
    user_roles = set(frappe.get_roles())
    if bypass_roles & user_roles:
        return  # privileged user — skip lock

    # Only check when moving to a non-Draft status (docstatus 0 = draft is fine)
    if doc.docstatus == 0:
        return

    open_pbgs = frappe.get_all(
        "Production Batch Group",
        filters={
            "source_entity": doc.source_entity,
            "status": ["!=", "Closed"],
            "name": ["!=", doc.name],
            "docstatus": 1,
        },
        fields=["name", "status"],
    )
    if open_pbgs:
        names = ", ".join(p.name for p in open_pbgs)
        frappe.throw(
            f"Cannot submit this Production Batch Group — the following PBG(s) for "
            f"{doc.source_entity} are still open: {names}. "
            "Close them first, or ask a Lab Supervisor to override.",
            title="Batch Sequence Lock",
        )


# ── Toll Fee Invoice ───────────────────────────────────────────────────────────

def _create_toll_invoice(doc):
    """
    When PBG closes, if the linked Work Order uses a Toll BOM, create a
    draft Sales Invoice in Motley Terpz for:
        toll_fee_g × total_rosin_yield_g (or total_bubble_yield_g for hash-only runs)
    """
    wo_name = doc.get("work_order_ref")
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

    toll_fee_g = flt(bom_data.custom_toll_fee_g)
    if toll_fee_g <= 0:
        return

    # Determine quantity billed: prefer rosin yield; fall back to bubble hash
    qty_g = flt(doc.get("total_rosin_yield_g") or 0)
    if qty_g <= 0:
        qty_g = flt(doc.get("total_bubble_yield_g") or 0)
    if qty_g <= 0:
        return

    # Toll customer is stored on the linked Work Order
    toll_customer = frappe.db.get_value("Work Order", wo_name, "custom_toll_customer")
    if not toll_customer:
        toll_customer = "TSBC Ranch"  # default

    # Don't create a duplicate invoice for the same PBG
    existing = frappe.db.get_value(
        "Sales Invoice",
        {"custom_production_batch_group": doc.name, "docstatus": ["!=", 2]},
        "name",
    )
    if existing:
        return

    # Toll service item
    toll_item = "toll-processing-fee"
    if not frappe.db.exists("Item", toll_item):
        frappe.log_error(
            f"MTM: Toll service item '{toll_item}' not found. "
            "Run setup_mtm_phases patch first.",
            "Toll Invoice Error",
        )
        return

    try:
        si = frappe.new_doc("Sales Invoice")
        si.company = "Motley Terpz"
        si.customer = toll_customer
        si.posting_date = today()
        si.due_date = today()

        # Custom field reference
        if frappe.db.has_column("Sales Invoice", "custom_production_batch_group"):
            si.custom_production_batch_group = doc.name

        si.append("items", {
            "item_code": toll_item,
            "item_name": "Toll Processing Fee",
            "description": (
                f"Toll manufacturing fee for PBG {doc.name} — "
                f"{qty_g:.2f}g @ ${toll_fee_g:.4f}/g"
            ),
            "qty": qty_g,
            "uom": "Gram",
            "rate": toll_fee_g,
            "amount": qty_g * toll_fee_g,
        })

        si.flags.ignore_permissions = True
        si.save()
        frappe.msgprint(
            f"Toll Invoice <b>{si.name}</b> created for {toll_customer} "
            f"({qty_g:.2f}g × ${toll_fee_g}/g = ${qty_g * toll_fee_g:.2f}). "
            "Review and submit.",
            alert=True,
        )
    except Exception as e:
        frappe.log_error(
            f"MTM: Failed to create toll invoice for PBG {doc.name}: {e}",
            "Toll Invoice Error",
        )
