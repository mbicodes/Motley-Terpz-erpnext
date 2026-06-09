# cannabis_management/hooks/job_card.py

import frappe
from frappe.utils import flt

MICRON_OPERATIONS = {"Wash", "Press"}


def calculate_sub_op_costs(doc, method=None):
    """
    For each time_log row, resolve workstation via the row's operation (sub-op)
    → Operation.workstation, falling back to Job Card.workstation.
    Write workstation, hourly rate, and cost back onto each row,
    and total on the Job Card.
    """
    op_ws_cache = {}
    total = 0.0

    for row in (doc.time_logs or []):
        ws_name = None

        if row.get("operation"):
            op = row.operation
            if op not in op_ws_cache:
                op_ws_cache[op] = frappe.db.get_value("Operation", op, "workstation") or ""
            ws_name = op_ws_cache[op]

        if not ws_name:
            ws_name = doc.workstation or ""

        hour_rate = 0.0
        if ws_name:
            hour_rate = flt(
                frappe.db.get_value("Workstation", ws_name, "custom_total_operating_cost") or 0
            )

        time_hrs = flt(row.get("time_in_mins") or 0) / 60.0
        cost = time_hrs * hour_rate

        row.custom_workstation = ws_name
        row.custom_hour_rate = hour_rate
        row.custom_sub_op_cost = cost
        total += cost

    doc.custom_sub_op_total_cost = total


def validate(doc, method=None):
    """
    Fired on:  validate (every save)
               on_submit (before the existing override)

    Rules:
      1. Only runs when doc.operation is "Wash" or "Press".
      2. Per-row required field check fires on every save so errors
         surface early.
      3. Grams total vs total_completed_qty is enforced only when
         status == "Completed".
    """
    if doc.operation not in MICRON_OPERATIONS:
        return

    rows = doc.get("custom_micron_collection_detail") or []

    # ── Per-row validation (every save) ─────────────────────────────────────
    for i, row in enumerate(rows, start=1):
        missing = []
        if not row.get("micron_size"):     missing.append("Micron Size")
        if not row.get("grams_collected"): missing.append("Grams Collected")
        if not row.get("quality_grade"):   missing.append("Quality Grade")
        if not row.get("collected_by"):    missing.append("Collected By")

        if missing:
            frappe.throw(
                f"Micron Collection Detail — Row {i}: "
                f"please fill in: <b>{', '.join(missing)}</b>.",
                title="Missing Micron Data"
            )

        if frappe.utils.flt(row.get("grams_collected")) <= 0:
            frappe.throw(
                f"Micron Collection Detail — Row {i}: "
                f"<b>Grams Collected</b> must be greater than zero.",
                title="Invalid Quantity"
            )

    # ── Total reconciliation (Completed status only) ─────────────────────────
    if doc.status == "Completed":
        completed_qty = frappe.utils.flt(doc.total_completed_qty)

        if not rows:
            frappe.throw(
                f"This Job Card cannot be marked <b>Completed</b> — "
                f"no Micron Collection Detail rows have been entered.<br><br>"
                f"Expected total: <b>{completed_qty} g</b>.",
                title="Micron Collection Required"
            )

        micron_total = sum(frappe.utils.flt(r.get("grams_collected")) for r in rows)

        if abs(micron_total - completed_qty) > 0.001:
            frappe.throw(
                f"Micron total (<b>{micron_total:.3f} g</b>) does not match "
                f"Completed Qty (<b>{completed_qty:.3f} g</b>).<br><br>"
                f"Difference: <b>{abs(micron_total - completed_qty):.3f} g</b>. "
                f"Reconcile the micron bag entries before closing this Job Card.",
                title="Micron Total Mismatch",
                exc=frappe.ValidationError
            )