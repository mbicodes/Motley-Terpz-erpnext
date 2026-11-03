import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.cannabis_management.doctype.press_production_plan.press_production_plan import groups


def execute(filters=None):
    """One line per wash (all microns) with its microns underneath: expected vs actual rosin and yield."""
    f = filters or {}
    cond, val = ["i.parenttype = 'Press Production Plan'"], {}
    for key, expr in (("company", "p.company = %(company)s"), ("from_date", "i.planned_date >= %(from_date)s"),
                      ("to_date", "i.planned_date <= %(to_date)s"), ("project", "i.project = %(project)s"),
                      ("plan", "p.name = %(plan)s"), ("row_status", "i.row_status = %(row_status)s")):
        if f.get(key):
            cond.append(expr); val[key] = f[key]
    if f.get("strain"):
        cond.append("i.strain like %(strain)s"); val["strain"] = "%" + f["strain"].strip() + "%"
    rows = frappe.db.sql(
        f"""select i.*, p.name plan from `tabPress Plan Item` i join `tabPress Production Plan` p on p.name = i.parent
        where {' and '.join(cond)} order by i.planned_date, i.sequence, p.name, i.idx""", val, as_dict=1)
    grps = groups()
    data = []
    for r in rows:
        pressed = r.row_status in ("Pressed", "Whipped") or flt(r.actual_rosin_g) > 0
        bh = flt(r.bh_planned_g)
        data.append({
            "id": r.name, "parent_id": None, "indent": 0, "planned_date": r.planned_date, "plan": r.plan,
            "strain": r.strain, "micron": _("All microns"), "project": r.project, "rosin_wo": r.rosin_work_order,
            "job_card": r.job_card, "metrc_tag": r.metrc_tag, "bh_g": bh,
            "exp_pct": flt(r.expected_rosin_g) / bh * 100 if bh else 0, "exp_rosin_g": flt(r.expected_rosin_g),
            "act_rosin_g": flt(r.actual_rosin_g) if pressed else None, "act_pct": flt(r.actual_yield) if pressed else None,
            "variance_g": flt(r.actual_rosin_g) - flt(r.expected_rosin_g) if pressed else None, "row_status": r.row_status,
        })
        split = sum(flt(r.get("g_" + g.slot)) for g in grps)
        scale = bh / split if split else 0
        for g in grps:
            act = flt(r.get("act_rosin_" + g.slot))
            data.append({
                "id": r.name + ":" + g.slot, "parent_id": r.name, "indent": 1, "strain": r.strain, "micron": g.label,
                "bh_g": flt(r.get("g_" + g.slot)) * scale, "exp_pct": flt(r.get("exp_yield_" + g.slot)),
                "exp_rosin_g": flt(r.get("exp_rosin_" + g.slot)), "act_rosin_g": act if pressed else None,
                "act_pct": flt(r.get("act_yield_" + g.slot)) if pressed else None,
                "variance_g": act - flt(r.get("exp_rosin_" + g.slot)) if pressed else None,
            })
    L = lambda n, l, t="Data", o=None, w=110: {"fieldname": n, "label": _(l), "fieldtype": t, "options": o, "width": w}
    cols = [L("strain", "Strain", w=190), L("micron", "Micron", w=110), L("planned_date", "Planned Date", "Date"),
            L("plan", "Plan", "Link", "Press Production Plan", 130), L("project", "Project", "Link", "Project"),
            L("bh_g", "BH (g)", "Float"), L("exp_pct", "Exp. Yield %", "Percent"), L("exp_rosin_g", "Exp. Rosin (g)", "Float"),
            L("act_rosin_g", "Actual Rosin (g)", "Float"), L("act_pct", "Actual Yield %", "Percent"),
            L("variance_g", "Variance (g)", "Float"), L("row_status", "Status", w=95),
            L("rosin_wo", "Rosin WO", "Link", "Work Order", 150), L("job_card", "Job Card", "Link", "Job Card", 120),
            L("metrc_tag", "METRC Tag", w=100)]
    return cols, data
