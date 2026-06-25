import datetime

import frappe
from frappe.utils import flt, getdate, nowdate


SALES_TARGET_DOCTYPE = "Sales Target"
RECON_SNAPSHOT_DOCTYPE = "AR Recon Snapshot"
ALL_COMPANIES = "All Companies"
TMM_GROUP_COMPANIES = ["Motley Terpz", "TSBC Ranch"]
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


def _stock_entry_yield_for_day(day):
    raw_lbs = _sum_sql(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('lb', 'lbs', 'pound', 'pounds') THEN sed.qty
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('kg', 'kilogram', 'kilograms') THEN sed.qty * 2.2046226218
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('g', 'gram', 'grams') THEN sed.qty / 453.59237
                ELSE sed.qty
            END
        ), 0) AS value
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        LEFT JOIN `tabItem` i ON i.name = sed.item_code
        WHERE se.docstatus = 1 AND se.purpose = 'Manufacture'
          AND se.posting_date = %(day)s
          AND COALESCE(sed.s_warehouse, '') != ''
          AND COALESCE(sed.t_warehouse, '') = ''
          AND (LOWER(COALESCE(i.item_group, '')) LIKE '%%raw%%' OR LOWER(COALESCE(i.item_group, '')) LIKE '%%flower%%' OR LOWER(COALESCE(sed.item_name, sed.item_code)) LIKE '%%fresh%%')
        """,
        {"day": str(day)},
    )
    finished_hash_g = _sum_sql(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('lb', 'lbs', 'pound', 'pounds') THEN sed.qty * 453.59237
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('kg', 'kilogram', 'kilograms') THEN sed.qty * 1000
                ELSE sed.qty
            END
        ), 0) AS value
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        LEFT JOIN `tabItem` i ON i.name = sed.item_code
        WHERE se.docstatus = 1 AND se.purpose = 'Manufacture'
          AND se.posting_date = %(day)s
          AND COALESCE(sed.t_warehouse, '') != ''
          AND COALESCE(sed.s_warehouse, '') = ''
          AND LOWER(CONCAT(COALESCE(i.item_group, ''), ' ', COALESCE(sed.item_name, sed.item_code))) LIKE '%%hash%%'
        """,
        {"day": str(day)},
    )
    rosin_g = _sum_sql(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('lb', 'lbs', 'pound', 'pounds') THEN sed.qty * 453.59237
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('kg', 'kilogram', 'kilograms') THEN sed.qty * 1000
                ELSE sed.qty
            END
        ), 0) AS value
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        LEFT JOIN `tabItem` i ON i.name = sed.item_code
        WHERE se.docstatus = 1 AND se.purpose = 'Manufacture'
          AND se.posting_date = %(day)s
          AND COALESCE(sed.t_warehouse, '') != ''
          AND COALESCE(sed.s_warehouse, '') = ''
          AND LOWER(CONCAT(COALESCE(i.item_group, ''), ' ', COALESCE(sed.item_name, sed.item_code))) LIKE '%%rosin%%'
        """,
        {"day": str(day)},
    )
    hash_input_g = _sum_sql(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('lb', 'lbs', 'pound', 'pounds') THEN sed.qty * 453.59237
                WHEN LOWER(COALESCE(sed.uom, '')) IN ('kg', 'kilogram', 'kilograms') THEN sed.qty * 1000
                ELSE sed.qty
            END
        ), 0) AS value
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        LEFT JOIN `tabItem` i ON i.name = sed.item_code
        WHERE se.docstatus = 1 AND se.purpose = 'Manufacture'
          AND se.posting_date = %(day)s
          AND COALESCE(sed.s_warehouse, '') != ''
          AND COALESCE(sed.t_warehouse, '') = ''
          AND LOWER(CONCAT(COALESCE(i.item_group, ''), ' ', COALESCE(sed.item_name, sed.item_code))) LIKE '%%hash%%'
        """,
        {"day": str(day)},
    )
    raw_g = raw_lbs * 453.59237
    return {
        "lbs_ran": raw_lbs,
        "hash_yield_pct": (finished_hash_g / raw_g * 100) if raw_g else 0,
        "rosin_yield_pct": (rosin_g / hash_input_g * 100) if hash_input_g else 0,
        "hash_out": finished_hash_g,
        "rosin_out": rosin_g,
    }


def _production_yield_for_day(day):
    native = _native_lab_yield_for_day(day)
    if any(flt(native.get(key)) for key in ("lbs_ran", "hash_out", "rosin_out")):
        return native
    return _stock_entry_yield_for_day(day)


def _lab_trends(start_date, end_date):
    rows = []
    for day in _days_between(start_date, end_date):
        y = _production_yield_for_day(day)
        rows.append({"date": str(day), **y})
    return rows

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


def _eod_rows(yesterday):
    if _doctype_exists("Lab Batch Entry Child"):
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
            {"day": str(yesterday)},
        )
        out = []
        for r in rows:
            hash_pct = 0.0
            if _doctype_exists("Hash Recording Child"):
                hash_rows = _safe_sql(
                    """
                    SELECT COALESCE(SUM(total_hash), 0) AS total_hash
                    FROM `tabHash Recording Child`
                    WHERE parent IN (SELECT name FROM `tabHash Recording` WHERE docstatus != 2)
                      AND date_transferred = %(day)s
                      AND strain_name = %(strain)s
                    """,
                    {"day": str(yesterday), "strain": r.strain_name},
                )
                total_hash = flt(hash_rows[0].total_hash) if hash_rows else 0
                amount_ran_grams = flt(r.amount_ran_grams)
                hash_pct = (total_hash / amount_ran_grams * 100) if amount_ran_grams else 0
            out.append({
                "run": r.run,
                "operator": r.operator,
                "input_lbs": flt(r.input_lbs) or (flt(r.amount_ran_grams) / 453.59237 if flt(r.amount_ran_grams) else 0),
                "hash_pct": hash_pct,
                "issue": r.run_for or "",
            })
        return out
    return []


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
    start = today - datetime.timedelta(days=29)
    y = _production_yield_for_day(yesterday)
    before = _production_yield_for_day(yesterday - datetime.timedelta(days=1))
    trends = _lab_trends(start, today)
    pending_count = _count("Sales Invoice", {"docstatus": 0})
    disc = _discrepancies()
    return {
        "as_of": str(today),
        "yesterday": str(yesterday),
        "production": {
            **y,
            "lbs_delta": flt(y.get("lbs_ran")) - flt(before.get("lbs_ran")),
            "hash_yield_delta": flt(y.get("hash_yield_pct")) - flt(before.get("hash_yield_pct")),
            "rosin_yield_delta": flt(y.get("rosin_yield_pct")) - flt(before.get("rosin_yield_pct")),
        },
        "trends": trends,
        "eod_rows": _eod_rows(yesterday),
        "pending_invoices": {"count": pending_count, "trend": _pending_invoices_trend(start, today)},
        "discrepancies": disc,
        "shipments": {"rows": _delivery_notes_yesterday(yesterday), "trend": _shipments_trend(start, today)},
    }
