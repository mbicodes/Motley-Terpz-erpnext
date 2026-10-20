import calendar
import json

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

EDIT_ROLES = ("System Manager", "Sales Manager")
EMOJIS = ["🏎", "🚙", "🛻", "🚜", "🏍", "🛵", "🚐", "🦖", "🐢"]

DEFAULT_CONFIG = {"reps": []}

# Same company / item-group rows as the Sales Target dashboard. Each item group
# (and everything under it) rolls into its line; anything unmatched goes to Others.
LINES = [
    {"key": "packaged_goods", "label": "Packaged Goods", "company": "Motley Terpz", "item_groups": ["Packaged goods"]},
    {"key": "rosin", "label": "Rosin", "company": "Motley Terpz", "item_groups": ["Rosins", "Rosin"]},
    {"key": "bubble_cured", "label": "Bubble Cured", "company": "Motley Terpz", "item_groups": ["Bubble Cured"]},
    {"key": "static", "label": "Static", "company": "Motley Terpz", "item_groups": ["Static"]},
    {"key": "pre_rolls", "label": "Pre Rolls", "company": "Motley Terpz", "item_groups": ["Pre Rolls"]},
    {"key": "gummies", "label": "Gummies", "company": "Motley Terpz", "item_groups": ["Gummies"]},
    {"key": "others", "label": "Others", "company": "Motley Terpz", "item_groups": []},
    {"key": "fresh_frozen", "label": "Fresh Frozen Main", "company": "TSBC Ranch",
     "item_groups": ["Fresh Frozen Main", "Frozen"]},
]
OTHERS = "others"
LINE_COMPANY = {l["key"]: l["company"] for l in LINES}
TSBC = "TSBC Ranch"


def _line(gmap, item_group, company):
    """Line for an item sold by company. As on the Matt dashboard, TSBC Ranch only feeds the
    TSBC lines and every other company only the Motley Terpz lines; the rest is Others."""
    key = gmap.get(item_group) or OTHERS
    return key if (LINE_COMPANY[key] == TSBC) == (company == TSBC) else OTHERS


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
        {"sales_person": n, "emoji": EMOJIS[i % len(EMOJIS)], "active": 1}
        for i, n in enumerate(names)
    ]


def _can_edit():
    return bool(set(EDIT_ROLES) & set(frappe.get_roles()))


def _group_map():
    """item group -> line key, walking parent_item_group (the lft/rgt tree is not reliable).
    Groups above the lines (All Item Groups, Extracts Motley, ...) map to None: they span
    several lines, so a target on them only counts toward the total."""
    parent = dict(frappe.db.sql("select name, parent_item_group from `tabItem Group`"))
    own = {ig: l["key"] for l in LINES for ig in l["item_groups"]}
    above = set()
    for ig in own:
        node = parent.get(ig)
        while node and node not in above:
            above.add(node)
            node = parent.get(node)
    mapping = {}
    for name in parent:
        node, seen = name, set()
        while node and node not in own and node not in seen:
            seen.add(node)
            node = parent.get(node)
        mapping[name] = own.get(node, None if name in above else OTHERS)
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
    frappe.db.set_single_value("Sales Race Settings", "config", json.dumps(config))
    return True


def _targets(start, end, gmap):
    """Sales Person -> Target Detail qty/amount for start..end, in total and per line by the
    row's item group. Targets are monthly; a month only partly in the range counts pro rata."""
    out = {}
    first = start.replace(day=1)
    while first <= end:
        days = calendar.monthrange(first.year, first.month)[1]
        last = first.replace(day=days)
        share = ((min(last, end) - max(first, start)).days + 1) / days
        _month_targets(first, share, gmap, out)
        first = add_days(last, 1)
    return out


def _month_targets(first, share, gmap, out):
    """Add one month's targets (fiscal year covering it, or blank), scaled by share, into out."""
    month = first.strftime("%B")
    for t in frappe.db.sql(
        """
        select td.parent, td.item_group, td.target_qty, td.target_amount, md.percentage_allocation as pct
        from `tabTarget Detail` td
        left join `tabFiscal Year` fy on fy.name = td.fiscal_year
        left join `tabMonthly Distribution Percentage` md
            on md.parent = td.distribution_id and md.month = %(month)s
        where td.parenttype = 'Sales Person'
          and (ifnull(td.fiscal_year, '') = '' or %(d)s between fy.year_start_date and fy.year_end_date)
        """,
        {"d": first, "month": month}, as_dict=True,
    ):
        factor = (flt(t.pct) / 100 if t.pct is not None else 1) * share
        o = out.setdefault(t.parent, {"qty": 0, "amount": 0, "lines": {}})
        o["qty"] += flt(t.target_qty) * factor
        o["amount"] += flt(t.target_amount) * factor
        key = gmap.get(t.item_group, OTHERS) if t.item_group else None
        if key:
            o["lines"][key] = o["lines"].get(key, 0) + flt(t.target_amount) * factor


def _sales_rows(doctype, first, last, company):
    """Submitted item rows split per sales person by allocated %. The document's own Sales Team
    is used; a document without one falls back to its Customer's Sales Team.
    Same scope as the Matt sales target matrix: no returns, no internal/intercompany customers."""
    from cannabis_management.api.jamie import _get_excluded_customers

    date_field = "transaction_date" if doctype == "Sales Order" else "posting_date"
    items = frappe.db.sql(
        f"""
        select d.name, d.customer, d.company, d.{date_field} as dt,
               coalesce(it.item_group, i.item_group) as item_group,
               i.base_net_amount as amt, i.stock_qty as qty
        from `tab{doctype}` d
        join `tab{doctype} Item` i on i.parent = d.name
        left join `tabItem` it on it.name = i.item_code
        where d.docstatus = 1 and d.{date_field} between %(a)s and %(b)s
          and d.customer not in %(ic)s
          {"and d.is_return = 0" if doctype == "Sales Invoice" else ""}
          {"and d.company = %(company)s" if company else ""}
        """,
        {"a": first, "b": last, "company": company, "ic": _get_excluded_customers()}, as_dict=True,
    )
    if not items:
        return []
    teams = {}
    for parenttype, parents in ((doctype, {r.name for r in items}), ("Customer", {r.customer for r in items})):
        for t in frappe.get_all(
            "Sales Team", filters={"parenttype": parenttype, "parent": ["in", list(parents)]},
            fields=["parent", "sales_person", "allocated_percentage"],
        ):
            teams.setdefault((parenttype, t.parent), []).append(t)
    rows = []
    for r in items:
        for t in teams.get((doctype, r.name)) or teams.get(("Customer", r.customer)) or []:
            share = flt(t.allocated_percentage) / 100
            rows.append(frappe._dict(r, sales_person=t.sales_person, amt=flt(r.amt) * share, qty=flt(r.qty) * share))
    return rows


@frappe.whitelist()
def get_race(from_date=None, to_date=None, company=None, basis="Sales Invoice"):
    """Defaults to the current month, all companies. Returns everything the page renders."""
    today = getdate(nowdate())
    first = getdate(from_date) if from_date else today.replace(day=1)
    last = getdate(to_date) if to_date else first.replace(day=calendar.monthrange(first.year, first.month)[1])
    if last < first:
        frappe.throw("To Date cannot be before From Date")
    days = (last - first).days + 1
    day = min(max((today - first).days + 1, 0), days)
    pace = day / days

    cfg = get_config()
    config = cfg["config"]
    reps = [r for r in config["reps"] if r.get("active", 1)]
    keys = [l["key"] for l in LINES]
    gmap = _group_map()

    doctype = "Sales Order" if basis == "Sales Order" else "Sales Invoice"
    rows = _sales_rows(doctype, first, last, company)

    week_start = add_days(today, -6)
    stats = {
        r["sales_person"]: {"sold": 0, "week": 0, "qty": 0, "lines": {k: 0 for k in keys}, "docs": {}}
        for r in reps
    }
    for row in rows:
        s = stats.get(row.sales_person)
        if s is None:
            continue
        key = _line(gmap, row.item_group, row.company)
        amt = flt(row.amt)
        s["sold"] += amt
        s["qty"] += flt(row.qty)
        s["lines"][key] += amt
        if getdate(row.dt) >= week_start:
            s["week"] += amt
        s["docs"][row.name] = s["docs"].get(row.name, 0) + amt

    targets = _targets(first, last, gmap)
    out_reps = []
    for r in reps:
        s = stats[r["sales_person"]]
        t = targets.get(r["sales_person"], {})
        quotas = t.get("lines", {})
        out_reps.append({
            "sales_person": r["sales_person"], "emoji": r.get("emoji") or "🏎",
            "sold": s["sold"], "week": s["week"], "qty": s["qty"],
            "target_amount": t.get("amount", 0), "target_qty": t.get("qty", 0),
            "lines": {k: {"sold": s["lines"][k], "quota": quotas.get(k, 0)} for k in keys},
            "biggest": max(s["docs"].values(), default=0),
        })
    out_reps.sort(key=lambda x: -x["sold"])

    team = {k: sum(r["lines"][k]["sold"] for r in out_reps) for k in keys}
    leaders = {}
    for k in keys:
        best = max(out_reps, key=lambda r: r["lines"][k]["sold"], default=None)
        if best and best["lines"][k]["sold"] > 0:
            leaders[k] = {"rep": best["sales_person"], "amount": best["lines"][k]["sold"]}
    big = max(out_reps, key=lambda r: r["biggest"], default=None)
    hot = max(out_reps, key=lambda r: r["week"], default=None)

    return {
        "from_date": str(first), "to_date": str(last), "company": company or "",
        "day": day, "days": days, "pace": pace,
        "basis": doctype, "reps": out_reps,
        "lines": [dict(l, plan=sum(r["lines"][l["key"]]["quota"] for r in out_reps)) for l in LINES],
        "team": team, "leaders": leaders,
        "biggest": {"rep": big["sales_person"], "amount": big["biggest"]} if big and big["biggest"] else None,
        "hottest": {"rep": hot["sales_person"], "amount": hot["week"]} if hot and hot["week"] else None,
        "target_amount": sum(r["target_amount"] for r in out_reps),
        "target_qty": sum(r["target_qty"] for r in out_reps),
        "sold": sum(r["sold"] for r in out_reps),
        "qty": sum(r["qty"] for r in out_reps),
        "payments": _payments(first, last, company),
    }


def _payments(first, last, company):
    """Submitted Receive Payment Entries in the range. Same rule as the Matt dashboard's Total Collected:
    only money allocated against Sales Invoices counts, internal/intercompany customers excluded.
    Each invoice's share is credited to its Sales Team (else the customer's)."""
    from cannabis_management.api.jamie import _get_excluded_customers

    pes = frappe.db.sql(
        f"""
        select name, posting_date, party_type, party, party_name, mode_of_payment, reference_no,
               paid_amount, base_received_amount, unallocated_amount, company
        from `tabPayment Entry`
        where docstatus = 1 and payment_type = 'Receive' and posting_date between %(a)s and %(b)s
          and not (party_type = 'Customer' and party in %(ic)s)
          {"and company = %(company)s" if company else ""}
        order by posting_date desc, name desc
        """,
        {"a": first, "b": last, "company": company, "ic": _get_excluded_customers()}, as_dict=True,
    )
    if not pes:
        return {"total": 0, "count": 0, "by_rep": [], "rows": []}
    refs = {}
    for r in frappe.get_all(
        "Payment Entry Reference", filters={"parent": ["in", [p.name for p in pes]]},
        fields=["parent", "reference_doctype", "reference_name", "allocated_amount"], order_by="idx",
    ):
        refs.setdefault(r.parent, []).append(r)

    keys = {("Customer", p.party) for p in pes if p.party_type == "Customer"}
    keys |= {(r.reference_doctype, r.reference_name) for rs in refs.values() for r in rs}
    teams = {}
    for parenttype in {k[0] for k in keys}:
        for t in frappe.get_all(
            "Sales Team",
            filters={"parenttype": parenttype, "parent": ["in", [k[1] for k in keys if k[0] == parenttype]]},
            fields=["parent", "sales_person", "allocated_percentage"],
        ):
            teams.setdefault((parenttype, t.parent), []).append(t)

    by_rep, rows = {}, []
    for p in pes:
        cust_team = teams.get(("Customer", p.party)) if p.party_type == "Customer" else None
        parts = [(teams.get((r.reference_doctype, r.reference_name)) or cust_team, flt(r.allocated_amount))
                 for r in refs.get(p.name, []) if r.reference_doctype == "Sales Invoice"]
        reps = {}
        for team, amt in parts:
            for t in team or [{"sales_person": "Unassigned", "allocated_percentage": 100}]:
                reps[t["sales_person"]] = reps.get(t["sales_person"], 0) + amt * flt(t["allocated_percentage"]) / 100
        for sp, amt in reps.items():
            by_rep[sp] = by_rep.get(sp, 0) + amt
        rows.append({
            "name": p.name, "date": str(p.posting_date), "customer": p.party_name or p.party,
            "mode": p.mode_of_payment, "ref_no": p.reference_no, "company": p.company,
            "amount": sum(amt for _, amt in parts), "received": flt(p.base_received_amount),
            "against": [{"doctype": r.reference_doctype, "name": r.reference_name, "amount": flt(r.allocated_amount)}
                        for r in refs.get(p.name, [])],
            "unallocated": flt(p.unallocated_amount),
            "reps": sorted(sp for sp, amt in reps.items() if abs(amt) >= 0.005),
        })
    return {
        "total": sum(r["amount"] for r in rows), "count": len(rows), "rows": rows,
        "by_rep": sorted(({"sales_person": k, "amount": v} for k, v in by_rep.items() if abs(v) >= 0.005),
                         key=lambda x: -x["amount"]),
    }
