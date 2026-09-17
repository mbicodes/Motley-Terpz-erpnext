import datetime

import frappe
from frappe.utils import flt, getdate, nowdate


SALES_TARGET_DOCTYPE = "Sales Target"
RECON_SNAPSHOT_DOCTYPE = "AR Recon Snapshot"
ALL_COMPANIES = "Master Touch Manufacturing"
TMM_GROUP_COMPANIES = ["Master Touch Manufacturing"]
LEGACY_AR_CUTOFF = "2026-06-01"


def _doctype_exists(doctype):
    try:
        return bool(frappe.db.exists("DocType", doctype))
    except Exception:
        return False


def _has_column(doctype, column):
    try:
        return bool(frappe.db.has_column(doctype, column))
    except Exception:
        return False


def _field_first(doctype, candidates):
    for fieldname in candidates:
        if _has_column(doctype, fieldname):
            return fieldname
    return None


def _safe_sql(query, values=None, default=None):
    try:
        return frappe.db.sql(query, values or {}, as_dict=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Daily Sync Dashboard SQL failed")
        return default if default is not None else []


def _sum_sql(query, values=None, key="value"):
    rows = _safe_sql(query, values, [])
    return flt(rows[0].get(key)) if rows else 0.0


def _count(doctype, filters=None):
    if not _doctype_exists(doctype):
        return 0
    try:
        return frappe.db.count(doctype, filters or {})
    except Exception:
        return 0


def _fmt_date(value):
    return str(value) if value else ""


def _days_between(start_date, end_date):
    start = getdate(start_date)
    end = getdate(end_date)
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += datetime.timedelta(days=1)
    return days


def _trend_rows(start_date, end_date, query, values=None, value_key="value"):
    values = dict(values or {})
    values.update({"from_date": str(start_date), "to_date": str(end_date)})
    rows = _safe_sql(query, values, [])
    by_date = {str(r.get("dt")): flt(r.get(value_key)) for r in rows}
    return [{"date": str(day), "value": by_date.get(str(day), 0)} for day in _days_between(start_date, end_date)]


def _company_scope(company=None):
    if not company or company == ALL_COMPANIES:
        return None
    if company == "TMM Group":
        return list(TMM_GROUP_COMPANIES)
    return [company]


def _company_clause(alias, company=None):
    scope = _company_scope(company)
    if not scope:
        return "", {}
    return f" AND {alias}.company IN %(companies)s", {"companies": tuple(scope)}


def _payment_mode_column(doctype):
    return _field_first(doctype, ["mode_of_payment", "custom_mode_of_payment"])


def _sales_order_paid_column():
    return _field_first("Sales Order", ["paid_amount", "advance_paid", "base_paid_amount"])


def _cod_filter_sql(alias="so"):
    mode_col = _payment_mode_column("Sales Order")
    paid_col = _sales_order_paid_column()
    clauses = []
    if mode_col:
        clauses.append(f"{alias}.{mode_col} = 'COD'")
    clauses.append(
        "EXISTS (SELECT 1 FROM `tabPayment Schedule` ps "
        f"WHERE ps.parent = {alias}.name AND ps.parenttype = 'Sales Order')"
    )
    paid_expr = f"COALESCE({alias}.{paid_col}, 0)" if paid_col else "0"
    return "(" + " OR ".join(clauses) + ")", paid_expr


def _sales_target_amount(today=None):
    if not _doctype_exists(SALES_TARGET_DOCTYPE):
        return 0.0
    today = getdate(today or nowdate())
    amount_col = _field_first(SALES_TARGET_DOCTYPE, ["target_amount", "amount", "target"])
    if not amount_col:
        return 0.0
    if _has_column(SALES_TARGET_DOCTYPE, "month") and _has_column(SALES_TARGET_DOCTYPE, "year"):
        return _sum_sql(
            f"""
            SELECT COALESCE(SUM({amount_col}), 0) AS value
            FROM `tabSales Target`
            WHERE month = %(month)s AND year = %(year)s
            """,
            {"month": today.strftime("%B"), "year": today.year},
        )
    date_col = _field_first(SALES_TARGET_DOCTYPE, ["target_date", "date", "from_date", "start_date"])
    if not date_col:
        return 0.0
    month_start = today.replace(day=1)
    next_month = (month_start.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    month_end = next_month - datetime.timedelta(days=1)
    return _sum_sql(
        f"""
        SELECT COALESCE(SUM({amount_col}), 0) AS value
        FROM `tabSales Target`
        WHERE {date_col} BETWEEN %(start)s AND %(end)s
        """,
        {"start": str(month_start), "end": str(month_end)},
    )


def _crm_summary():
    leads = _count("CRM Lead") or _count("Lead")
    deals_total = _count("CRM Deal") or _count("Opportunity")
    won = 0
    open_deals = 0
    if _doctype_exists("CRM Deal"):
        won = _count("CRM Deal", {"status": ["in", ["Won", "Closed Won"]]})
        open_deals = max(deals_total - won - _count("CRM Deal", {"status": ["in", ["Lost", "Closed Lost"]]}), 0)
    elif _doctype_exists("Opportunity"):
        won = _count("Opportunity", {"status": "Converted"})
        open_deals = _count("Opportunity", {"status": ["not in", ["Converted", "Lost", "Closed"]]})
    conversion = (won / deals_total * 100) if deals_total else 0
    return {"total_leads": leads, "ongoing_deals": open_deals, "won_deals": won, "conversion_pct": conversion}


def _ar_summary(company=None):
    today = getdate(nowdate())
    start_14 = today - datetime.timedelta(days=13)
    company_sql, company_values = _company_clause("si", company)
    cod_where, paid_expr = _cod_filter_sql("so")

    cod = _safe_sql(
        f"""
        SELECT COUNT(*) AS count, COALESCE(SUM(so.grand_total), 0) AS amount
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
          AND COALESCE(so.grand_total, 0) > {paid_expr}
          AND {cod_where}
        """,
        {},
        [{}],
    )[0]

    yday = today - datetime.timedelta(days=1)
    cod_yday = _safe_sql(
        f"""
        SELECT COUNT(*) AS count, COALESCE(SUM(so.grand_total), 0) AS amount
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
          AND so.transaction_date <= %(yday)s
          AND COALESCE(so.grand_total, 0) > {paid_expr}
          AND {cod_where}
        """,
        {"yday": str(yday)},
        [{}],
    )[0]

    invoiced_month = _sum_sql(
        f"""
        SELECT COALESCE(SUM(si.grand_total), 0) AS value
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND YEAR(si.posting_date) = YEAR(CURDATE())
          AND MONTH(si.posting_date) = MONTH(CURDATE())
          {company_sql}
        """,
        company_values,
    )
    target = _sales_target_amount(today)
    target_pct = (invoiced_month / target * 100) if target else 0

    expected = _sum_sql(
        f"""
        SELECT COALESCE(SUM(si.grand_total), 0) AS value
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {company_sql}
        """,
        {**company_values, "from_date": str(start_14), "to_date": str(today)},
    )
    outstanding = _sum_sql(
        f"""
        SELECT COALESCE(SUM(si.outstanding_amount), 0) AS value
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {company_sql}
        """,
        {**company_values, "from_date": str(start_14), "to_date": str(today)},
    )
    received = max(expected - outstanding, 0)
    accuracy = (received / expected * 100) if expected else 0

    ar_trend = _trend_rows(
        start_14,
        today,
        f"""
        SELECT si.posting_date AS dt, COALESCE(SUM(si.outstanding_amount), 0) AS value
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.outstanding_amount > 0
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {company_sql}
        GROUP BY si.posting_date
        """,
        company_values,
    )

    unreconciled = _unreconciled_snapshot_series(company, start_14, today)
    return {
        "cod_unpaid_count": int(cod.get("count") or 0),
        "cod_unpaid_amount": flt(cod.get("amount")),
        "cod_count_delta": int(cod.get("count") or 0) - int(cod_yday.get("count") or 0),
        "cod_amount_delta": flt(cod.get("amount")) - flt(cod_yday.get("amount")),
        "prediction_accuracy": accuracy,
        "prediction_expected": expected,
        "prediction_received": received,
        "sales_target_pct": target_pct,
        "sales_month_actual": invoiced_month,
        "sales_month_target": target,
        "ar_trend": ar_trend,
        "unreconciled_trend": unreconciled,
    }


def _unreconciled_snapshot_series(company, start_date, end_date):
    if _doctype_exists(RECON_SNAPSHOT_DOCTYPE):
        rows = _safe_sql(
            """
            SELECT snapshot_date AS dt, unreconciled_count AS value
            FROM `tabAR Recon Snapshot`
            WHERE snapshot_date BETWEEN %(from_date)s AND %(to_date)s
              AND company = %(company)s
            ORDER BY snapshot_date
            """,
            {"from_date": str(start_date), "to_date": str(end_date), "company": company or ALL_COMPANIES},
            [],
        )
        if rows:
            by_date = {str(r.dt): flt(r.value) for r in rows}
            return [{"date": str(d), "value": by_date.get(str(d), 0)} for d in _days_between(start_date, end_date)]
    status_col = "custom_reconciliation_status" if _has_column("Customer", "custom_reconciliation_status") else None
    if not status_col:
        return [{"date": str(d), "value": 0} for d in _days_between(start_date, end_date)]
    current = _sum_sql(
        """
        SELECT COUNT(DISTINCT si.customer) AS value
        FROM `tabSales Invoice` si
        JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1 AND si.outstanding_amount > 0.01
          AND c.custom_reconciliation_status = 'Unreconciled'
        """,
    )
    return [{"date": str(d), "value": current if d == end_date else 0} for d in _days_between(start_date, end_date)]


def _cash_bank_rows():
    if not _doctype_exists("Payment Entry"):
        return []
    today = getdate(nowdate())
    start = today - datetime.timedelta(days=13)
    rows = _safe_sql(
        """
        SELECT pe.posting_date AS date, pe.mode_of_payment AS type, pe.paid_amount AS amount, pe.name
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive'
          AND pe.posting_date BETWEEN %(start)s AND %(end)s
        ORDER BY pe.posting_date DESC, pe.creation DESC
        LIMIT 8
        """,
        {"start": str(start), "end": str(today)},
    )
    return [{"date": _fmt_date(r.date), "type": r.type or "Payment", "amount": flt(r.amount), "name": r.name} for r in rows]


def _outstanding_accounts(company=None):
    company_sql, values = _company_clause("si", company)
    rows = _safe_sql(
        f"""
        SELECT si.customer, COALESCE(MAX(si.customer_name), si.customer) AS customer_name,
               COALESCE(SUM(si.outstanding_amount), 0) AS amount,
               MAX(DATEDIFF(CURDATE(), si.due_date)) AS days_overdue
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.outstanding_amount > 0.01
          {company_sql}
        GROUP BY si.customer
        ORDER BY amount DESC
        LIMIT 8
        """,
        values,
    )
    return [{"customer": r.customer_name or r.customer, "amount": flt(r.amount), "days_overdue": int(r.days_overdue or 0)} for r in rows]


def _native_lab_yield_for_day(day):
    """Prefer the custom lab doctypes because their units are explicit.

    Lab Batch/Hash/Rosin rows record pounds and grams side by side; this avoids
    mixing Stock Entry LBS inputs with Gram outputs when calculating yield.
    """
    lab = {"lbs_ran": 0.0, "hash_yield_pct": 0.0, "rosin_yield_pct": 0.0, "hash_out": 0.0, "rosin_out": 0.0}

    if _doctype_exists("Lab Batch Entry Child"):
        rows = _safe_sql(
            """
            SELECT COALESCE(SUM(pounds_ran), 0) AS pounds_ran,
                   COALESCE(SUM(amount_ran_grams), 0) AS amount_ran_grams
            FROM `tabLab Batch Entry Child` child
            JOIN `tabLab Batch Entry` parent ON parent.name = child.parent
            WHERE parent.docstatus != 2 AND child.date_transferred = %(day)s
            """,
            {"day": str(day)},
        )
        if rows:
            grams = flt(rows[0].amount_ran_grams)
            pounds = flt(rows[0].pounds_ran)
            lab["lbs_ran"] = pounds or (grams / 453.592 if grams else 0)

    if _doctype_exists("Hash Recording Child"):
        rows = _safe_sql(
            """
            SELECT COALESCE(SUM(total_hash), 0) AS total_hash,
                   COALESCE(SUM(amount_ran_grams), 0) AS amount_ran_grams
            FROM `tabHash Recording Child` child
            JOIN `tabHash Recording` parent ON parent.name = child.parent
            WHERE parent.docstatus != 2 AND child.date_transferred = %(day)s
            """,
            {"day": str(day)},
        )
        if rows:
            total_hash = flt(rows[0].total_hash)
            amount_ran_grams = flt(rows[0].amount_ran_grams)
            lab["hash_out"] = total_hash
            if amount_ran_grams:
                lab["hash_yield_pct"] = total_hash / amount_ran_grams * 100
            if not lab["lbs_ran"] and amount_ran_grams:
                lab["lbs_ran"] = amount_ran_grams / 453.592

    if _doctype_exists("Lab Tolling Data"):
        rows = _safe_sql(
            """
            SELECT COALESCE(SUM(CAST(total_hash AS DECIMAL(18,6))), 0) AS total_hash,
                   COALESCE(SUM(CAST(total_rosin AS DECIMAL(18,6))), 0) AS total_rosin,
                   COALESCE(SUM(raw_material_quantity), 0) AS raw_lbs,
                   COALESCE(SUM(CAST(amount_ran_grams AS DECIMAL(18,6))), 0) AS amount_ran_grams
            FROM `tabLab Tolling Data` child
            JOIN `tabRosin Recording` parent ON parent.name = child.parent
            WHERE parent.docstatus != 2 AND child.date_transferred = %(day)s
            """,
            {"day": str(day)},
        )
        if rows:
            total_hash = flt(rows[0].total_hash)
            total_rosin = flt(rows[0].total_rosin)
            raw_lbs = flt(rows[0].raw_lbs)
            amount_ran_grams = flt(rows[0].amount_ran_grams)
            lab["rosin_out"] = total_rosin
            if total_hash:
                lab["rosin_yield_pct"] = total_rosin / total_hash * 100
            if not lab["hash_out"]:
                lab["hash_out"] = total_hash
            if not lab["hash_yield_pct"] and amount_ran_grams and total_hash:
                lab["hash_yield_pct"] = total_hash / amount_ran_grams * 100
            if not lab["lbs_ran"]:
                lab["lbs_ran"] = raw_lbs or (amount_ran_grams / 453.592 if amount_ran_grams else 0)

    return lab


# ---------------------------------------------------------------------------
# Conversion Entry production metrics.
#
# Routing mirrors the Production Log print format
# (cannabis_management/print_format/production_log) line for line — that print
# format is the source of truth for how a conversion line is classified, and
# for the expected yield it prints against each stage:
#
#   FROZEN     Fresh Frozen (LBS) -> hash / rosin (Grams)   expected 3%
#   ROSIN_VRR  rosin (Grams)      -> VRR (Grams)            expected 90%
#   VAPES      VRR                -> vapes (Each)           expected 95%
#   BLEND      rosin              -> rosin                  expected 90%
#   GUMMIES    any                -> gummies (Each)         expected 95%
#
# Only FROZEN and ROSIN_VRR lines feed the yield KPIs. Everything else — a
# "Primes -> Tier 1" re-grade, a "Fresh Frozen - SHO -> Fresh Frozen - BHO"
# re-designation, packaging — moves material without consuming it, and rolling
# those into the totals is what made the old numbers meaningless (a 335 lb
# warehouse transfer showed up as 335 lbs "ran").
# ---------------------------------------------------------------------------
_CE_K_FROZEN = ["fresh frozen", "frozen", "fresh-frozen", "ff "]
_CE_K_ROSIN = ["rosin", "tier", "prime", "subprime", "full spec", "food grade", "t1", "t2", "t3", "static", "bubble"]
_CE_K_VRR = ["vrr", "vape ready"]
_CE_K_VAPE = ["vape", "hardware", "cart", "o2", "packaged"]
_CE_K_GUMMY = ["gumm"]

_CE_RM_SLOTS = range(1, 8)
_CE_FG_SLOTS = range(1, 4)

GRAMS_PER_LB = 453.59237

# Expected yields as printed on the Production Log.
FROZEN_YIELD_BENCHMARK = 3.0
ROSIN_VRR_YIELD_BENCHMARK = 90.0
BLEND_YIELD_BENCHMARK = 90.0

_CE_STAGE_LABELS = {
    "FROZEN": "Frozen → Rosin",
    "ROSIN_VRR": "Rosin → VRR",
    "VAPES": "VRR → Vapes",
    "BLEND": "Blend",
    "GUMMIES": "Gummies",
    "GENERIC": "Transfer / Re-grade",
}


def _empty_yield():
    return {
        "lbs_ran": 0.0,
        "hash_out": 0.0,
        "hash_yield_pct": 0.0,
        "rosin_in": 0.0,
        "rosin_out": 0.0,
        "rosin_yield_pct": 0.0,
        "runs": 0,
    }


def _has_production(metrics):
    return any(flt((metrics or {}).get(key)) for key in ("lbs_ran", "hash_out", "rosin_out"))


def _ce_item_meta(codes):
    """item_code -> (item_group, item_name).

    The denormalised `rm_*_item_group` / `fg_*_item_group` columns are blank on
    a chunk of the rows, so fall back to the Item master the same way the
    Production Log print format does.
    """
    codes = sorted({c for c in codes if c})
    if not codes:
        return {}
    # ignore_permissions: this is an aggregate read, and lab users who can see
    # the dashboard do not necessarily hold Item read permission.
    rows = frappe.get_all(
        "Item",
        filters={"name": ["in", codes]},
        fields=["name", "item_group", "item_name"],
        ignore_permissions=True,
    )
    return {r.name: (r.item_group or "", r.item_name or "") for r in rows}


def _ce_flags(row_group, code, meta):
    group, item_name = meta.get(code, ("", ""))
    hay = f"{row_group or group or ''} {code or ''} {item_name or ''}".lower()

    def has(keywords):
        return any(k in hay for k in keywords)

    return {
        "frozen": has(_CE_K_FROZEN),
        "rosin": has(_CE_K_ROSIN),
        "vrr": has(_CE_K_VRR),
        "vape": has(_CE_K_VAPE),
        "gummy": has(_CE_K_GUMMY),
    }


def _ce_route(row, meta):
    """Classify one Conversion Entry Item line -> (stage_key, rms, fgs)."""
    rms = []
    for i in _CE_RM_SLOTS:
        code = row.get(f"raw_material_{i}")
        if not code:
            continue
        rms.append({"qty": flt(row.get(f"qty_rm_{i}")), "flags": _ce_flags(row.get(f"rm_{i}_item_group"), code, meta)})

    fgs = []
    for i in _CE_FG_SLOTS:
        code = row.get(f"finished_good_{i}")
        if not code:
            continue
        fgs.append({"qty": flt(row.get(f"qty_fg_{i}")), "flags": _ce_flags(row.get(f"fg_{i}_item_group"), code, meta)})

    src_vrr = any(r["flags"]["vrr"] for r in rms)
    src_frozen = any(r["flags"]["frozen"] for r in rms)
    # VRR wins over the generic rosin flag, same precedence as the print format.
    src_rosin = any(r["flags"]["rosin"] for r in rms) and not src_vrr

    fg_gummy = any(f["flags"]["gummy"] for f in fgs)
    fg_vrr = any(f["flags"]["vrr"] for f in fgs)
    fg_rosin = any(f["flags"]["rosin"] for f in fgs) and not fg_vrr
    fg_vape = any(f["flags"]["vape"] for f in fgs) and not fg_gummy

    if fg_gummy:
        key = "GUMMIES"
    elif src_frozen and (fg_rosin or fg_vrr):
        key = "FROZEN"
    elif src_vrr and fg_vape:
        key = "VAPES"
    elif (src_rosin or src_vrr) and fg_vrr:
        key = "ROSIN_VRR"
    elif src_rosin and fg_rosin:
        key = "BLEND"
    else:
        key = "GENERIC"
    return key, rms, fgs


def _conversion_rows(start_date, end_date):
    if not _doctype_exists("Conversion Entry Item"):
        return []
    columns = ["ce.name AS entry", "ce.posting_date AS posting_date", "ce.owner AS owner", "ce.reasons AS reasons"]
    for i in _CE_RM_SLOTS:
        columns += [f"ci.raw_material_{i}", f"ci.qty_rm_{i}", f"ci.rm_{i}_item_group"]
    for i in _CE_FG_SLOTS:
        columns += [f"ci.finished_good_{i}", f"ci.qty_fg_{i}", f"ci.fg_{i}_item_group"]
    return _safe_sql(
        f"""
        SELECT {", ".join(columns)}
        FROM `tabConversion Entry Item` ci
        JOIN `tabConversion Entry` ce ON ce.name = ci.parent
        WHERE ce.docstatus = 1 AND ce.posting_date BETWEEN %(from_date)s AND %(to_date)s
        ORDER BY ce.posting_date, ce.creation, ci.idx
        """,
        {"from_date": str(start_date), "to_date": str(end_date)},
    )


def _conversion_yield_by_day(start_date, end_date):
    rows = _conversion_rows(start_date, end_date)
    codes = []
    for row in rows:
        codes += [row.get(f"raw_material_{i}") for i in _CE_RM_SLOTS]
        codes += [row.get(f"finished_good_{i}") for i in _CE_FG_SLOTS]
    meta = _ce_item_meta(codes)

    by_day = {}
    runs_seen = {}
    for row in rows:
        day = str(row.get("posting_date"))
        bucket = by_day.setdefault(day, _empty_yield())
        stage, rms, fgs = _ce_route(row, meta)
        if stage == "FROZEN":
            bucket["lbs_ran"] += sum(r["qty"] for r in rms if r["flags"]["frozen"])
            bucket["hash_out"] += sum(f["qty"] for f in fgs if f["flags"]["rosin"] or f["flags"]["vrr"])
        elif stage == "ROSIN_VRR":
            # Only a genuine rosin -> VRR press counts. A VRR -> VRR line is a
            # repack (input == output), and folding those in pins the yield at
            # a meaningless 100%.
            press_in = sum(r["qty"] for r in rms if r["flags"]["rosin"] and not r["flags"]["vrr"])
            if not press_in:
                continue
            bucket["rosin_in"] += press_in
            bucket["rosin_out"] += sum(f["qty"] for f in fgs if f["flags"]["vrr"])
        else:
            continue
        seen = runs_seen.setdefault(day, set())
        if row.get("entry") not in seen:
            seen.add(row.get("entry"))
            bucket["runs"] += 1

    for bucket in by_day.values():
        input_grams = bucket["lbs_ran"] * GRAMS_PER_LB
        bucket["hash_yield_pct"] = (bucket["hash_out"] / input_grams * 100) if input_grams else 0.0
        bucket["rosin_yield_pct"] = (bucket["rosin_out"] / bucket["rosin_in"] * 100) if bucket["rosin_in"] else 0.0
    return by_day


def _legacy_lab_days(start_date, end_date):
    """Days still covered only by the pre-Conversion Entry lab doctypes."""
    days = set()
    for child, parent in (
        ("Lab Batch Entry Child", "Lab Batch Entry"),
        ("Hash Recording Child", "Hash Recording"),
        ("Lab Tolling Data", "Rosin Recording"),
    ):
        if not _doctype_exists(child):
            continue
        rows = _safe_sql(
            f"""
            SELECT DISTINCT child.date_transferred AS dt
            FROM `tab{child}` child
            JOIN `tab{parent}` parent ON parent.name = child.parent
            WHERE parent.docstatus != 2
              AND child.date_transferred BETWEEN %(from_date)s AND %(to_date)s
            """,
            {"from_date": str(start_date), "to_date": str(end_date)},
        )
        days |= {str(r.get("dt")) for r in rows if r.get("dt")}
    return days


def _lab_yield_by_day(start_date, end_date):
    """date string -> production metrics, for every day in the range."""
    by_day = _conversion_yield_by_day(start_date, end_date)
    legacy_days = _legacy_lab_days(start_date, end_date)

    out = {}
    for day in _days_between(start_date, end_date):
        key = str(day)
        metrics = by_day.get(key)
        if _has_production(metrics):
            out[key] = metrics
            continue
        # Conversion Entry replaced Lab Batch Entry / Hash Recording / Rosin
        # Recording in Aug 2026; older days only exist on the legacy doctypes.
        if key in legacy_days:
            legacy = _native_lab_yield_for_day(day)
            if _has_production(legacy):
                # Rosin Recording on those days mirrors the hash total into the
                # rosin column, so its "rosin yield" is always 100% — keep the
                # wash figures only.
                out[key] = {
                    **_empty_yield(),
                    "lbs_ran": flt(legacy.get("lbs_ran")),
                    "hash_out": flt(legacy.get("hash_out")),
                    "hash_yield_pct": flt(legacy.get("hash_yield_pct")),
                }
                continue
        out[key] = metrics or _empty_yield()
    return out


def _production_yield_for_day(day):
    return _lab_yield_by_day(day, day).get(str(day)) or _empty_yield()


def _delivery_notes_yesterday(yesterday):
    if not _doctype_exists("Delivery Note"):
        return []
    rows = _safe_sql(
        """
        SELECT dn.name, dn.customer_name, dn.customer, dn.grand_total, dn.posting_date,
               COUNT(dni.name) AS item_count, COALESCE(SUM(dni.qty), 0) AS total_qty
        FROM `tabDelivery Note` dn
        LEFT JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
        WHERE dn.docstatus = 1 AND dn.posting_date = %(day)s
        GROUP BY dn.name
        ORDER BY dn.creation DESC
        LIMIT 8
        """,
        {"day": str(yesterday)},
    )
    return [{"name": r.name, "customer": r.customer_name or r.customer, "items": int(r.item_count or 0), "qty": flt(r.total_qty), "value": flt(r.grand_total)} for r in rows]



def _latest_delivery_notes(yesterday, lookback_days=120):
    """Shipments for yesterday, falling back to the last day anything shipped."""
    rows = _safe_sql(
        """
        SELECT MAX(posting_date) AS dt
        FROM `tabDelivery Note`
        WHERE docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        {"from_date": str(getdate(yesterday) - datetime.timedelta(days=lookback_days)), "to_date": str(yesterday)},
    )
    day = rows[0].get("dt") if rows else None
    if not day:
        return str(yesterday), []
    return str(day), _delivery_notes_yesterday(day)

def _shipments_trend(start_date, end_date):
    return _trend_rows(
        start_date,
        end_date,
        """
        SELECT posting_date AS dt, COUNT(*) AS value
        FROM `tabDelivery Note`
        WHERE docstatus = 1 AND posting_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY posting_date
        """,
    )


def _pending_invoices_trend(start_date, end_date):
    return _trend_rows(
        start_date,
        end_date,
        """
        SELECT posting_date AS dt, COUNT(*) AS value
        FROM `tabSales Invoice`
        WHERE docstatus = 0 AND posting_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY posting_date
        """,
    )


def _discrepancies():
    for doctype in ["ERP-METRC Reconciliation", "ERP METRC Reconciliation", "Physical Inventory Verification"]:
        if not _doctype_exists(doctype):
            continue
        status_field = _field_first(doctype, ["status", "workflow_state"])
        filters = {}
        if status_field:
            filters[status_field] = ["not in", ["Resolved", "Closed", "Cancelled"]]
        try:
            rows = frappe.get_all(doctype, filters=filters, fields=["name", status_field] if status_field else ["name"], limit=8, order_by="modified desc")
        except Exception:
            rows = []
        return {"doctype": doctype, "open_count": len(rows), "rows": [{"item": r.name, "status": r.get(status_field) or "Open", "erp_qty": None, "metrc_qty": None, "physical_qty": None} for r in rows]}
    return {"doctype": None, "open_count": 0, "rows": []}


def _eod_rows(day):
    """One row per (Conversion Entry, stage) for the day being shown."""
    rows = _conversion_rows(day, day)
    if not rows:
        return _legacy_eod_rows(day)

    codes = []
    for row in rows:
        codes += [row.get(f"raw_material_{i}") for i in _CE_RM_SLOTS]
        codes += [row.get(f"finished_good_{i}") for i in _CE_FG_SLOTS]
    meta = _ce_item_meta(codes)

    grouped = {}
    order = []
    for row in rows:
        stage, rms, fgs = _ce_route(row, meta)
        key = (row.get("entry"), stage)
        if key not in grouped:
            grouped[key] = {
                "run": row.get("entry"),
                "doctype": "Conversion Entry",
                "operator": row.get("owner"),
                "stage": _CE_STAGE_LABELS.get(stage, stage),
                "stage_key": stage,
                "input": 0.0,
                "input_uom": "lbs" if stage == "FROZEN" else "g",
                "output": 0.0,
                "output_uom": "each" if stage in ("VAPES", "GUMMIES") else "g",
                "yield_pct": None,
                "benchmark": None,
                "issue": row.get("reasons") or "",
            }
            order.append(key)
        bucket = grouped[key]

        if stage == "FROZEN":
            bucket["input"] += sum(r["qty"] for r in rms if r["flags"]["frozen"])
            bucket["output"] += sum(f["qty"] for f in fgs if f["flags"]["rosin"] or f["flags"]["vrr"])
            bucket["benchmark"] = FROZEN_YIELD_BENCHMARK
        elif stage == "ROSIN_VRR":
            bucket["input"] += sum(r["qty"] for r in rms if r["flags"]["rosin"] or r["flags"]["vrr"])
            bucket["output"] += sum(f["qty"] for f in fgs if f["flags"]["vrr"])
            bucket["benchmark"] = ROSIN_VRR_YIELD_BENCHMARK
        elif stage == "BLEND":
            bucket["input"] += sum(r["qty"] for r in rms if r["flags"]["rosin"])
            bucket["output"] += sum(f["qty"] for f in fgs if f["flags"]["rosin"])
            bucket["benchmark"] = BLEND_YIELD_BENCHMARK
        else:
            # Packaging and transfers: quantities are worth showing, but input
            # and output are in different units so a yield % would be noise.
            bucket["input"] += sum(r["qty"] for r in rms)
            bucket["output"] += sum(f["qty"] for f in fgs)

    operators = {}
    for user in {g["operator"] for g in grouped.values() if g["operator"]}:
        operators[user] = frappe.db.get_value("User", user, "full_name") or user

    out = []
    for key in order:
        bucket = grouped[key]
        bucket["operator"] = operators.get(bucket["operator"], bucket["operator"])
        if bucket["stage_key"] == "FROZEN":
            input_grams = bucket["input"] * GRAMS_PER_LB
            bucket["yield_pct"] = (bucket["output"] / input_grams * 100) if input_grams else 0.0
        elif bucket["benchmark"]:
            bucket["yield_pct"] = (bucket["output"] / bucket["input"] * 100) if bucket["input"] else 0.0
        out.append(bucket)

    # Yield-bearing stages first, then the biggest runs.
    out.sort(key=lambda r: (r["benchmark"] is None, -flt(r["input"])))
    return out[:12]


def _legacy_eod_rows(day):
    """Pre-Conversion Entry runs, for days that only exist on Lab Batch Entry."""
    if not _doctype_exists("Lab Batch Entry Child"):
        return []
    rows = _safe_sql(
        """
        SELECT child.parent AS run, parent.owner AS operator,
               child.pounds_ran AS input_lbs,
               child.amount_ran_grams AS amount_ran_grams,
               child.strain_name,
               child.run_for
        FROM `tabLab Batch Entry Child` child
        JOIN `tabLab Batch Entry` parent ON parent.name = child.parent
        WHERE parent.docstatus != 2 AND child.date_transferred = %(day)s
        ORDER BY parent.modified DESC
        LIMIT 8
        """,
        {"day": str(day)},
    )
    out = []
    for r in rows:
        total_hash = 0.0
        if _doctype_exists("Hash Recording Child"):
            hash_rows = _safe_sql(
                """
                SELECT COALESCE(SUM(total_hash), 0) AS total_hash
                FROM `tabHash Recording Child`
                WHERE parent IN (SELECT name FROM `tabHash Recording` WHERE docstatus != 2)
                  AND date_transferred = %(day)s
                  AND strain_name = %(strain)s
                """,
                {"day": str(day), "strain": r.strain_name},
            )
            total_hash = flt(hash_rows[0].total_hash) if hash_rows else 0.0
        input_lbs = flt(r.input_lbs) or (flt(r.amount_ran_grams) / GRAMS_PER_LB if flt(r.amount_ran_grams) else 0.0)
        input_grams = input_lbs * GRAMS_PER_LB
        out.append({
            "run": r.run,
            "doctype": "Lab Batch Entry",
            "operator": r.operator,
            "stage": _CE_STAGE_LABELS["FROZEN"],
            "stage_key": "FROZEN",
            "input": input_lbs,
            "input_uom": "lbs",
            "output": total_hash,
            "output_uom": "g",
            "yield_pct": (total_hash / input_grams * 100) if input_grams else 0.0,
            "benchmark": FROZEN_YIELD_BENCHMARK,
            "issue": r.run_for or "",
        })
    return out


@frappe.whitelist()
def get_sales_daily_sync_dashboard(company=None):
    today = getdate(nowdate())
    start = today - datetime.timedelta(days=13)
    summary = _ar_summary(company)
    return {
        "as_of": str(today),
        "company": company or ALL_COMPANIES,
        "summary": summary,
        "crm": _crm_summary(),
        "cash_bank_rows": _cash_bank_rows(),
        "outstanding_accounts": _outstanding_accounts(company),
        "period": {"from_date": str(start), "to_date": str(today)},
    }


@frappe.whitelist()
def get_lab_daily_sync_dashboard():
    today = getdate(nowdate())
    yesterday = today - datetime.timedelta(days=1)
    yesterday_key = str(yesterday)
    trend_start = today - datetime.timedelta(days=29)
    # The lab does not run every day, so look further back than the trend
    # window to find the last day that actually ran.
    lookback_start = today - datetime.timedelta(days=119)

    by_day = _lab_yield_by_day(lookback_start, today)
    trends = [{"date": str(day), **by_day.get(str(day), _empty_yield())} for day in _days_between(trend_start, today)]

    # The KPI cards report yesterday, full stop. When nothing ran, `last_run`
    # carries the most recent day that did, so the cards can say so instead of
    # showing an unexplained row of zeros.
    days = [str(day) for day in _days_between(lookback_start, yesterday)]
    run_days = [day for day in days if _has_production(by_day.get(day))]
    current = by_day.get(yesterday_key) or _empty_yield()

    last_run = None
    if run_days:
        last_run_date = run_days[-1]
        last_run = {
            "date": last_run_date,
            "days_ago": (yesterday - getdate(last_run_date)).days,
            **(by_day.get(last_run_date) or _empty_yield()),
        }

    def _prior_value(field, gate):
        """Latest value of `field` before yesterday on a day that actually ran
        that stage — the lab skips days, so comparing against a blank calendar
        day would turn every KPI delta into the day's own value."""
        for day in reversed([d for d in days if d < yesterday_key]):
            metrics = by_day.get(day) or {}
            if flt(metrics.get(gate)):
                return flt(metrics.get(field))
        return None

    def _delta(field, gate):
        if not flt(current.get(gate)):
            return None
        prior = _prior_value(field, gate)
        return None if prior is None else flt(current.get(field)) - prior

    shipment_date, shipment_rows = _latest_delivery_notes(yesterday)

    return {
        "as_of": str(today),
        "yesterday": yesterday_key,
        "ran_yesterday": _has_production(current),
        "last_run": last_run,
        "eod_date": (last_run or {}).get("date") or yesterday_key,
        "production": {
            **current,
            "has_wash_run": bool(flt(current.get("lbs_ran"))),
            "has_rosin_run": bool(flt(current.get("rosin_in"))),
            "lbs_delta": _delta("lbs_ran", "lbs_ran"),
            "hash_yield_delta": _delta("hash_yield_pct", "lbs_ran"),
            "rosin_yield_delta": _delta("rosin_yield_pct", "rosin_in"),
            "hash_benchmark": FROZEN_YIELD_BENCHMARK,
            "rosin_benchmark": ROSIN_VRR_YIELD_BENCHMARK,
        },
        "trends": trends,
        "period": {"from_date": str(trend_start), "to_date": str(today)},
        "eod_rows": _eod_rows((last_run or {}).get("date") or yesterday_key),
        "pending_invoices": {"count": _count("Sales Invoice", {"docstatus": 0}), "trend": _pending_invoices_trend(trend_start, today)},
        "discrepancies": _discrepancies(),
        "shipments": {
            "date": shipment_date,
            "is_yesterday": shipment_date == str(yesterday),
            "rows": shipment_rows,
            "trend": _shipments_trend(trend_start, today),
        },
    }
