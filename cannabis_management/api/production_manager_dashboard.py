import frappe
from frappe.utils import flt, nowdate

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
def get_dashboard_data(from_date=None, to_date=None):
    today = nowdate()
    from_date = from_date or today
    to_date   = to_date   or today

    rp = {"from_date": from_date, "to_date": to_date}
    tp = {"today": today}

    # ── 1. KPIs — always live / current state ────────────────────────────
    active_wo = frappe.db.sql("""
        SELECT COUNT(*) AS cnt FROM `tabWork Order`
        WHERE docstatus = 1 AND status IN ('Not Started','In Process')
    """, as_dict=True)

    open_jc = frappe.db.sql("""
        SELECT COUNT(*) AS cnt FROM `tabJob Card`
        WHERE docstatus != 2 AND status IN ('Open','Work In Progress')
    """, as_dict=True)

    today_output = frappe.db.sql("""
        SELECT COALESCE(SUM(produced_qty), 0) AS qty FROM `tabWork Order`
        WHERE docstatus = 1 AND DATE(modified) = %(today)s
    """, tp, as_dict=True)

    overdue_wo = frappe.db.sql("""
        SELECT COUNT(*) AS cnt FROM `tabWork Order`
        WHERE docstatus = 1
          AND planned_end_date < %(today)s
          AND status NOT IN ('Completed','Stopped')
    """, tp, as_dict=True)

    # ── 2. Operations breakdown ──────────────────────────────────────────
    operations = frappe.db.sql("""
        SELECT
            COALESCE(jc.operation, 'Unknown') AS operation,
            SUM(jctl.time_in_mins)            AS total_mins,
            COUNT(DISTINCT jc.name)           AS jc_count
        FROM `tabJob Card Time Log` jctl
        JOIN `tabJob Card`   jc ON jc.name   = jctl.parent
        JOIN `tabWork Order` wo ON wo.name   = jc.work_order
        WHERE jc.docstatus != 2
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY jc.operation
        ORDER BY total_mins DESC
        LIMIT 10
    """, rp, as_dict=True)

    # ── 3. Workstation utilization ───────────────────────────────────────
    workstations = frappe.db.sql("""
        SELECT
            COALESCE(jc.workstation, 'Unassigned')                       AS workstation,
            COUNT(*)                                                       AS total_jc,
            SUM(CASE WHEN jc.status = 'Work In Progress' THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN jc.status = 'Completed'        THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN jc.status = 'Open'             THEN 1 ELSE 0 END) AS open_count
        FROM `tabJob Card` jc
        JOIN `tabWork Order` wo ON wo.name = jc.work_order
        WHERE jc.docstatus != 2
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY jc.workstation
        ORDER BY active DESC, total_jc DESC
        LIMIT 12
    """, rp, as_dict=True)

    # ── 4. Job Cards table ───────────────────────────────────────────────
    job_cards = frappe.db.sql("""
        SELECT
            jc.name,
            jc.operation,
            jc.workstation,
            jc.status,
            jc.for_quantity,
            jc.work_order,
            jc.production_item,
            COALESCE(emp.employee_name, tl.employee, '') AS employee_name,
            COALESCE(tl.total_mins, 0)                   AS total_mins
        FROM `tabJob Card` jc
        JOIN `tabWork Order` wo ON wo.name = jc.work_order
        LEFT JOIN (
            SELECT parent,
                   SUBSTRING_INDEX(GROUP_CONCAT(employee ORDER BY time_in_mins DESC), ',', 1) AS employee,
                   SUM(time_in_mins) AS total_mins
            FROM `tabJob Card Time Log`
            GROUP BY parent
        ) tl ON tl.parent = jc.name
        LEFT JOIN `tabEmployee` emp ON emp.name = tl.employee
        WHERE jc.docstatus != 2
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
        ORDER BY jc.modified DESC
        LIMIT 30
    """, rp, as_dict=True)

    # ── 5. WO Pipeline ───────────────────────────────────────────────────
    pipeline = frappe.db.sql("""
        SELECT
            wo.name,
            wo.item_name,
            wo.production_item     AS item_code,
            wo.qty,
            wo.produced_qty,
            GREATEST(wo.qty - wo.produced_qty, 0) AS remaining_qty,
            CASE WHEN wo.qty > 0
                 THEN ROUND(wo.produced_qty / wo.qty * 100, 1) ELSE 0 END AS completion_pct,
            wo.status,
            wo.planned_start_date,
            wo.planned_end_date,
            CASE WHEN wo.planned_end_date < %(today)s
                      AND wo.status NOT IN ('Completed','Stopped')
                 THEN 1 ELSE 0 END AS is_overdue
        FROM `tabWork Order` wo
        WHERE wo.docstatus = 1
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
        ORDER BY is_overdue DESC, wo.planned_end_date ASC
        LIMIT 25
    """, {**rp, **tp}, as_dict=True)

    # ── 6. Micron ────────────────────────────────────────────────────────
    micron = []
    mt = _get_micron_table()
    if mt:
        try:
            micron = frappe.db.sql(f"""
                SELECT
                    jcm.micron_size,
                    COALESCE(SUM(jcm.grams_collected), 0) AS grams
                FROM `{mt}` jcm
                JOIN `tabJob Card`   jc ON jc.name = jcm.parent
                JOIN `tabWork Order` wo ON wo.name = jc.work_order
                WHERE jc.docstatus != 2
                  AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
                  AND jcm.micron_size IS NOT NULL
                  AND jcm.grams_collected > 0
                GROUP BY jcm.micron_size
                ORDER BY FIELD(jcm.micron_size,'150U','120U','90U','73U','45U','25U')
            """, rp, as_dict=True)
        except Exception:
            micron = []

    # ── 7. Employee time log ─────────────────────────────────────────────
    employees = frappe.db.sql("""
        SELECT
            jctl.employee,
            COALESCE(emp.employee_name, jctl.employee) AS employee_name,
            SUM(jctl.time_in_mins)   AS total_mins,
            COUNT(DISTINCT jc.name)  AS jc_count
        FROM `tabJob Card Time Log` jctl
        JOIN `tabJob Card`   jc  ON jc.name  = jctl.parent
        JOIN `tabWork Order` wo  ON wo.name  = jc.work_order
        LEFT JOIN `tabEmployee` emp ON emp.name = jctl.employee
        WHERE jc.docstatus != 2
          AND DATE(wo.modified) BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY jctl.employee, emp.employee_name
        HAVING total_mins > 0
        ORDER BY total_mins DESC
        LIMIT 10
    """, rp, as_dict=True)

    # ── 8. LBS Washed (Hash Recording) ──────────────────────────────────────
    lbs_kpi = frappe.db.sql("""
        SELECT
            COALESCE(SUM(total_quantity), 0)  AS total_lbs,
            COUNT(*)                           AS runs,
            COALESCE(AVG(total_quantity), 0)  AS avg_per_run
        FROM `tabHash Recording`
        WHERE docstatus = 1
          AND DATE(creation) BETWEEN %(from_date)s AND %(to_date)s
    """, rp, as_dict=True)

    lbs_daily = frappe.db.sql("""
        SELECT
            DATE(creation)         AS dt,
            SUM(total_quantity)    AS total_lbs,
            COUNT(*)               AS runs
        FROM `tabHash Recording`
        WHERE docstatus = 1
          AND DATE(creation) BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY DATE(creation)
        ORDER BY dt
    """, rp, as_dict=True)

    # ── 9. Logistics Pipeline (Sales Orders — live, not date-filtered) ────
    logistics_kpis = frappe.db.sql("""
        SELECT
            status,
            COUNT(*)                           AS cnt,
            COALESCE(SUM(grand_total), 0)      AS total_value
        FROM `tabSales Order`
        WHERE docstatus = 1
          AND status NOT IN ('Completed','Cancelled','Closed')
        GROUP BY status
        ORDER BY cnt DESC
    """, as_dict=True)

    logistics_orders = frappe.db.sql("""
        SELECT
            so.name,
            so.customer,
            so.status,
            so.grand_total,
            so.transaction_date,
            so.delivery_date
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
          AND so.status NOT IN ('Completed','Cancelled','Closed')
        ORDER BY so.delivery_date ASC
        LIMIT 25
    """, as_dict=True)

    lk = lbs_kpi[0] if lbs_kpi else {}

    return {
        "kpis": {
            "active_wo":    int((active_wo[0]    or {}).get("cnt") or 0),
            "open_jc":      int((open_jc[0]      or {}).get("cnt") or 0),
            "today_output": flt((today_output[0] or {}).get("qty") or 0),
            "overdue_wo":   int((overdue_wo[0]   or {}).get("cnt") or 0),
        },
        "operations":  operations,
        "workstations": workstations,
        "job_cards":   job_cards,
        "pipeline":    pipeline,
        "micron":      micron,
        "employees":   employees,
        "lbs_washed": {
            "total_lbs":   flt(lk.get("total_lbs")),
            "runs":        int(lk.get("runs") or 0),
            "avg_per_run": flt(lk.get("avg_per_run")),
            "daily":       lbs_daily,
        },
        "logistics": {
            "kpis":   logistics_kpis,
            "orders": logistics_orders,
        },
    }
