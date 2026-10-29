import frappe
from frappe.utils import flt

MICRON_OPERATIONS = {"Wash", "Press"}


def calculate_sub_op_costs(doc, method=None):
    op_ws_cache = {}
    ws_rate_cache = {}
    wage_cache = {}
    ws_flag_cache = {}
    total = 0.0
    total_completed_qty = 0.0

    has_labor_fields = _has_field("Job Card Time Log", "custom_labor_rate") and _has_field(
        "Job Card Time Log", "custom_labor_cost"
    )

    jc_op_ws = ""
    if doc.get("operation"):
        jc_op = doc.operation
        if jc_op not in op_ws_cache:
            op_ws_cache[jc_op] = frappe.db.get_value("Operation", jc_op, "workstation") or ""
        jc_op_ws = op_ws_cache[jc_op]

    for row in (doc.time_logs or []):
        ws_name = row.get("custom_workstation") or None

        if not ws_name and row.get("operation"):
            op = row.operation
            if op not in op_ws_cache:
                op_ws_cache[op] = frappe.db.get_value("Operation", op, "workstation") or ""
            ws_name = op_ws_cache[op]

        if not ws_name:
            ws_name = doc.workstation or ""

        if not ws_name:
            ws_name = jc_op_ws

        hour_rate = 0.0
        if ws_name:
            if ws_name not in ws_rate_cache:
                ws_rate_cache[ws_name] = flt(
                    frappe.db.get_value("Workstation", ws_name, "custom_total_operating_cost") or 0
                )
            hour_rate = ws_rate_cache[ws_name]

        time_hrs = flt(row.get("time_in_mins") or 0) / 60.0
        machine_cost = time_hrs * hour_rate

        labor_rate, labor_cost = _labor_for_row(row, ws_name, wage_cache, ws_flag_cache)
        cost = round(machine_cost + labor_cost, 6)

        row.custom_workstation = ws_name
        row.custom_hour_rate = hour_rate
        row.custom_sub_op_cost = cost

        values = {
            "custom_workstation": ws_name,
            "custom_hour_rate":   hour_rate,
            "custom_sub_op_cost": cost,
        }

        if has_labor_fields:
            row.custom_labor_rate = labor_rate
            row.custom_labor_cost = labor_cost
            values["custom_labor_rate"] = labor_rate
            values["custom_labor_cost"] = labor_cost

        if row.get("name") and not row.get("name", "").startswith("new-"):
            frappe.db.set_value("Job Card Time Log", row.name, values, update_modified=False)

        total += cost
        total_completed_qty += flt(row.get("completed_qty") or 0)

    doc.custom_sub_op_total_cost = total
    doc.total_completed_qty = total_completed_qty
    frappe.db.set_value("Job Card", doc.name, {
        "custom_sub_op_total_cost": total,
        "total_completed_qty": total_completed_qty,
    }, update_modified=False)

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
    from frappe.utils import flt
    if flt(doc.total_completed_qty):
        doc.for_quantity = doc.total_completed_qty


def sync_micron_total_to_time_log(doc, method=None):
    rows = doc.get("custom_micron_collection_detail") or []
    logs = doc.get("time_logs") or []
    if doc.docstatus != 0 or not rows or not logs:
        return

    total = sum(flt(r.get("grams_collected")) for r in rows)

    before = doc.get_doc_before_save()
    if before and total == sum(
        flt(r.get("grams_collected")) for r in (before.get("custom_micron_collection_detail") or [])
    ):
        return
    set_output_qty(doc, total)


def set_output_qty(doc, qty):
    logs = doc.get("time_logs") or []
    if not logs:
        return
    with_qty = [tl for tl in logs if flt(tl.completed_qty) > 0]
    target = with_qty[-1] if with_qty else logs[-1]
    for tl in logs:
        tl.completed_qty = 0
    target.completed_qty = qty


def validate(doc, method=None):
    if doc.operation not in MICRON_OPERATIONS:
        return

    rows = doc.get("custom_micron_collection_detail") or []

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

WORKSTATION_LABOR_FLAG = "custom_employee_wise_labor_cost"
EMPLOYEE_WAGE_FIELD = "custom_hourly_wage_rate"

TIME_LOG_FIELD_ORDER = [
    "employee", "from_time", "to_time", "column_break_2", "time_in_mins",
    "completed_qty", "operation", "custom_workstation", "custom_hour_rate",
    "custom_labor_rate", "custom_labor_cost", "custom_sub_op_cost",
]


def install_custom_fields():
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


def _has_field(doctype, fieldname):
    try:
        return bool(frappe.get_meta(doctype).has_field(fieldname))
    except Exception:
        return False


def _labor_for_row(row, ws_name, wage_cache, ws_flag_cache):
    if not ws_name or not row.get("employee"):
        return 0.0, 0.0

    if not _has_field("Workstation", WORKSTATION_LABOR_FLAG):
        return 0.0, 0.0

    if ws_name not in ws_flag_cache:
        ws_flag_cache[ws_name] = bool(
            frappe.db.get_value("Workstation", ws_name, WORKSTATION_LABOR_FLAG)
        )
    if not ws_flag_cache[ws_name]:
        return 0.0, 0.0

    if not _has_field("Employee", EMPLOYEE_WAGE_FIELD):
        return 0.0, 0.0

    employee = row.employee
    if employee not in wage_cache:
        wage_cache[employee] = flt(
            frappe.db.get_value("Employee", employee, EMPLOYEE_WAGE_FIELD) or 0
        )

    rate = wage_cache[employee]
    cost = round(rate / 60.0 * flt(row.get("time_in_mins") or 0), 6)
    return rate, cost
