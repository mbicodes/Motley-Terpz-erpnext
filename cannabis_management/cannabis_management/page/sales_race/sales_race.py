import calendar
import json

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

EDIT_ROLES = ("System Manager", "Sales Manager")
EMOJIS = ["🏎", "🚙", "🛻", "🚜", "🏍", "🛵", "🚐", "🦖", "🐢"]

DEFAULT_CONFIG = {
    "basis": "Sales Order",
    "lines": [
        {"key": "solventless", "label": "Solventless / tolling", "plan": 500000,
         "item_groups": ["Extracts Motley", "Fresh Frozen Main"]},
        {"key": "edibles", "label": "Edibles", "plan": 250000, "item_groups": ["Jam"]},
        {"key": "packaged", "label": "Packaged goods", "plan": 250000,
         "item_groups": ["Flower Bigs", "Flower Smalls"]},
    ],
    "reps": [],
}


def _get_config():
    raw = frappe.db.get_single_value("Sales Race Settings", "config")
    config = json.loads(raw) if raw else {}
    for k, v in DEFAULT_CONFIG.items():
        config.setdefault(k, json.loads(json.dumps(v)))
    return config


def _seed_reps():
    names = frappe.get_all(
        "Sales Person", filters={"is_group": 0, "enabled": 1}, pluck="name", order_by="name"
    )
    return [
        {"sales_person": n, "emoji": EMOJIS[i % len(EMOJIS)], "active": 1,
         "quotas": {"solventless": 125000, "edibles": 62500, "packaged": 62500}}
        for i, n in enumerate(names)
    ]


def _can_edit():
    return bool(set(EDIT_ROLES) & set(frappe.get_roles()))


def _group_map(lines):
    """item group (incl. descendants) -> line key"""
    mapping = {}
    for line in lines:
        for ig in line.get("item_groups") or []:
            bounds = frappe.db.get_value("Item Group", ig, ["lft", "rgt"])
            if not bounds:
                continue
            for name in frappe.db.sql_list(
                "select name from `tabItem Group` where lft >= %s and rgt <= %s", bounds
            ):
                mapping.setdefault(name, line["key"])
    return mapping


@frappe.whitelist()
def get_config():
    config = _get_config()
    if not config["reps"]:
        config["reps"] = _seed_reps()
    return {"config": config, "can_edit": _can_edit()}


@frappe.whitelist()
def save_config(config):
    if not _can_edit():
        frappe.throw("Not permitted", frappe.PermissionError)
    config = json.loads(config) if isinstance(config, str) else config
    if config.get("basis") not in ("Sales Order", "Sales Invoice"):
        config["basis"] = "Sales Order"
    frappe.db.set_single_value("Sales Race Settings", "config", json.dumps(config))
    return True


@frappe.whitelist()
def get_race(month=None):
    """month: 'YYYY-MM' (default current). Returns everything the page renders."""
    today = getdate(nowdate())
    first = getdate(f"{month}-01") if month else today.replace(day=1)
    days_in_month = calendar.monthrange(first.year, first.month)[1]
    last = first.replace(day=days_in_month)
    if first.year == today.year and first.month == today.month:
        day = today.day
    else:
        day = days_in_month if first < today else 0
    pace = day / days_in_month

    cfg = get_config()
    config = cfg["config"]
    lines = config["lines"]
    reps = [r for r in config["reps"] if r.get("active", 1)]
    keys = [l["key"] for l in lines]
    gmap = _group_map(lines)

    doctype = "Sales Invoice" if config["basis"] == "Sales Invoice" else "Sales Order"
    date_field = "posting_date" if doctype == "Sales Invoice" else "transaction_date"
    rows = frappe.db.sql(
        f"""
        select d.name, d.customer_name, d.{date_field} as dt, st.sales_person,
               i.item_group, i.net_amount * st.allocated_percentage / 100 as amt
        from `tab{doctype}` d
        join `tab{doctype} Item` i on i.parent = d.name
        join `tabSales Team` st on st.parent = d.name and st.parenttype = %(dt)s
        where d.docstatus = 1 and d.{date_field} between %(a)s and %(b)s
        """,
        {"dt": doctype, "a": first, "b": last}, as_dict=True,
    )

    week_start = add_days(today, -6)
    stats = {
        r["sales_person"]: {"total": 0, "week": 0, "lines": {k: 0 for k in keys}, "docs": {}}
        for r in reps
    }
    recent, unmapped = {}, 0
    for row in rows:
        s = stats.get(row.sales_person)
        if s is None:
            continue
        key = gmap.get(row.item_group)
        amt = flt(row.amt)
        if not key:
            unmapped += amt
            continue
        s["total"] += amt
        s["lines"][key] += amt
        if getdate(row.dt) >= week_start:
            s["week"] += amt
        s["docs"][row.name] = s["docs"].get(row.name, 0) + amt
        rec = recent.setdefault((row.name, row.sales_person), {
            "doc": row.name, "rep": row.sales_person, "customer": row.customer_name,
            "date": str(row.dt), "line": key, "amount": 0})
        rec["amount"] += amt

    out_reps = []
    for r in reps:
        s = stats[r["sales_person"]]
        quotas = {k: flt((r.get("quotas") or {}).get(k)) for k in keys}
        out_reps.append({
            "sales_person": r["sales_person"], "emoji": r.get("emoji") or "🏎",
            "total": s["total"], "week": s["week"], "quota": sum(quotas.values()),
            "lines": {k: {"sold": s["lines"][k], "quota": quotas[k]} for k in keys},
            "biggest": max(s["docs"].values(), default=0),
        })
    out_reps.sort(key=lambda x: -x["total"])

    team = {k: sum(r["lines"][k]["sold"] for r in out_reps) for k in keys}
    leaders = {}
    for k in keys:
        best = max(out_reps, key=lambda r: r["lines"][k]["sold"], default=None)
        if best and best["lines"][k]["sold"] > 0:
            leaders[k] = {"rep": best["sales_person"], "amount": best["lines"][k]["sold"]}
    big = max(out_reps, key=lambda r: r["biggest"], default=None)
    hot = max(out_reps, key=lambda r: r["week"], default=None)

    return {
        "month": first.strftime("%Y-%m"), "month_label": first.strftime("%B %Y"),
        "day": day, "days_in_month": days_in_month, "pace": pace,
        "basis": doctype, "can_edit": cfg["can_edit"], "lines": lines, "reps": out_reps,
        "team": team, "leaders": leaders,
        "plan_total": sum(flt(l.get("plan")) for l in lines),
        "biggest": {"rep": big["sales_person"], "amount": big["biggest"]} if big and big["biggest"] else None,
        "hottest": {"rep": hot["sales_person"], "amount": hot["week"]} if hot and hot["week"] else None,
        "recent": sorted(recent.values(), key=lambda x: (x["date"], x["doc"]), reverse=True)[:12],
        "unmapped": unmapped,
    }
