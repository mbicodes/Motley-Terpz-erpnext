# cannabis_management/hooks/job_card.py

import frappe

MICRON_OPERATIONS = {"Wash", "Press"}


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