import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.cannabis_management.page.manufacturing_runs.manufacturing_runs import (
    JC_FROM,
    _build_run_row,
)

MTM_COMPANY = "Master Touch Manufacturing"
from cannabis_management.ff_groups import FF_GROUPS as FRESH_FROZEN_GROUPS  # noqa: E402

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
        item["yield_to_hash_avg"] = data.get("yield_to_hash_avg")
        item["bho_yield"] = data.get("bho_yield", "")
        item["bho_yield_parts"] = data.get("bho_yield_parts", [])
        item["bho_yield_avg"] = data.get("bho_yield_avg")
        item["hash_to_rosin_parts"] = data.get("hash_to_rosin_parts", [])

    grade_map = get_quality_grades_for_items(item_codes) if item_group in FRESH_FROZEN_GROUPS else {}
    notes = get_item_notes(item_codes)
    for item in items:
        item["quality_grade"] = grade_map.get(item.item_code)
        item["note"] = notes.get(item.item_code, "")

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
    _collect_yields(item_codes, yield_map, records)

    result = {}
    for code, entry in yield_map.items():
        result[code] = {
            "yield_to_hash": ", ".join(dict.fromkeys(p["value"] for p in entry["yield_to_hash"])),
            "hash_to_rosin": ", ".join(dict.fromkeys(p["value"] for p in entry["hash_to_rosin"])),
            "yield_to_hash_parts": entry["yield_to_hash"],
            "hash_to_rosin_parts": entry["hash_to_rosin"],
            "yield_to_hash_avg": yield_to_hash_avg(yth_values_from_parts(entry["yield_to_hash"])),
            "bho_yield": ", ".join(dict.fromkeys(p["value"] for p in entry["bho_yield"])),
            "bho_yield_parts": entry["bho_yield"],
            "bho_yield_avg": yield_to_hash_avg(yth_values_from_parts(entry["bho_yield"])),
            "yield_to_hash_count": len(yth_values_from_parts(entry["yield_to_hash"])),
        }

    return result


def _collect_yields(item_codes, yield_map, records=None):
    if records is None:
        placeholders = ", ".join(["%s"] * len(item_codes))
        records = frappe.db.sql("""
            SELECT ltd.strain_name AS item_code, ltd.yield_to_hash, ltd.actual_rosin_yield
            FROM `tabLab Tolling Data` ltd
            INNER JOIN `tabRosin Recording` rr ON rr.name = ltd.parent
            WHERE ltd.strain_name IN ({placeholders}) AND rr.docstatus < 2
            ORDER BY ltd.strain_name, rr.creation
        """.format(placeholders=placeholders), tuple(item_codes), as_dict=True)
    for row in records:
        entry = _yield_entry(yield_map, row.item_code)
        _add_yield(entry["yield_to_hash"], row.get("yield_to_hash"))
        _add_yield(entry["hash_to_rosin"], row.get("actual_rosin_yield"))
    add_run_yields(item_codes, yield_map)
    add_repack_wash_yields(item_codes, yield_map)
    add_customer_yields(item_codes, yield_map)



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
    return yield_map.setdefault(item_code, {"yield_to_hash": [], "hash_to_rosin": [], "bho_yield": []})


# Below this a Yield To Hash value is a data-entry slip (e.g. 0.03 typed for 3%), not a real wash.
MIN_VALID_YIELD_TO_HASH = 0.5


def yth_values_from_parts(parts):
    """The Yield To Hash values exactly as the dashboard shows them (one per badge), minus slips < 0.5%."""
    out = []
    for p in parts or []:
        v = _yield_number(p.get("value"))
        if v is not None and v >= MIN_VALID_YIELD_TO_HASH:
            out.append(v)
    return out


def _yield_number(value):
    """2.76, "2.76", "2.76%" or " 2.76 % " -> 2.76 (Lab Tolling Data stores Yield To Hash as text)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    import re
    m = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return round(float(m.group()), 2) if m else None


def yield_to_hash_values(item_codes):
    """{item: [Yield To Hash %, ...]} from the same sources the dashboard shows: Lab Tolling Data,
    manufacturing run yields and submitted Customer Yield Feedback. The FF auto-classification
    (doc_hooks/ff_wash_classify.py) uses the average of these values."""
    item_codes = list(item_codes or [])
    if not item_codes:
        return {}
    yield_map = {}
    _collect_yields(item_codes, yield_map)
    out = {}
    for code, entry in yield_map.items():
        vals = yth_values_from_parts(entry["yield_to_hash"])
        if vals:
            out[code] = vals
    return out


def yield_to_hash_avg(values):
    """Average to 2 decimals, half-up like a calculator (3.315 -> 3.32), from the 2-decimal values."""
    if not values:
        return None
    from decimal import ROUND_HALF_UP, Decimal
    total = sum(Decimal(str(v)) for v in values)
    return float((total / len(values)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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

def add_repack_wash_yields(item_codes, yield_map):
    """Washes posted as Repack Stock Entries (Sept 2026, before Work Orders) have no manufacturing run,
    so their Yield To Hash is added here. Manufacture washes are already in add_run_yields."""
    from cannabis_management.doc_hooks.ff_wash_classify import wash_runs
    wanted = set(item_codes)
    for code, runs in wash_runs(item_codes).items():
        if code not in wanted:  # other strains washed in the same entry
            continue
        for r in runs:
            if r.purpose == "Repack":
                entry = _yield_entry(yield_map, code)
                _add_yield(entry["yield_to_hash"], r["yield"])


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
        SELECT iy.item_code, iy.yield_percentage, iy.hash_to_rosin, iy.yield_source, {bho_col},
               cyf.customer, COALESCE(NULLIF(cyf.customer_name, ''), cyf.customer) AS customer_name
        FROM `tabItem Yield` iy
        INNER JOIN `tabCustomer Yield Feedback` cyf ON cyf.name = iy.parent
        WHERE iy.parenttype = 'Customer Yield Feedback'
            AND cyf.docstatus = 1
            AND iy.item_code IN ({placeholders})
        ORDER BY cyf.date, cyf.creation, iy.idx
    """.format(placeholders=placeholders,
               bho_col="iy.bho_yield" if frappe.db.has_column("Item Yield", "bho_yield") else "NULL AS bho_yield"),
        tuple(item_codes), as_dict=True)
    if not rows:
        return

    colours = customer_yield_colours()
    for row in rows:
        entry = _yield_entry(yield_map, row.item_code)
        colour = colours.get(row.customer) or CUSTOMER_YIELD_COLOURS[-1]
        for parts, value in ((entry["yield_to_hash"], row.yield_percentage),
                             (entry["hash_to_rosin"], row.hash_to_rosin),
                             (entry["bho_yield"], row.bho_yield)):
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


# ---------------------------------------------------------------- Add Yield (Fresh Frozen view)
YIELD_DOCTYPE = "Customer Yield Feedback"


@frappe.whitelist(allow_guest=True)
def can_add_yield():
    """The dashboard shows Add Yield only to logged-in users who may create and submit Customer Yield Feedback."""
    if frappe.session.user == "Guest":
        return False
    return bool(frappe.has_permission(YIELD_DOCTYPE, "create") and frappe.has_permission(YIELD_DOCTYPE, "submit"))


@frappe.whitelist()
def add_yield(item_code, source="Our Lab", customer=None, date=None, quantity=None, hash_qty=None,
              yield_percentage=None, rosin_qty=None, hash_to_rosin=None, bho_qty=None, bho_yield=None,
              remarks=None, run_to="SHO"):
    """Save one yield line from the Inventory Dashboard as a submitted Customer Yield Feedback, so it shows
    in Run to SHO / Run to BHO, the averages and the SHO / BHO / TBD classification straight away.
    Grams given with Qty (LBS) are turned into % by the Customer Yield Feedback controller."""
    if not can_add_yield():
        frappe.throw(_("You are not permitted to add yields."), frappe.PermissionError)
    from cannabis_management.doc_hooks.ff_wash_classify import ff_groups
    group = frappe.db.get_value("Item", item_code, "item_group")
    if not group:
        frappe.throw(_("Item {0} not found").format(item_code))
    if group not in ff_groups():
        frappe.throw(_("{0} is not a Fresh Frozen item").format(item_code))
    if source not in ("Our Lab", "Customer"):
        frappe.throw(_("Source must be Our Lab or Customer"))
    if source == "Customer":
        if not customer:
            frappe.throw(_("Pick the customer who sent this yield"))
        if not frappe.db.exists("Customer", customer):
            frappe.throw(_("Customer {0} not found").format(customer))
    values = {f: flt(v) for f, v in (("quantity", quantity), ("hash_qty", hash_qty), ("yield_percentage", yield_percentage),
                                      ("rosin_qty", rosin_qty), ("hash_to_rosin", hash_to_rosin),
                                      ("bho_qty", bho_qty), ("bho_yield", bho_yield))}
    if any(v < 0 for v in values.values()):
        frappe.throw(_("Values cannot be negative"))
    run_to = run_to or "SHO"
    if run_to not in ("SHO", "BHO"):
        frappe.throw(_("Run To must be SHO or BHO"))
    keep = ("quantity", "bho_qty", "bho_yield") if run_to == "BHO" else \
        ("quantity", "hash_qty", "yield_percentage", "rosin_qty", "hash_to_rosin")
    values = {k: (v if k in keep else 0) for k, v in values.items()}
    if run_to == "SHO" and not (values["yield_percentage"] or (values["quantity"] and values["hash_qty"]) or values["hash_to_rosin"]):
        frappe.throw(_("Run to SHO: enter Yield to Hash % (or Hash g with Qty) and / or Hash to Rosin %"))
    if run_to == "BHO" and not (values["bho_yield"] or (values["quantity"] and values["bho_qty"])):
        frappe.throw(_("Run to BHO: enter BHO Yield % (or BHO g with Qty)"))
    row = {"item_code": item_code, "yield_source": source, "run_to": run_to}
    row.update({k: v for k, v in values.items() if v})
    doc = frappe.get_doc({
        "doctype": YIELD_DOCTYPE,
        "customer": customer if source == "Customer" else None,
        "date": date or frappe.utils.nowdate(),
        "remarks": remarks or _("Added from the Inventory Dashboard"),
        "item_yield": [row],
    })
    doc.insert()
    doc.submit()
    saved = doc.item_yield[0]
    return {
        "name": doc.name,
        "item_group": frappe.db.get_value("Item", item_code, "item_group"),
        "yield_percentage": flt(saved.yield_percentage, 2),
        "hash_to_rosin": flt(saved.hash_to_rosin, 2),
        "bho_yield": flt(saved.get("bho_yield"), 2),
    }


@frappe.whitelist()
def yield_customers():
    """Customer choices for the Add Yield form (only for users who may add yields)."""
    if not can_add_yield():
        return []
    return frappe.get_all("Customer", filters={"disabled": 0}, fields=["name", "customer_name"],
                          order_by="customer_name asc", limit_page_length=0)


# ---------------------------------------------------------------- Notes (Fresh Frozen view)
NOTE_DOCTYPE = "Inventory Item Note"


def get_item_notes(item_codes):
    """{item_code: note} for logged-in users; the dashboard's data is also served to guests, notes are not."""
    if not item_codes or frappe.session.user == "Guest":
        return {}
    return dict(frappe.get_all(NOTE_DOCTYPE, filters={"item": ["in", list(set(item_codes))]},
                               fields=["item", "note"], as_list=True))


@frappe.whitelist(allow_guest=True)
def can_edit_notes():
    """Any logged-in desk user may write the Note column."""
    if frappe.session.user == "Guest":
        return False
    return frappe.db.get_value("User", frappe.session.user, "user_type") == "System User"


@frappe.whitelist(methods=["POST"])
def save_item_note(item_code, note=None):
    """One note per item, kept until someone changes it. Every change is in the note's version history."""
    if not can_edit_notes():
        frappe.throw(_("Log in to edit notes."), frappe.PermissionError)
    if not item_code or not frappe.db.exists("Item", item_code):
        frappe.throw(_("Item {0} not found").format(item_code))
    note = (note or "").strip()
    if frappe.db.exists(NOTE_DOCTYPE, item_code):
        doc = frappe.get_doc(NOTE_DOCTYPE, item_code)
        if (doc.note or "") != note:
            doc.note = note
            doc.save(ignore_permissions=True)
    elif note:
        doc = frappe.get_doc({"doctype": NOTE_DOCTYPE, "item": item_code, "note": note}).insert(ignore_permissions=True)
    else:
        return {"item_code": item_code, "note": ""}
    return {"item_code": item_code, "note": doc.note or "", "modified_by": doc.modified_by, "modified": str(doc.modified)}


# ---------------------------------------------------------------- Yields view (Fresh Frozen)
@frappe.whitelist(allow_guest=True)
def get_fresh_frozen_yields(project=None):
    """Every Fresh Frozen item with its yields as the Stock view shows them (Run to SHO / Run to BHO,
    averages, quality grade), whether it has stock or not. With a project: every item that moved in it."""
    groups = tuple(FRESH_FROZEN_GROUPS)
    if project:
        codes = frappe.db.sql_list("""
            SELECT DISTINCT sle.item_code
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabItem` i ON i.name = sle.item_code
            LEFT JOIN ({union}) vp ON vp.voucher_type = sle.voucher_type AND vp.voucher_no = sle.voucher_no
            WHERE i.item_group IN %(groups)s AND i.disabled = 0 AND i.custom_show_in_dashboard = 1
              AND sle.is_cancelled = 0
              AND IFNULL(NULLIF(sle.project, ''), IFNULL(vp.project, '')) = %(project)s
        """.format(union=VOUCHER_PROJECT_UNION), {"groups": groups, "project": project})
    else:
        codes = frappe.get_all("Item", filters={"item_group": ["in", groups], "disabled": 0,
                                                "custom_show_in_dashboard": 1}, pluck="name")
    info = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", codes or [""]]},
                                              fields=["name", "item_name", "item_group"])}

    on_hand, warehouses = {}, {}
    if project:
        rows = [r for g in groups for r in get_project_balances(g, "", [g], project)]
    else:
        rows = frappe.db.sql("""
            SELECT b.item_code, b.warehouse, b.actual_qty
            FROM `tabBin` b INNER JOIN `tabItem` i ON i.name = b.item_code
            WHERE i.item_group IN %(groups)s AND b.actual_qty != 0 AND b.warehouse NOT LIKE 'Virtual%%'
        """, {"groups": groups}, as_dict=True)
    for r in rows:
        on_hand[r.item_code] = on_hand.get(r.item_code, 0) + flt(r.actual_qty)
        warehouses.setdefault(r.item_code, set()).add(r.warehouse)

    yield_map = get_yield_data_for_items(codes)
    grades = get_quality_grades_for_items(codes)
    notes = get_item_notes(codes)
    items = []
    for code in codes:
        i = info.get(code)
        if not i:
            continue
        data = yield_map.get(code) or {}
        items.append({
            "item_code": code,
            "item_name": i.item_name,
            "item_group": i.item_group,
            "on_hand": flt(on_hand.get(code), 6),
            "warehouses": sorted(warehouses.get(code, [])),
            "yield_to_hash": data.get("yield_to_hash", ""),
            "hash_to_rosin": data.get("hash_to_rosin", ""),
            "yield_to_hash_parts": data.get("yield_to_hash_parts", []),
            "yield_to_hash_avg": data.get("yield_to_hash_avg"),
            "hash_to_rosin_parts": data.get("hash_to_rosin_parts", []),
            "bho_yield": data.get("bho_yield", ""),
            "bho_yield_parts": data.get("bho_yield_parts", []),
            "bho_yield_avg": data.get("bho_yield_avg"),
            "quality_grade": grades.get(code),
            "note": notes.get(code, ""),
        })

    projects = {}
    for g in groups:
        for p in get_projects_with_stock(g, "", [g]):
            projects[p["name"]] = p["project_name"]
    if project and project not in projects:
        projects[project] = (frappe.db.get_value("Project", project, "project_name") or "").strip() or project
    return {
        "items": items,
        "projects": [{"name": k, "project_name": v} for k, v in sorted(projects.items(), key=lambda kv: kv[1].lower())],
    }
