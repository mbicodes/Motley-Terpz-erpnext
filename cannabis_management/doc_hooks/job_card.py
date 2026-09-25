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
    wage_cache = {}
    ws_flag_cache = {}
    total = 0.0
    total_completed_qty = 0.0

    # Pre-resolve the Job Card's own operation workstation as ultimate fallback
    jc_op_ws = ""
    if doc.get("operation"):
        jc_op = doc.operation
        if jc_op not in op_ws_cache:
            op_ws_cache[jc_op] = frappe.db.get_value("Operation", jc_op, "workstation") or ""
        jc_op_ws = op_ws_cache[jc_op]

    for row in (doc.time_logs or []):
        # 0. workstation picked explicitly for this time log (Start popup)
        ws_name = row.get("custom_workstation") or None

        # 1. row-level operation
        if not ws_name and row.get("operation"):
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
        machine_cost = time_hrs * hour_rate

        # Operator's wage for these minutes, when the workstation is costed
        # employee-wise. Zero otherwise, so the total is unchanged for every
        # workstation that has not opted in.
        labor_rate, labor_cost = _labor_for_row(row, ws_name, wage_cache, ws_flag_cache)
        cost = round(machine_cost + labor_cost, 6)

        # Write directly to child row in memory (picked up by validate → save)
        row.custom_workstation = ws_name
        row.custom_hour_rate = hour_rate
        row.custom_labor_rate = labor_rate
        row.custom_labor_cost = labor_cost
        row.custom_sub_op_cost = cost

        # Also persist explicitly in case this runs from on_submit after the doc save
        if row.get("name") and not row.get("name", "").startswith("new-"):
            frappe.db.set_value("Job Card Time Log", row.name, {
                "custom_workstation": ws_name,
                "custom_hour_rate":   hour_rate,
                "custom_labor_rate":  labor_rate,
                "custom_labor_cost":  labor_cost,
                "custom_sub_op_cost": cost,
            }, update_modified=False)

        total += cost
        total_completed_qty += flt(row.get("completed_qty") or 0)

    doc.custom_sub_op_total_cost = total
    doc.total_completed_qty = total_completed_qty
    frappe.db.set_value("Job Card", doc.name, {
        "custom_sub_op_total_cost": total,
        "total_completed_qty": total_completed_qty,
    }, update_modified=False)

    # On submit: roll up all submitted Job Cards for this Work Order → actual_operating_cost
    if doc.docstatus == 1 and doc.get("work_order"):
        wo_total = frappe.db.sql("""
            SELECT COALESCE(SUM(custom_sub_op_total_cost), 0)
            FROM `tabJob Card`
            WHERE work_order = %s AND docstatus = 1
        """, doc.work_order)[0][0]
        frappe.db.set_value("Work Order", doc.work_order, {
            "actual_operating_cost": flt(wo_total),
            "total_operating_cost":  flt(wo_total),
        }, update_modified=False)


def bypass_qty_to_manufacture_check(doc, method=None):
    """
    ERPNext blocks submit when total_completed_qty != for_quantity.
    Set for_quantity = total_completed_qty so the check always passes.
    """
    from frappe.utils import flt
    if flt(doc.total_completed_qty):
        doc.for_quantity = doc.total_completed_qty


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

# ── Employee-wise labour cost ───────────────────────────────────────────────
#
# A workstation can be billed for the machine alone, or for the machine plus
# whoever ran it. Workstation.custom_employee_wise_labor_cost turns the second
# on; when it is set, each time log picks up that employee's hourly wage and
# adds the labour for the minutes logged on top of the workstation rate.

WORKSTATION_LABOR_FLAG = "custom_employee_wise_labor_cost"
EMPLOYEE_WAGE_FIELD = "custom_hourly_wage_rate"

TIME_LOG_FIELD_ORDER = [
    "employee", "from_time", "to_time", "column_break_2", "time_in_mins",
    "completed_qty", "operation", "custom_workstation", "custom_hour_rate",
    "custom_labor_rate", "custom_labor_cost", "custom_sub_op_cost",
]


def install_custom_fields():
    """Idempotent; re-asserted on every migrate via after_migrate."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {
            "Workstation": [
                {
                    "fieldname": WORKSTATION_LABOR_FLAG,
                    "label": "Employee wise labor Cost",
                    "fieldtype": "Check",
                    "default": "0",
                    "insert_after": "custom_total_operating_cost",
                    "description": (
                        "Charge the operator's hourly wage on top of this "
                        "workstation's rate, per time log."
                    ),
                }
            ],
            "Job Card Time Log": [
                {
                    "fieldname": "custom_labor_rate",
                    "label": "Labor Rate / Hour",
                    "fieldtype": "Currency",
                    "read_only": 1,
                    "insert_after": "custom_hour_rate",
                    "description": "From the employee's hourly wage rate.",
                },
                {
                    "fieldname": "custom_labor_cost",
                    "label": "Labor Cost",
                    "fieldtype": "Currency",
                    "read_only": 1,
                    "insert_after": "custom_labor_rate",
                    "description": "Labor rate / 60 x minutes logged. Included in Sub Op Cost.",
                },
            ],
        },
        ignore_validate=True,
    )

    # The grid's column order is pinned by a Property Setter, so new fields
    # stay invisible until they are named in it.
    frappe.make_property_setter(
        {
            "doctype": "Job Card Time Log",
            "doctype_or_field": "DocType",
            "property": "field_order",
            "value": frappe.as_json(TIME_LOG_FIELD_ORDER),
            "property_type": "Text",
        },
        is_system_generated=False,
    )


def _labor_for_row(row, ws_name, wage_cache, ws_flag_cache):
    """(rate, cost) for a time log row -- zero unless the workstation asks
    for employee-wise costing and the row names an employee."""
    if not ws_name or not row.get("employee"):
        return 0.0, 0.0

    if ws_name not in ws_flag_cache:
        ws_flag_cache[ws_name] = bool(
            frappe.db.get_value("Workstation", ws_name, WORKSTATION_LABOR_FLAG)
        )
    if not ws_flag_cache[ws_name]:
        return 0.0, 0.0

    employee = row.employee
    if employee not in wage_cache:
        wage_cache[employee] = flt(
            frappe.db.get_value("Employee", employee, EMPLOYEE_WAGE_FIELD) or 0
        )

    rate = wage_cache[employee]
    cost = round(rate / 60.0 * flt(row.get("time_in_mins") or 0), 6)
    return rate, cost
