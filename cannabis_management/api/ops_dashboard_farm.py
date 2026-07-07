import frappe
from frappe.utils import today


def _resolve_range(from_date, to_date):
    return (from_date or today(), to_date or today())


# ---------------------------------------------------------------------------
# Section A: Daily
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_daily_summary(from_date=None, to_date=None):
    from_date, to_date = _resolve_range(from_date, to_date)

    logs = frappe.get_all(
        "Farm Daily Log",
        filters={"log_date": ["between", [from_date, to_date]]},
        fields=["logged_by", "scouting_completed", "issue_reported", "dcc_ready_status", "metrc_open_corrections"],
    )

    total = len(logs) or 1
    scouting_pct = sum(1 for l in logs if l.scouting_completed) / total * 100
    issues_count = sum(1 for l in logs if l.issue_reported)
    dcc_pct = sum(1 for l in logs if l.dcc_ready_status == "Pass") / total * 100
    open_corrections = sum(l.metrc_open_corrections or 0 for l in logs)

    by_employee = {}
    for l in logs:
        emp = l.logged_by or "Unassigned"
        by_employee.setdefault(emp, {"total": 0, "scouted": 0})
        by_employee[emp]["total"] += 1
        if l.scouting_completed:
            by_employee[emp]["scouted"] += 1

    employee_breakdown = [
        {"employee": emp, "scouting_pct": round(v["scouted"] / v["total"] * 100, 1) if v["total"] else 0}
        for emp, v in by_employee.items()
    ]

    return {
        "scouting_pct": round(scouting_pct, 1),
        "issues_count": issues_count,
        "dcc_pct": round(dcc_pct, 1),
        "open_corrections": open_corrections,
        "total_logs": len(logs),
        "employee_breakdown": employee_breakdown,
    }


# ---------------------------------------------------------------------------
# Section B: Harvest Window
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_harvest_window(from_date=None, to_date=None):
    """Single seasonal KPI: total lbs taken down across all harvest events
    in range. No per-harvest target exists yet in Farm Settings, so target
    is always None (frontend shows "[TBD]") until one is added."""
    from_date, to_date = _resolve_range(from_date, to_date)

    rows = frappe.get_all(
        "Farm Production Batch",
        filters={"harvest_date": ["between", [from_date, to_date]]},
        fields=["lbs_produced"],
    )
    total_lbs = sum(r.lbs_produced or 0 for r in rows)

    return {
        "target": None,
        "actual": total_lbs or None,
        "count": len(rows),
    }


# ---------------------------------------------------------------------------
# Section C: Labor Efficiency — Active Sessions
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_labor_efficiency(from_date=None, to_date=None):
    from_date, to_date = _resolve_range(from_date, to_date)
    settings = frappe.get_single("Farm Settings")

    clones_avg = frappe.db.sql(
        """
        SELECT AVG(clones_per_hour) FROM `tabCloning Batch`
        WHERE session_date BETWEEN %s AND %s AND docstatus = 1 AND status = 'Active'
        """,
        (from_date, to_date),
    )[0][0] or 0

    def task_avg(task_type):
        return frappe.db.sql(
            """
            SELECT AVG(rate_per_hour) FROM `tabFarm Labor Session`
            WHERE task_type = %s AND session_date BETWEEN %s AND %s
            AND docstatus = 1 AND status = 'Active'
            """,
            (task_type, from_date, to_date),
        )[0][0] or 0

    return {
        "clones": {"actual": round(clones_avg, 2), "target": settings.clones_per_hour_target or 0},
        "planting": {"actual": round(task_avg("Planting"), 2), "target": settings.planting_rate_target or 0},
        "deleaf": {"actual": round(task_avg("Deleaf"), 2), "target": settings.deleaf_rate_target or 0},
        "bucking": {"actual": round(task_avg("Bucking"), 2), "target": settings.bucking_rate_target or 0},
    }


@frappe.whitelist()
def archive_cloning_batches(from_date=None, to_date=None):
    from_date, to_date = _resolve_range(from_date, to_date)
    names = frappe.get_all(
        "Cloning Batch",
        filters={"session_date": ["between", [from_date, to_date]], "status": "Active"},
        pluck="name",
    )
    for n in names:
        frappe.db.set_value("Cloning Batch", n, "status", "Archived")
    frappe.db.commit()
    return len(names)


@frappe.whitelist()
def archive_labor_sessions(task_type, from_date=None, to_date=None):
    from_date, to_date = _resolve_range(from_date, to_date)
    names = frappe.get_all(
        "Farm Labor Session",
        filters={"task_type": task_type, "session_date": ["between", [from_date, to_date]], "status": "Active"},
        pluck="name",
    )
    for n in names:
        frappe.db.set_value("Farm Labor Session", n, "status", "Archived")
    frappe.db.commit()
    return len(names)


# ---------------------------------------------------------------------------
# Section D: Archived Sessions
# ---------------------------------------------------------------------------

TASK_TARGET_FIELD = {
    "Planting": "planting_rate_target",
    "Deleaf": "deleaf_rate_target",
    "Bucking": "bucking_rate_target",
}


@frappe.whitelist()
def get_archived_sessions():
    settings = frappe.get_single("Farm Settings")

    cloning = frappe.get_all(
        "Cloning Batch",
        filters={"status": "Archived"},
        fields=["name", "session_date", "clones_per_hour"],
        order_by="session_date desc",
    )
    for c in cloning:
        c["target"] = settings.clones_per_hour_target or None

    labor = frappe.get_all(
        "Farm Labor Session",
        filters={"status": "Archived"},
        fields=["name", "task_type", "session_date", "rate_per_hour"],
        order_by="session_date desc",
    )
    for l in labor:
        l["target"] = getattr(settings, TASK_TARGET_FIELD.get(l.task_type, ""), None) or None

    return {"cloning": cloning, "labor": labor}


@frappe.whitelist()
def restore_cloning_batch(name):
    frappe.db.set_value("Cloning Batch", name, "status", "Active")
    frappe.db.commit()
    return "Active"


@frappe.whitelist()
def restore_labor_session(name):
    frappe.db.set_value("Farm Labor Session", name, "status", "Active")
    frappe.db.commit()
    return "Active"
