"""
Backend for the "Sales Daily Sync" top sections of the
"Sales Target and Inventory Dashboard" Custom HTML Block.

  get_cod_deliveries_last_7_days -> COD orders shipped in the last 7 days.
      Delivery Notes posted in the last 7 days whose linked Sales Order
      (via Delivery Note Item.against_sales_order) has rows in its
      payment_schedule child table (COD per business rule, since the
      site has no dedicated "COD" Payment Term).

  get_predicted_vs_actual       -> Predicted vs actual money in (last 7 days).
      Submitted Sales Invoices posted in the last 7 days with
      outstanding_amount > 0: expected = grand_total,
      received = grand_total - outstanding_amount.
"""
import datetime
import frappe
from frappe.utils import add_days, nowdate, flt, getdate

# Rolling window shared by the two top sections.
WINDOW_DAYS = 7


@frappe.whitelist()
def get_cod_deliveries_last_7_days():
    to_date = nowdate()
    from_date = add_days(to_date, -WINDOW_DAYS)

    dns = frappe.get_all(
        "Delivery Note",
        filters={"posting_date": ["between", [from_date, to_date]], "docstatus": 1},
        fields=["name", "customer", "customer_name", "grand_total", "posting_date"],
        order_by="posting_date desc, creation desc",
    )

    rows = []
    for dn in dns:
        # Sales Orders this Delivery Note was created against
        sos = frappe.get_all(
            "Delivery Note Item",
            filters={"parent": dn.name},
            pluck="against_sales_order",
        )
        sos = sorted({s for s in sos if s})

        # keep only SOs that have a payment_schedule (COD per spec)
        cod_sos = [
            so for so in sos
            if frappe.db.exists("Payment Schedule", {"parent": so, "parenttype": "Sales Order"})
        ]
        if not cod_sos:
            continue

        rows.append({
            "delivery_note": dn.name,
            "sales_order": ", ".join(cod_sos),
            "customer": dn.customer_name or dn.customer,
            "amount": flt(dn.grand_total),
            "date": str(dn.posting_date),
        })

    return {
        "rows": rows,
        "total": sum(r["amount"] for r in rows),
        "count": len(rows),
        "from_date": str(from_date),
        "to_date": str(to_date),
    }


@frappe.whitelist()
def get_predicted_vs_actual():
    to_date = nowdate()
    from_date = add_days(to_date, -WINDOW_DAYS)

    # Totals across outstanding invoices in the last 7 days
    agg = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(grand_total), 0)                         AS expected_total,
            COALESCE(SUM(grand_total - outstanding_amount), 0)    AS received_total,
            COUNT(*)                                              AS cnt
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
          AND posting_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        {"from_date": from_date, "to_date": to_date},
        as_dict=True,
    )[0]

    sis = frappe.get_all(
        "Sales Invoice",
        filters={
            "outstanding_amount": [">", 0],
            "docstatus": 1,
            "posting_date": ["between", [from_date, to_date]],
        },
        fields=["name", "customer", "customer_name", "grand_total",
                "outstanding_amount", "posting_date"],
        order_by="posting_date desc, creation desc",
    )

    rows = []
    for si in sis:
        expected = flt(si.grand_total)
        received = expected - flt(si.outstanding_amount)
        rows.append({
            "reference": si.name,
            "customer": si.customer_name or si.customer,
            "expected": expected,
            "received": received,
            "outstanding": flt(si.outstanding_amount),
            "date": str(si.posting_date),
        })

    return {
        "rows": rows,
        "expected_total": flt(agg.expected_total),
        "received_total": flt(agg.received_total),
        "count": int(agg.cnt),
        "from_date": str(from_date),
        "to_date": str(to_date),
    }


# Shared AR definitions live in api.jamie so every dashboard agrees on the rules.
from cannabis_management.api.jamie import LEGACY_AR_CUTOFF, _get_excluded_customers

# "TMM Group" aggregates these companies (mirrors the AR Dashboard page).
TMM_GROUP_COMPANIES = ["Motley Terpz", "TSBC Ranch"]
ALL_COMPANIES = "All Companies"

# Common WHERE clause that strips company / internal / intercompany customers.
_AR_CUST_FILTER = """
      AND si.customer NOT IN %(exc)s
      AND COALESCE(c.is_internal_customer, 0) = 0
      AND (c.represents_company IS NULL OR c.represents_company = '')
      AND si.customer NOT IN (SELECT name FROM `tabCompany`)
"""


def _companies_for_scope(company):
    """Resolve the company filter -> list of company names, or None for all."""
    if not company or company == ALL_COMPANIES:
        return None
    if company == "TMM Group":
        return list(TMM_GROUP_COMPANIES)
    return [company]


@frappe.whitelist()
def get_ar_companies():
    """Company options for the AR section dropdown (mirrors the AR Dashboard page)."""
    companies = frappe.get_all("Company", pluck="name", order_by="name")
    options = [ALL_COMPANIES]
    # "TMM Group" is treated as the virtual Motley Terpz + TSBC Ranch group
    # (mirrors the AR Dashboard page), so list it once and drop any real
    # company literally named "TMM Group".
    if set(TMM_GROUP_COMPANIES) <= set(companies) or "TMM Group" in companies:
        options.append("TMM Group")
    options.extend([c for c in companies if c != "TMM Group"])
    return options


@frappe.whitelist()
def get_ar_week_summary(company=None):
    """
    AR Dashboard KPIs for the current week (Monday -> today), scoped to `company`
    (a Company name, "TMM Group", "All Companies", or None = all):
      1. legacy_ar_balance           — current outstanding on pre-cutoff invoices ("What is our legacy AR at?")
      2. legacy_collected_week       — payments received this week against legacy invoices
      3. post_legacy_accumulated_week— new (post-cutoff) AR invoiced this week
      4. ar_paid_down_week           — total payments received this week against any AR
    Legacy = Sales Invoice posting_date < LEGACY_AR_CUTOFF (2026-06-01); post-legacy = >=.
    """
    today = getdate(nowdate())
    week_start = today - datetime.timedelta(days=today.weekday())   # Monday of this week
    excluded = _get_excluded_customers()
    cutoff = getdate(LEGACY_AR_CUTOFF)

    scope = _companies_for_scope(company)
    company_clause = "" if scope is None else "AND si.company IN %(cos)s"
    cos = tuple(scope) if scope else None
    base = {"exc": excluded, "cos": cos}

    # ── 1. Legacy AR outstanding balance (snapshot now) ──────────────────────
    legacy_bal = frappe.db.sql(f"""
        SELECT COALESCE(SUM(si.outstanding_amount), 0) AS bal
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND si.posting_date < %(cutoff)s
          {company_clause}
          {_AR_CUST_FILTER}
    """, {**base, "cutoff": LEGACY_AR_CUTOFF}, as_dict=True)
    legacy_ar_balance = flt(legacy_bal[0].bal) if legacy_bal else 0.0

    # ── 2 & 4. Collections received THIS WEEK (split legacy vs all) ───────────
    pay_rows = frappe.db.sql(f"""
        SELECT per.allocated_amount AS amt, si.posting_date AS inv_date
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe ON pe.name = per.parent
        JOIN `tabSales Invoice` si ON si.name = per.reference_name
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.posting_date BETWEEN %(s)s AND %(e)s
          {company_clause}
          {_AR_CUST_FILTER}
    """, {**base, "s": str(week_start), "e": str(today)}, as_dict=True)

    legacy_collected = 0.0
    ar_paid_down = 0.0
    for r in pay_rows:
        amt = flt(r.amt)
        ar_paid_down += amt
        inv_date = getdate(str(r.inv_date)) if r.inv_date else today
        if inv_date < cutoff:
            legacy_collected += amt

    # ── 3. Post-legacy AR accumulated this week (new invoices raised this week) ─
    acc = frappe.db.sql(f"""
        SELECT COALESCE(SUM(si.grand_total), 0) AS amt
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.posting_date >= %(cutoff)s
          AND si.posting_date BETWEEN %(s)s AND %(e)s
          {company_clause}
          {_AR_CUST_FILTER}
    """, {**base, "cutoff": LEGACY_AR_CUTOFF, "s": str(week_start), "e": str(today)}, as_dict=True)
    post_legacy_accumulated = flt(acc[0].amt) if acc else 0.0

    return {
        "company": company or ALL_COMPANIES,
        "legacy_ar_balance": legacy_ar_balance,
        "legacy_collected_week": legacy_collected,
        "post_legacy_accumulated_week": post_legacy_accumulated,
        "ar_paid_down_week": ar_paid_down,
        "week_start": str(week_start),
        "week_end": str(today),
    }


RECON_UNRECONCILED = "Unreconciled"


def _unreconciled_rows(company):
    """Per-customer legacy AR (invoiced/paid/outstanding) for customers flagged
    Unreconciled, scoped to `company`. Numbers match the AR Dashboard page."""
    scope = _companies_for_scope(company)
    company_clause = "" if scope is None else "AND si.company IN %(cos)s"
    cos = tuple(scope) if scope else None
    rows = frappe.db.sql(f"""
        SELECT si.customer AS customer,
               COALESCE(MAX(c.customer_name), si.customer)           AS customer_name,
               COUNT(*)                                              AS invoice_count,
               COALESCE(SUM(si.grand_total), 0)                      AS invoiced,
               COALESCE(SUM(si.grand_total - si.outstanding_amount), 0) AS paid,
               COALESCE(SUM(si.outstanding_amount), 0)               AS outstanding
        FROM `tabSales Invoice` si
        JOIN `tabCustomer` c ON c.name = si.customer
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND si.posting_date < %(cutoff)s
          AND c.custom_reconciliation_status = %(unrec)s
          {company_clause}
          {_AR_CUST_FILTER}
        GROUP BY si.customer
        HAVING outstanding > 0.01
        ORDER BY customer_name ASC
    """, {"cutoff": LEGACY_AR_CUTOFF, "unrec": RECON_UNRECONCILED,
          "cos": cos, "exc": _get_excluded_customers()}, as_dict=True)
    for r in rows:
        r["customer_name"] = r["customer_name"] or r["customer"]
        r["invoice_count"] = int(r["invoice_count"] or 0)
        r["invoiced"] = flt(r["invoiced"])
        r["paid"] = flt(r["paid"])
        r["outstanding"] = flt(r["outstanding"])
    return rows


def _record_snapshot(company, count, outstanding, d):
    name = f"{d}|{company}"
    if frappe.db.exists("AR Recon Snapshot", name):
        frappe.db.set_value("AR Recon Snapshot", name,
                            {"unreconciled_count": count, "outstanding_total": outstanding})
    else:
        frappe.get_doc({
            "doctype": "AR Recon Snapshot", "__newname": name,
            "snapshot_date": str(d), "company": company,
            "unreconciled_count": count, "outstanding_total": outstanding,
        }).insert(ignore_permissions=True)


@frappe.whitelist()
def get_unreconciled_customers(company=None):
    """
    Table of Unreconciled customers (Customer | Invoiced | Paid | Outstanding) for
    the selected company, plus the current count and a day-over-day trend recorded
    in AR Recon Snapshot.
    """
    company = company or ALL_COMPANIES
    today = getdate(nowdate())
    week_start = today - datetime.timedelta(days=today.weekday())

    rows = _unreconciled_rows(company)
    count = len(rows)
    outstanding_total = sum(r["outstanding"] for r in rows)

    # Record today's snapshot for this scope (so the trend builds even between scheduler runs)
    try:
        _record_snapshot(company, count, outstanding_total, today)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "AR Recon Snapshot upsert failed")

    prev = frappe.db.sql("""
        SELECT snapshot_date, unreconciled_count
        FROM `tabAR Recon Snapshot`
        WHERE company = %(co)s AND snapshot_date < %(t)s
        ORDER BY snapshot_date DESC LIMIT 1
    """, {"co": company, "t": str(today)}, as_dict=True)

    wk = frappe.db.sql("""
        SELECT unreconciled_count
        FROM `tabAR Recon Snapshot`
        WHERE company = %(co)s AND snapshot_date >= %(ws)s AND snapshot_date < %(t)s
        ORDER BY snapshot_date ASC LIMIT 1
    """, {"co": company, "ws": str(week_start), "t": str(today)}, as_dict=True)

    return {
        "company": company,
        "rows": rows,
        "count": count,
        "outstanding_total": outstanding_total,
        "prev_count": int(prev[0].unreconciled_count) if prev else None,
        "prev_date": str(prev[0].snapshot_date) if prev else None,
        "week_start_count": int(wk[0].unreconciled_count) if wk else None,
        "as_of": str(today),
    }


def snapshot_unreconciled():
    """Daily scheduler hook: snapshot the unreconciled count for every company scope."""
    today = getdate(nowdate())
    for company in get_ar_companies():
        rows = _unreconciled_rows(company)
        _record_snapshot(company, len(rows), sum(r["outstanding"] for r in rows), today)
    frappe.db.commit()
