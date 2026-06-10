# cannabis_management/hooks/job_card.py

import frappe
from frappe.utils import flt

MICRON_OPERATIONS = {"Wash", "Press"}


def calculate_sub_op_costs(doc, method=None):
    """
    For each time_log row, resolve workstation via:
      1. row.operation → Operation.workstation
      2. doc.workstation  (Job Card header)
      3. doc.operation  → Operation.workstation  (Job Card's main op)
    Writes workstation, hourly rate, and sub-op cost on each row,
    plus the total on the Job Card. Uses db.set_value so changes
    persist even when called from on_submit.
    """
    op_ws_cache = {}
    ws_rate_cache = {}
    total = 0.0

    # Pre-resolve the Job Card's own operation workstation as ultimate fallback
    jc_op_ws = ""
    if doc.get("operation"):
        jc_op = doc.operation
        if jc_op not in op_ws_cache:
            op_ws_cache[jc_op] = frappe.db.get_value("Operation", jc_op, "workstation") or ""
        jc_op_ws = op_ws_cache[jc_op]

    for row in (doc.time_logs or []):
        ws_name = None

        # 1. row-level operation
        if row.get("operation"):
            op = row.operation
            if op not in op_ws_cache:
                op_ws_cache[op] = frappe.db.get_value("Operation", op, "workstation") or ""
            ws_name = op_ws_cache[op]

        # 2. Job Card header workstation
        if not ws_name:
            ws_name = doc.workstation or ""

        # 3. Job Card's main operation workstation
        if not ws_name:
            ws_name = jc_op_ws

        # Resolve hourly rate
        hour_rate = 0.0
        if ws_name:
            if ws_name not in ws_rate_cache:
                ws_rate_cache[ws_name] = flt(
                    frappe.db.get_value("Workstation", ws_name, "custom_total_operating_cost") or 0
                )
            hour_rate = ws_rate_cache[ws_name]

        time_hrs = flt(row.get("time_in_mins") or 0) / 60.0
        cost = round(time_hrs * hour_rate, 6)

        # Write directly to child row in memory (picked up by validate → save)
        row.custom_workstation = ws_name
        row.custom_hour_rate = hour_rate
        row.custom_sub_op_cost = cost

        # Also persist explicitly in case this runs from on_submit after the doc save
        if row.get("name") and not row.get("name", "").startswith("new-"):
            frappe.db.set_value("Job Card Time Log", row.name, {
                "custom_workstation": ws_name,
                "custom_hour_rate":   hour_rate,
                "custom_sub_op_cost": cost,
            }, update_modified=False)

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