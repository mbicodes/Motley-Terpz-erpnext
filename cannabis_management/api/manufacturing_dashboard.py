import frappe
from frappe.utils import flt, add_days, nowdate

# Auto-detect micron child table (same candidates as traceability report)
_MICRON_CANDIDATES = [
    "tabJob Card Micron Detail",
    "tabJob Card Micron",
    "tabCannabis Job Card Micron Detail",
    "tabCannabis Micron Detail",
    "tabMicron Detail",
]
_micron_table_cache = {}


def _get_micron_table():
    site = frappe.local.site
    if site in _micron_table_cache:
        return _micron_table_cache[site]
    rows = frappe.db.sql(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE %s",
        ("%micron%",), as_list=True,
    )
    found = [r[0] for r in rows]
    chosen = next((c for c in _MICRON_CANDIDATES if c in found), None) or (found[0] if found else None)
    _micron_table_cache[site] = chosen
    return chosen


@frappe.whitelist()
def get_dashboard_data(from_date=None, to_date=None, company=""):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    params = {
        "from_date": from_date,
        "to_date": to_date,
    }
    company_wo  = ""
    company_jc  = ""
    company_se  = ""

    # ── 1. Work Order KPIs ────────────────────────────────────────────────
    wo_kpis = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(wo.qty), 0)               AS planned_qty,
            COALESCE(SUM(wo.produced_qty), 0)       AS produced_qty,
            COUNT(*)                                AS wo_count,
            SUM(CASE WHEN wo.status = 'Completed' THEN 1 ELSE 0 END) AS completed_wo,
            COALESCE(SUM(wo.process_loss_qty), 0)   AS process_loss
        FROM `tabWork Order` wo
        WHERE wo.docstatus = 1
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
          {company_wo}
    """, params, as_dict=True)
    w = wo_kpis[0] if wo_kpis else {}

    # ── 2. Job Card KPIs ──────────────────────────────────────────────────
    jc_kpis = frappe.db.sql(f"""
        SELECT
            COUNT(*) AS jc_count,
            SUM(CASE WHEN jc.status = 'Completed' THEN 1 ELSE 0 END) AS jc_completed
        FROM `tabJob Card` jc
        JOIN `tabWork Order` wo ON wo.name = jc.work_order
        WHERE jc.docstatus != 2
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
          {company_wo}
    """, params, as_dict=True)
    j = jc_kpis[0] if jc_kpis else {}

    # ── 3. WO Status breakdown ────────────────────────────────────────────
    wo_status = frappe.db.sql(f"""
        SELECT wo.status, COUNT(*) AS cnt
        FROM `tabWork Order` wo
        WHERE wo.docstatus = 1
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
          {company_wo}
        GROUP BY wo.status
        ORDER BY cnt DESC
    """, params, as_dict=True)

    # ── 4. JC Status breakdown ────────────────────────────────────────────
    jc_status = frappe.db.sql(f"""
        SELECT jc.status, COUNT(*) AS cnt
        FROM `tabJob Card` jc
        JOIN `tabWork Order` wo ON wo.name = jc.work_order
        WHERE jc.docstatus != 2
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
          {company_wo}
        GROUP BY jc.status
        ORDER BY cnt DESC
    """, params, as_dict=True)

    # ── 5. Throughput trend (daily) ───────────────────────────────────────
    throughput = frappe.db.sql(f"""
        SELECT
            DATE(wo.modified) AS dt,
            COALESCE(SUM(wo.qty), 0)           AS planned,
            COALESCE(SUM(wo.produced_qty), 0)  AS produced
        FROM `tabWork Order` wo
        WHERE wo.docstatus = 1
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
          {company_wo}
        GROUP BY DATE(wo.modified)
        ORDER BY dt
        LIMIT 14
    """, params, as_dict=True)

    # ── 6. Micron distribution ────────────────────────────────────────────
    micron = []
    mt = _get_micron_table()
    if mt:
        try:
            micron = frappe.db.sql(f"""
                SELECT
                    jcm.micron_size,
                    COALESCE(SUM(jcm.grams_collected), 0) AS grams
                FROM `{mt}` jcm
                JOIN `tabJob Card` jc ON jc.name = jcm.parent
                JOIN `tabWork Order` wo ON wo.name = jc.work_order
                WHERE jc.docstatus != 2
                  AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
                  {company_wo}
                  AND jcm.micron_size IS NOT NULL
                  AND jcm.grams_collected > 0
                GROUP BY jcm.micron_size
                ORDER BY FIELD(jcm.micron_size, '150U','120U','90U','73U','45U','25U')
            """, params, as_dict=True)
        except Exception:
            micron = []

    # ── 7. Cost breakdown from Manufacture SEs ────────────────────────────
    costs_rows = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(sed.basic_amount), 0)          AS raw_material_cost,
            COALESCE(SUM(se.total_additional_costs), 0) AS operating_cost,
            COALESCE(SUM(sed.qty), 0)                   AS total_produced_g
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.docstatus = 1
          AND se.purpose = 'Manufacture'
          AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND sed.is_finished_item = 1
          {company_se}
    """, params, as_dict=True)
    cost = costs_rows[0] if costs_rows else {}

    # ── 8. Employee productivity ──────────────────────────────────────────
    employees = frappe.db.sql(f"""
        SELECT
            jctl.employee,
            COALESCE(emp.employee_name, jctl.employee) AS employee_name,
            SUM(jctl.time_in_mins) AS total_mins,
            SUM(
                jc.for_quantity * jctl.time_in_mins /
                NULLIF((
                    SELECT SUM(t2.time_in_mins)
                    FROM `tabJob Card Time Log` t2
                    WHERE t2.parent = jc.name
                ), 0)
            ) AS weighted_qty
        FROM `tabJob Card Time Log` jctl
        JOIN `tabJob Card` jc ON jc.name = jctl.parent
        JOIN `tabWork Order` wo ON wo.name = jc.work_order
        LEFT JOIN `tabEmployee` emp ON emp.name = jctl.employee
        WHERE jc.docstatus != 2
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
          {company_wo}
        GROUP BY jctl.employee, emp.employee_name
        HAVING total_mins > 0
        ORDER BY weighted_qty DESC
        LIMIT 8
    """, params, as_dict=True)

    for emp in employees:
        mins = flt(emp.get("total_mins"))
        qty = flt(emp.get("weighted_qty"))
        emp["qty_per_hour"] = round(qty / (mins / 60), 1) if mins > 0 else 0.0

    # ── 9. Work Orders list ───────────────────────────────────────────────
    work_orders = frappe.db.sql(f"""
        SELECT
            wo.name,
            wo.production_item  AS item_code,
            wo.item_name,
            wo.qty,
            wo.produced_qty,
            GREATEST(wo.qty - wo.produced_qty, 0) AS remaining_qty,
            CASE WHEN wo.qty > 0
                 THEN ROUND(wo.produced_qty / wo.qty * 100, 1)
                 ELSE 0 END   AS completion_pct,
            wo.status,
            wo.planned_start_date,
            wo.planned_end_date
        FROM `tabWork Order` wo
        WHERE wo.docstatus = 1
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
          {company_wo}
        ORDER BY wo.modified DESC
        LIMIT 25
    """, params, as_dict=True)

    planned = flt(w.get("planned_qty"))
    produced = flt(w.get("produced_qty"))

    return {
        "kpis": {
            "planned_qty":  planned,
            "produced_qty": produced,
            "remaining_qty": max(planned - produced, 0),
            "process_loss": flt(w.get("process_loss")),
            "wo_count":     int(w.get("wo_count") or 0),
            "completed_wo": int(w.get("completed_wo") or 0),
            "jc_count":     int(j.get("jc_count") or 0),
            "jc_completed": int(j.get("jc_completed") or 0),
        },
        "wo_status":   wo_status,
        "jc_status":   jc_status,
        "throughput":  throughput,
        "micron":      micron,
        "costs": {
            "raw_material":   flt(cost.get("raw_material_cost")),
            "operating":      flt(cost.get("operating_cost")),
            "total_produced_g": flt(cost.get("total_produced_g")),
        },
        "employees":   employees,
        "work_orders": work_orders,
    }
