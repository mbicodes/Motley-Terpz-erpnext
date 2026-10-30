import frappe
from frappe.utils import flt

from cannabis_management.cannabis_management.page.manufacturing_runs.manufacturing_runs import (
    JC_FROM,
    _build_run_row,
)

MTM_COMPANY = "Master Touch Manufacturing"
FRESH_FROZEN_GROUPS = ("Fresh Frozen", "Fresh Frozen - BHO", "Fresh Frozen - SHO")

RESERVED_SUBQUERY = """
    SELECT item_code, warehouse, SUM(reserved_qty - delivered_qty) AS reserved_qty
    FROM `tabStock Reservation Entry`
    WHERE docstatus = 1
      AND status IN ('Reserved', 'Partially Reserved', 'Partially Delivered')
    GROUP BY item_code, warehouse
"""

VOUCHER_PROJECT_UNION = """
    SELECT 'Stock Entry' AS voucher_type, name AS voucher_no, project FROM `tabStock Entry`
    UNION ALL
    SELECT 'Purchase Receipt', name, project FROM `tabPurchase Receipt`
    UNION ALL
    SELECT 'Purchase Invoice', name, project FROM `tabPurchase Invoice`
    UNION ALL
    SELECT 'Delivery Note', name, project FROM `tabDelivery Note`
    UNION ALL
    SELECT 'Sales Invoice', name, project FROM `tabSales Invoice`
"""


@frappe.whitelist(allow_guest=True)
def get_stock_by_item_group(item_group, project=None, _=None):
    company_condition = ""
    values = [item_group]

    if item_group not in FRESH_FROZEN_GROUPS:
        company_condition = "AND w.company = %s"
        values.append(MTM_COMPANY)

    projects = get_projects_with_stock(item_group, company_condition, values)

    if project:
        items = get_project_stock(item_group, project, company_condition, values)
    else:
        items = get_bin_stock(company_condition, values)

    item_codes = list(set(item.item_code for item in items))

    yield_map = get_yield_data_for_items(item_codes)

    for item in items:
        code = item.item_code
        data = yield_map.get(code) or {}
        item["yield_to_hash"] = data.get("yield_to_hash", "")
        item["hash_to_rosin"] = data.get("hash_to_rosin", "")
        item["yield_to_hash_parts"] = data.get("yield_to_hash_parts", [])
        item["hash_to_rosin_parts"] = data.get("hash_to_rosin_parts", [])

    grade_map = get_quality_grades_for_items(item_codes) if item_group in FRESH_FROZEN_GROUPS else {}
    for item in items:
        item["quality_grade"] = grade_map.get(item.item_code)

    total_qty = sum(item.actual_qty or 0 for item in items)
    unique_items = len(set(item.item_code for item in items))
    low_stock = len([i for i in items if (i.actual_qty or 0) - (i.reserved_qty or 0) <= 0])

    return {
        "items": items,
        "projects": projects,
        "summary": {
            "total_items": unique_items,
            "total_qty": total_qty,
            "low_stock_items": low_stock
        }
    }


def get_project_balances(item_group, company_condition, values, project=None):
    project_condition = "AND eff_project = %s" if project else "AND eff_project != ''"
    args = (item_group,) + tuple(values[1:]) + ((project,) if project else ())
    return frappe.db.sql("""
        SELECT
            eff_project AS project,
            item_code,
            item_name,
            item_group,
            propagation,
            breeder,
            warehouse,
            LEAST(SUM(actual_qty), actual_qty_bin) AS actual_qty,
            ROUND(
                MAX(reserved_qty)
                * LEAST(SUM(actual_qty), actual_qty_bin)
                / NULLIF(actual_qty_bin, 0)
            , 6) AS reserved_qty
        FROM (
            SELECT
                sle.actual_qty,
                sle.item_code,
                i.item_name,
                i.item_group,
                i.custom_propagation AS propagation,
                i.custom_breeder AS breeder,
                sle.warehouse,
                b.actual_qty AS actual_qty_bin,
                COALESCE(sre.reserved_qty, 0) AS reserved_qty,
                IFNULL(NULLIF(sle.project, ''), IFNULL(vp.project, '')) AS eff_project
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabItem` i ON i.name = sle.item_code
            INNER JOIN `tabWarehouse` w ON w.name = sle.warehouse
            INNER JOIN `tabBin` b ON b.item_code = sle.item_code AND b.warehouse = sle.warehouse
            LEFT JOIN ({reserved_subquery}) sre
                ON sre.item_code = b.item_code AND sre.warehouse = b.warehouse
            LEFT JOIN ({voucher_project_union}) vp
                ON vp.voucher_type = sle.voucher_type AND vp.voucher_no = sle.voucher_no
            WHERE i.item_group = %s
                AND i.disabled = 0
                AND i.custom_show_in_dashboard = 1
                AND sle.is_cancelled = 0
                AND b.actual_qty > 0
                AND sle.warehouse NOT LIKE 'Virtual%%'
                {company_condition}
        ) ledger
        WHERE 1 = 1 {project_condition}
        GROUP BY eff_project, item_code, warehouse, actual_qty_bin
        HAVING ROUND(SUM(actual_qty), 6) > 0
        ORDER BY item_name
    """.format(project_condition=project_condition, company_condition=company_condition,
               reserved_subquery=RESERVED_SUBQUERY,
               voucher_project_union=VOUCHER_PROJECT_UNION), args, as_dict=True)


def get_project_stock(item_group, project, company_condition, values):
    return get_project_balances(item_group, company_condition, values, project)


def get_projects_with_stock(item_group, company_condition, values):
    projects = {}
    for row in get_project_balances(item_group, company_condition, values):
        p = projects.setdefault(row.project, {"name": row.project, "warehouses": []})
        if row.warehouse not in p["warehouses"]:
            p["warehouses"].append(row.warehouse)
    if not projects:
        return []
    labels = dict(frappe.get_all(
        "Project", filters={"name": ["in", list(projects)]}, fields=["name", "project_name"], as_list=True
    ))
    for name, p in projects.items():
        p["project_name"] = (labels.get(name) or "").strip() or name
    return sorted(projects.values(), key=lambda p: p["project_name"].lower())


def get_bin_stock(company_condition, values):
    return frappe.db.sql("""
        SELECT
            b.item_code,
            i.item_name,
            i.item_group,
            i.custom_propagation AS propagation,
            i.custom_breeder AS breeder,
            b.warehouse,
            b.actual_qty,
            COALESCE(sre.reserved_qty, 0) AS reserved_qty
        FROM `tabBin` b
        INNER JOIN `tabItem` i ON i.name = b.item_code
        INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
        LEFT JOIN ({reserved_subquery}) sre
            ON sre.item_code = b.item_code AND sre.warehouse = b.warehouse
        WHERE i.item_group = %s
            AND i.disabled = 0
            AND i.custom_show_in_dashboard = 1
            AND b.actual_qty != 0
            AND b.warehouse NOT LIKE 'Virtual%%'
            {company_condition}
        ORDER BY i.item_name
    """.format(company_condition=company_condition, reserved_subquery=RESERVED_SUBQUERY),
        tuple(values), as_dict=True)


def get_yield_data_for_items(item_codes):
    if not item_codes:
        return {}

    placeholders = ", ".join(["%s"] * len(item_codes))

    records = frappe.db.sql("""
        SELECT
            ltd.strain_name AS item_code,
            ltd.yield_to_hash,
            ltd.actual_rosin_yield
        FROM `tabLab Tolling Data` ltd
        INNER JOIN `tabRosin Recording` rr ON rr.name = ltd.parent
        WHERE ltd.strain_name IN ({placeholders})
            AND rr.docstatus < 2
        ORDER BY ltd.strain_name, rr.creation
    """.format(placeholders=placeholders), tuple(item_codes), as_dict=True)

    yield_map = {}
    for row in records:
        entry = _yield_entry(yield_map, row.item_code)
        _add_yield(entry["yield_to_hash"], row.get("yield_to_hash"))
        _add_yield(entry["hash_to_rosin"], row.get("actual_rosin_yield"))

    add_run_yields(item_codes, yield_map)
    add_customer_yields(item_codes, yield_map)

    result = {}
    for code, entry in yield_map.items():
        result[code] = {
            "yield_to_hash": ", ".join(dict.fromkeys(p["value"] for p in entry["yield_to_hash"])),
            "hash_to_rosin": ", ".join(dict.fromkeys(p["value"] for p in entry["hash_to_rosin"])),
            "yield_to_hash_parts": entry["yield_to_hash"],
            "hash_to_rosin_parts": entry["hash_to_rosin"],
        }

    return result



QUALITY_TIERS = {"Tier 1": "t1", "Tier 1 Plus": "t1", "Tier 2": "t2", "Tier 3": "t3"}
QUALITY_GRADE_CACHE_KEY = "mtm_inventory_dashboard_quality_grades"

CONVERSION_RM_SLOTS = 7
CONVERSION_FG_SLOTS = 3


def get_quality_grades_for_items(item_codes):
    grades = frappe.cache().get_value(QUALITY_GRADE_CACHE_KEY)
    if grades is None:
        grades = build_quality_grades()
        frappe.cache().set_value(QUALITY_GRADE_CACHE_KEY, grades, expires_in_sec=600)
    return {code: grades[code] for code in item_codes if code in grades}


def build_quality_grades():
    from collections import defaultdict

    from cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry import grams_per_unit

    rows = frappe.db.sql("""
        SELECT sed.parent, sed.item_code, sed.s_warehouse, sed.t_warehouse, sed.transfer_qty,
               i.stock_uom, i.item_group
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        INNER JOIN `tabItem` i ON i.name = sed.item_code
        WHERE se.docstatus = 1 AND se.purpose IN ('Manufacture', 'Repack')
    """, as_dict=True)

    factors = {}
    groups = {}
    entries = defaultdict(lambda: {"in": defaultdict(float), "out": defaultdict(float)})

    def to_grams(qty, uom):
        if uom not in factors:
            factors[uom] = grams_per_unit(uom) or 1.0
        return flt(qty) * factors[uom]

    for r in rows:
        grams = to_grams(r.transfer_qty, r.stock_uom)
        groups[r.item_code] = r.item_group or ""
        side = "in" if r.s_warehouse else "out" if r.t_warehouse else None
        if side and grams:
            entries[r.parent][side][r.item_code] += grams

    add_unposted_conversion_rows(entries, groups, to_grams)

    produced_by = defaultdict(list)
    for name, e in entries.items():
        for code, grams in e["out"].items():
            if code not in e["in"]:
                produced_by[code].append((grams, e["in"]))

    def is_fresh_frozen(code):
        return groups.get(code, "").startswith("Fresh Frozen")

    memo = {}
    stack = set()

    def input_origins(inputs, exclude=None):
        total = sum(g for c, g in inputs.items() if c != exclude)
        mix = defaultdict(float)
        if not total:
            return mix
        for code, grams in inputs.items():
            if code == exclude:
                continue
            for ff, share in origins(code).items():
                mix[ff] += grams / total * share
        return mix

    def origins(code):
        if is_fresh_frozen(code):
            return {code: 1.0}
        if code in memo:
            return memo[code]
        if code in stack:
            return {}
        stack.add(code)
        acc = defaultdict(float)
        made = 0.0
        for grams, inputs in produced_by.get(code, []):
            made += grams
            for ff, share in input_origins(inputs, code).items():
                acc[ff] += grams * share
        stack.discard(code)
        memo[code] = {ff: v / made for ff, v in acc.items()} if made else {}
        return memo[code]

    tiers_by_ff = defaultdict(lambda: {"t1": 0.0, "t2": 0.0, "t3": 0.0})
    for e in entries.values():
        if any(groups.get(c) in QUALITY_TIERS for c in e["in"]):
            continue
        tier_out = [(QUALITY_TIERS[groups[c]], g) for c, g in e["out"].items() if groups.get(c) in QUALITY_TIERS]
        if not tier_out:
            continue
        for ff, share in input_origins(e["in"]).items():
            for tier, grams in tier_out:
                tiers_by_ff[ff][tier] += grams * share

    result = {}
    for ff, t in tiers_by_ff.items():
        total = t["t1"] + t["t2"] + t["t3"]
        if total:
            result[ff] = {k + "_pct": round(t[k] / total * 100, 1) for k in ("t1", "t2", "t3")}
    return result


def add_unposted_conversion_rows(entries, groups, to_grams):
    from collections import defaultdict

    se_states = defaultdict(set)
    for ce, docstatus in frappe.db.sql("""
        SELECT custom_conversion_entry_reference, docstatus FROM `tabStock Entry`
        WHERE IFNULL(custom_conversion_entry_reference, '') != ''
    """):
        se_states[ce].add(docstatus)

    rows = frappe.db.sql("""
        SELECT ci.*
        FROM `tabConversion Entry Item` ci
        INNER JOIN `tabConversion Entry` ce ON ce.name = ci.parent
        WHERE ce.docstatus = 1 AND ci.parenttype = 'Conversion Entry'
        ORDER BY ci.parent, ci.idx
    """, as_dict=True)
    codes = {r.get("{}_{}".format(f, i)) for r in rows
             for f, n in (("raw_material", CONVERSION_RM_SLOTS), ("finished_good", CONVERSION_FG_SLOTS))
             for i in range(1, n + 1)} - {None, ""}
    meta = {d.name: d for d in frappe.get_all(
        "Item", filters={"name": ["in", list(codes)]}, fields=["name", "item_group", "stock_uom"]
    )} if codes else {}

    by_entry = defaultdict(list)
    for r in rows:
        entry = {"in": defaultdict(float), "out": defaultdict(float)}
        for side, field, qty_field, slots in (("in", "raw_material", "qty_rm", CONVERSION_RM_SLOTS),
                                              ("out", "finished_good", "qty_fg", CONVERSION_FG_SLOTS)):
            for i in range(1, slots + 1):
                code = r.get("{}_{}".format(field, i))
                item = meta.get(code)
                qty = flt(r.get("{}_{}".format(qty_field, i)))
                if item and qty > 0:
                    groups[code] = item.item_group or ""
                    entry[side][code] += to_grams(qty, item.stock_uom)
        if entry["in"] and entry["out"]:
            by_entry[r.parent].append((r.name, entry))

    def fingerprint(entry):
        return (tuple(sorted(entry["in"].items())), tuple(sorted(entry["out"].items())))

    posted_rows = {fingerprint(e) for ce, ce_rows in by_entry.items() if 1 in se_states[ce] for _, e in ce_rows}

    for ce, ce_rows in by_entry.items():
        states = se_states[ce]
        if 1 in states or 2 in states:
            continue
        if all(fingerprint(e) in posted_rows for _, e in ce_rows):
            continue
        for name, entry in ce_rows:
            entries["CE:" + name] = entry

def _yield_entry(yield_map, item_code):
    return yield_map.setdefault(item_code, {"yield_to_hash": [], "hash_to_rosin": []})


def _add_yield(parts, value, customer=None, customer_name=None, colour=None):
    if value is None or value == "" or value == 0:
        return
    try:
        formatted = "{:.2f}%".format(float(value))
    except (ValueError, TypeError):
        formatted = str(value)
    if formatted == "0.00%":
        return
    part = {"value": formatted, "source": "customer" if customer else "lab"}
    if customer:
        part["customer"] = customer
        part["customer_name"] = customer_name or customer
        part.update(colour or {})
    if part not in parts:
        parts.append(part)


def add_run_yields(item_codes, yield_map):
    placeholders = ", ".join(["%s"] * len(item_codes))

    runs = frappe.db.sql("""
        SELECT wo.material_request AS run_id,
               MIN(mri.item_code) AS item_code,
               MIN(COALESCE(jc.actual_start_date, jc.creation)) AS first_start
        {jc_from}
        INNER JOIN `tabMaterial Request Item` mri ON mri.parent = wo.material_request
        WHERE jc.status != 'Cancelled' AND jc.docstatus < 2
            AND mri.item_code IN ({placeholders})
        GROUP BY wo.material_request
        ORDER BY first_start
    """.format(jc_from=JC_FROM, placeholders=placeholders), tuple(item_codes), as_dict=True)

    for run in runs:
        row = _build_run_row(run.run_id)
        entry = _yield_entry(yield_map, run.item_code)
        _add_yield(entry["yield_to_hash"], row.get("hash_yield"))
        _add_yield(entry["hash_to_rosin"], row.get("hash_to_rosin_yield"))

CUSTOMER_YIELD_COLOURS = [
    {"color": "Blue", "fg": "#ffffff", "bg": "#2563eb", "swatch": "#2563eb"},
    {"color": "Green", "fg": "#ffffff", "bg": "#16a34a", "swatch": "#16a34a"},
    {"color": "Orange", "fg": "#ffffff", "bg": "#ea580c", "swatch": "#ea580c"},
    {"color": "Black", "fg": "#ffffff", "bg": "#111827", "swatch": "#111827"},
    {"color": "Yellow", "fg": "#1f2937", "bg": "#facc15", "swatch": "#facc15"},
    {"color": "Sky Blue", "fg": "#0c4a6e", "bg": "#7dd3fc", "swatch": "#7dd3fc"},
    {"color": "Red", "fg": "#ffffff", "bg": "#dc2626", "swatch": "#dc2626"},
    {"color": "Brown", "fg": "#ffffff", "bg": "#78350f", "swatch": "#78350f"},
    {"color": "Lime", "fg": "#1a2e05", "bg": "#a3e635", "swatch": "#a3e635"},
    {"color": "Gray", "fg": "#ffffff", "bg": "#6b7280", "swatch": "#6b7280"},
]


def customer_yield_colours():
    customers = frappe.db.sql_list("""
        SELECT cyf.customer FROM `tabCustomer Yield Feedback` cyf
        INNER JOIN `tabItem Yield` iy ON iy.parent = cyf.name
            AND iy.parenttype = 'Customer Yield Feedback'
        WHERE cyf.docstatus = 1 AND IFNULL(iy.yield_source, '') != 'Our Lab'
        GROUP BY cyf.customer
        ORDER BY MIN(cyf.creation), cyf.customer
    """)
    return {c: CUSTOMER_YIELD_COLOURS[i % len(CUSTOMER_YIELD_COLOURS)]
            for i, c in enumerate(customers)}


def add_customer_yields(item_codes, yield_map):
    placeholders = ", ".join(["%s"] * len(item_codes))

    rows = frappe.db.sql("""
        SELECT iy.item_code, iy.yield_percentage, iy.hash_to_rosin, iy.yield_source,
               cyf.customer, COALESCE(NULLIF(cyf.customer_name, ''), cyf.customer) AS customer_name
        FROM `tabItem Yield` iy
        INNER JOIN `tabCustomer Yield Feedback` cyf ON cyf.name = iy.parent
        WHERE iy.parenttype = 'Customer Yield Feedback'
            AND cyf.docstatus = 1
            AND iy.item_code IN ({placeholders})
        ORDER BY cyf.date, cyf.creation, iy.idx
    """.format(placeholders=placeholders), tuple(item_codes), as_dict=True)
    if not rows:
        return

    colours = customer_yield_colours()
    for row in rows:
        entry = _yield_entry(yield_map, row.item_code)
        colour = colours.get(row.customer) or CUSTOMER_YIELD_COLOURS[-1]
        for parts, value in ((entry["yield_to_hash"], row.yield_percentage),
                             (entry["hash_to_rosin"], row.hash_to_rosin)):
            if row.yield_source == "Our Lab":
                _add_yield(parts, value)
            else:
                _add_yield(parts, value, row.customer, row.customer_name, colour)


@frappe.whitelist(allow_guest=True)
def get_batch_warehouse_summary(item_group):
    data = frappe.db.sql("""
        SELECT
            warehouse,
            COUNT(DISTINCT eff_project) AS batch_count
        FROM (
            SELECT
                sle.warehouse,
                IFNULL(NULLIF(sle.project, ''), IFNULL(vp.project, '')) AS eff_project,
                SUM(sle.actual_qty) AS qty
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabItem` i ON i.name = sle.item_code
            LEFT JOIN ({voucher_project_union}) vp
                ON vp.voucher_type = sle.voucher_type AND vp.voucher_no = sle.voucher_no
            WHERE i.item_group = %s
              AND i.disabled = 0
              AND i.custom_show_in_dashboard = 1
              AND sle.is_cancelled = 0
            GROUP BY sle.warehouse, eff_project
            HAVING SUM(sle.actual_qty) > 0 AND eff_project != ''
        ) sub
        GROUP BY warehouse
        ORDER BY batch_count DESC
    """.format(voucher_project_union=VOUCHER_PROJECT_UNION), (item_group,), as_dict=True)
    return data


RESERVE_EXCLUDED_COMPANY = "Motley Terpz"


@frappe.whitelist()
def get_reserved_sales_orders():
    rows = frappe.db.sql("""
        SELECT sre.name, sre.voucher_no, sre.item_code, i.item_name, sre.warehouse,
               sre.reserved_qty, sre.delivered_qty, sre.reserved_qty - sre.delivered_qty AS open_qty,
               sre.stock_uom, sre.status, sre.project
        FROM `tabStock Reservation Entry` sre
        LEFT JOIN `tabItem` i ON i.name = sre.item_code
        WHERE sre.docstatus = 1
          AND sre.voucher_type = 'Sales Order'
          AND sre.company != %s
          AND sre.status IN ('Reserved', 'Partially Reserved', 'Partially Delivered')
        ORDER BY sre.voucher_no, sre.item_code
    """, (RESERVE_EXCLUDED_COMPANY,), as_dict=True)
    if not rows:
        return []

    orders = {
        so.name: dict(so, items=[])
        for so in frappe.get_list(
            "Sales Order",
            filters={"name": ["in", list({r.voucher_no for r in rows})]},
            fields=["name", "customer", "customer_name", "company", "transaction_date",
                    "delivery_date", "status"],
            limit_page_length=0,
        )
    }
    for r in rows:
        if r.voucher_no in orders:
            orders[r.voucher_no]["items"].append(r)
    return sorted(orders.values(), key=lambda o: (o["delivery_date"] or o["transaction_date"], o["name"]))
