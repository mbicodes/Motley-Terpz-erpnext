import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    f = filters or {}
    cond, val = ["i.parenttype = 'Wash Production Plan'", "p.status != 'Cancelled'"], {}
    for key, expr in (("company", "p.company = %(company)s"), ("from_date", "i.planned_date >= %(from_date)s"),
                      ("to_date", "i.planned_date <= %(to_date)s"), ("freezer", "i.source_freezer = %(freezer)s"),
                      ("project", "i.project = %(project)s"), ("plan", "p.name = %(plan)s"),
                      ("item", "i.fresh_frozen_item = %(item)s")):
        if f.get(key):
            cond.append(expr); val[key] = f[key]
    data = frappe.db.sql(
        f"""select i.planned_date, p.name plan, i.item_name strain, i.source_freezer freezer, i.project,
        i.planned_qty_lbs, i.expected_hash_g, i.actual_hash_g, i.expected_hash_yield exp_hash_pct,
        i.actual_hash_yield act_hash_pct, i.expected_rosin_g, i.actual_rosin_g,
        i.expected_rosin_yield exp_rosin_pct, i.actual_rosin_yield act_rosin_pct,
        i.material_request mr, i.hash_work_order hash_wo, i.rosin_work_order rosin_wo, i.row_status
        from `tabWash Production Plan Item` i join `tabWash Production Plan` p on p.name = i.parent
        where {' and '.join(cond)} order by i.planned_date, p.name, i.idx""", val, as_dict=1)
    L = lambda n, l, t="Data", o=None, w=110: {"fieldname": n, "label": _(l), "fieldtype": t, "options": o, "width": w}
    cols = [L("planned_date", "Planned Date", "Date"), L("plan", "Plan", "Link", "Wash Production Plan"), L("strain", "Strain", w=200),
            L("freezer", "Freezer", "Link", "Warehouse"), L("project", "Project", "Link", "Project"),
            L("planned_qty_lbs", "Planned (lbs)", "Float"), L("expected_hash_g", "Exp. Hash (g)", "Float"),
            L("actual_hash_g", "Actual Hash (g)", "Float"), L("exp_hash_pct", "Exp. Hash %", "Percent"),
            L("act_hash_pct", "Actual Hash %", "Percent"), L("expected_rosin_g", "Exp. Rosin (g)", "Float"),
            L("actual_rosin_g", "Actual Rosin (g)", "Float"), L("exp_rosin_pct", "Exp. Rosin %", "Percent"),
            L("act_rosin_pct", "Actual Rosin %", "Percent"), L("mr", "Material Request", "Link", "Material Request", 150),
            L("hash_wo", "Hash WO", "Link", "Work Order", 140), L("rosin_wo", "Rosin WO", "Link", "Work Order", 140), L("row_status", "Status")]
    return cols, data
