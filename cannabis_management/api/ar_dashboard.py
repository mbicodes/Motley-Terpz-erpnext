"""
AR Dashboard API — KPI endpoints for the AR Dashboard page.
All balances read from GL Entry (source of truth), not SI.outstanding_amount.
"""

import frappe
from frappe.utils import flt, nowdate, add_days

from cannabis_management.api.ar import DEFAULT_RECEIVABLE_ACCOUNTS

AR_CAP          = 400_000.0
DSO_PERIOD_DAYS = 30


def _gl_total_ar(customer=None, as_of=None):
    """GL Entry balance for all customers, or a single customer."""
    params = {"accounts": tuple(DEFAULT_RECEIVABLE_ACCOUNTS)}
    extra = ""
    if customer:
        extra += " AND party = %(customer)s"
        params["customer"] = customer
    if as_of:
        extra += " AND posting_date <= %(as_of)s"
        params["as_of"] = as_of

    result = frappe.db.sql(
        f"""
        SELECT COALESCE(SUM(debit - credit), 0) AS bal
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND account IN %(accounts)s
          AND is_cancelled = 0
          {extra}
        """,
        params,
        as_dict=True,
    )
    return flt(result[0].bal) if result else 0.0


# ── KPI summary ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ar_kpis():
    """Total AR (GL), DSO, Cap % used, Red List customer count."""
    today      = nowdate()
    from_date  = add_days(today, -DSO_PERIOD_DAYS)
    total_ar   = _gl_total_ar()

    sales = frappe.db.sql(
        """
        SELECT COALESCE(SUM(grand_total), 0) AS total
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND posting_date BETWEEN %(from_date)s AND %(today)s
        """,
        {"from_date": from_date, "today": today},
        as_dict=True,
    )
    credit_sales = flt(sales[0].total) if sales else 0.0
    dso = round((total_ar / credit_sales * DSO_PERIOD_DAYS), 1) if credit_sales > 0 else 0.0
    cap_pct = round((total_ar / AR_CAP) * 100, 1)

    rl = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT customer) AS cnt
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
          AND due_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        """,
        as_dict=True,
    )
    red_list_count = int(rl[0].cnt) if rl else 0

    return {
        "total_ar":       total_ar,
        "dso":            dso,
        "cap_pct":        cap_pct,
        "cap_limit":      AR_CAP,
        "red_list_count": red_list_count,
        "as_of":          today,
    }


# ── Red List table ────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_red_list():
    """
    Customers with invoices 30+ days past due.
    SI.outstanding_amount used for aging bucket / invoice count;
    GL Entry balance shown as the authoritative ledger figure.
    """
    rows = frappe.db.sql(
        """
        SELECT
            si.customer,
            COUNT(*)                              AS invoice_count,
            SUM(si.outstanding_amount)            AS overdue_si,
            MAX(DATEDIFF(CURDATE(), si.due_date)) AS max_days,
            COALESCE(MAX(st.sales_person), '')    AS sales_person
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Team` st
               ON st.parent = si.name AND st.parenttype = 'Sales Invoice'
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.due_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY si.customer
        ORDER BY overdue_si DESC
        """,
        as_dict=True,
    )

    if not rows:
        return []

    cust_tuple = tuple(r.customer for r in rows)
    gl = frappe.db.sql(
        """
        SELECT party AS customer,
               COALESCE(SUM(debit - credit), 0) AS gl_balance
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND party IN %(custs)s
          AND account IN %(accounts)s
          AND is_cancelled = 0
        GROUP BY party
        """,
        {"custs": cust_tuple, "accounts": tuple(DEFAULT_RECEIVABLE_ACCOUNTS)},
        as_dict=True,
    )
    gl_map = {r.customer: flt(r.gl_balance) for r in gl}

    def _bucket(days):
        d = int(days or 0)
        if d <= 60:  return "31-60"
        if d <= 90:  return "61-90"
        return "90+"

    return [
        {
            "customer":      r.customer,
            "overdue_si":    flt(r.overdue_si),
            "gl_balance":    gl_map.get(r.customer, 0.0),
            "max_days":      int(r.max_days or 0),
            "bucket":        _bucket(r.max_days),
            "invoice_count": int(r.invoice_count or 0),
            "sales_person":  r.sales_person or "",
        }
        for r in rows
    ]


# ── AR trend (8 weeks) ────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ar_trend():
    """
    Weekly AR outstanding snapshots for the last 8 weeks.
    Uses GL Entry cumulative balance up to each Sunday.
    """
    rows = frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(posting_date, '%%Y-%%u') AS week_key,
            MIN(posting_date)                    AS week_start,
            COALESCE(SUM(debit - credit), 0)     AS net_movement
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND account IN %(accounts)s
          AND is_cancelled = 0
          AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 8 WEEK)
        GROUP BY DATE_FORMAT(posting_date, '%%Y-%%u')
        ORDER BY week_key
        """,
        {"accounts": tuple(DEFAULT_RECEIVABLE_ACCOUNTS)},
        as_dict=True,
    )
    return [
        {"week": str(r.week_start), "net_movement": flt(r.net_movement)}
        for r in rows
    ]


# ── COD vs Credit ratio ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_cod_credit_ratio():
    """COD vs Credit totals for the current calendar month."""
    rows = frappe.db.sql(
        """
        SELECT
            CASE
                WHEN is_pos = 1 THEN 'COD / POS'
                WHEN (payment_terms_template IS NULL
                      OR payment_terms_template = '') THEN 'COD / No Terms'
                ELSE payment_terms_template
            END AS mode,
            COUNT(*)         AS cnt,
            SUM(grand_total) AS total
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND MONTH(posting_date) = MONTH(CURDATE())
          AND YEAR(posting_date)  = YEAR(CURDATE())
        GROUP BY mode
        ORDER BY total DESC
        """,
        as_dict=True,
    )

    cod_total    = sum(flt(r.total) for r in rows if "COD" in (r.mode or "").upper())
    credit_total = sum(flt(r.total) for r in rows if "COD" not in (r.mode or "").upper())

    return {
        "cod":       cod_total,
        "credit":    credit_total,
        "breakdown": [
            {"mode": r.mode, "count": int(r.cnt), "total": flt(r.total)}
            for r in rows
        ],
    }


# ── Per-customer ledger balance ───────────────────────────────────────────────

@frappe.whitelist()
def get_customer_gl_balance(customer):
    """Live GL ledger balance for a single customer (used by Red List popup)."""
    if not customer:
        return 0.0
    return _gl_total_ar(customer=customer)
