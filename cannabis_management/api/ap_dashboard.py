import frappe
from frappe.utils import flt, nowdate, add_days


@frappe.whitelist()
def get_ap_data(company="All", period_days=30):
    """
    Returns KPI summary and per-vendor AP table for the AP Dashboard.

    period_days: lookback window for "Paid This Period" column (default 30).
    """
    period_days = int(period_days)
    today = nowdate()
    period_start = add_days(today, -period_days)

    pi_company_filter = ""
    pe_company_filter = ""
    company_params = []
    if company and company != "All":
        pi_company_filter = "AND pi.company = %s"
        pe_company_filter = "AND pe.company = %s"
        company_params = [company]

    # ── 1. Outstanding AP per vendor ──────────────────────────────────────────
    # Exclude intercompany: supplier name matches another entity's company name
    outstanding_rows = frappe.db.sql(
        """
        SELECT
            pi.supplier,
            pi.company,
            SUM(pi.outstanding_amount) AS outstanding,
            MIN(ps.due_date) AS next_due_date,
            COUNT(DISTINCT pi.name) AS open_invoices,
            SUM(CASE WHEN pi.outstanding_amount < 0 THEN pi.outstanding_amount ELSE 0 END) AS credit_amount
        FROM `tabPurchase Invoice` pi
        LEFT JOIN `tabPayment Schedule` ps
               ON ps.parent = pi.name AND ps.outstanding > 0
        WHERE pi.docstatus = 1
          AND pi.outstanding_amount != 0
          AND pi.supplier NOT IN ('TSBC Ranch', 'Motley Terpz')
          {pi_company_filter}
        GROUP BY pi.supplier, pi.company
        ORDER BY
            CASE pi.company WHEN 'TSBC Ranch' THEN 1 WHEN 'Motley Terpz' THEN 2 ELSE 3 END,
            outstanding DESC
        """.format(pi_company_filter=pi_company_filter),
        company_params,
        as_dict=True,
    )

    # ── 2. Paid this period per vendor ────────────────────────────────────────
    paid_params = [period_start] + company_params
    paid_rows = frappe.db.sql(
        """
        SELECT
            pe.party AS supplier,
            pe.company,
            SUM(pe.paid_amount) AS paid_amount
        FROM `tabPayment Entry` pe
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Pay'
          AND pe.posting_date >= %s
          {pe_company_filter}
        GROUP BY pe.party, pe.company
        """.format(pe_company_filter=pe_company_filter),
        paid_params,
        as_dict=True,
    )

    paid_map = {}
    for r in paid_rows:
        key = (r.supplier, r.company)
        paid_map[key] = flt(r.paid_amount)

    # ── 3. Build vendor table rows ────────────────────────────────────────────
    vendors = []
    for r in outstanding_rows:
        outstanding = flt(r.outstanding)
        credit = flt(r.credit_amount)
        paid = paid_map.get((r.supplier, r.company), 0.0)
        live_balance = outstanding - paid  # balance after recent payments

        if outstanding <= 0 and credit < 0:
            status = "CREDIT"
        elif outstanding == 0:
            status = "CLEARED"
        elif outstanding > 25000:
            status = "HIGH"
        else:
            status = "OPEN"

        vendors.append(
            {
                "supplier": r.supplier,
                "company": r.company,
                "outstanding": outstanding,
                "paid_this_period": paid,
                "live_balance": max(live_balance, 0),
                "status": status,
                "next_due_date": str(r.next_due_date) if r.next_due_date else None,
                "open_invoices": r.open_invoices or 0,
                "credit_amount": abs(credit),
            }
        )

    # ── 4. KPI summary ────────────────────────────────────────────────────────
    total_ap = sum(flt(v["outstanding"]) for v in vendors if flt(v["outstanding"]) > 0)
    tsbc_ap = sum(
        flt(v["outstanding"])
        for v in vendors
        if v["company"] == "TSBC Ranch" and flt(v["outstanding"]) > 0
    )
    motley_ap = sum(
        flt(v["outstanding"])
        for v in vendors
        if v["company"] == "Motley Terpz" and flt(v["outstanding"]) > 0
    )
    open_vendors = len({v["supplier"] for v in vendors if flt(v["outstanding"]) > 0})
    total_credits = sum(
        flt(v["credit_amount"]) for v in vendors if flt(v["credit_amount"]) > 0
    )
    total_paid = sum(flt(v["paid_this_period"]) for v in vendors)

    # Scheduled payments: next 30 days from Payment Schedule
    sched_params = [today, add_days(today, 30)] + company_params
    sched_rows = frappe.db.sql(
        """
        SELECT IFNULL(SUM(ps.outstanding), 0) AS total
        FROM `tabPayment Schedule` ps
        JOIN `tabPurchase Invoice` pi ON pi.name = ps.parent
        WHERE pi.docstatus = 1
          AND ps.outstanding > 0
          AND ps.due_date BETWEEN %s AND %s
          AND pi.supplier NOT IN ('TSBC Ranch', 'Motley Terpz')
          {pi_company_filter}
        """.format(pi_company_filter=pi_company_filter),
        sched_params,
        as_dict=True,
    )
    scheduled_payments = flt(sched_rows[0].total) if sched_rows else 0.0

    kpis = {
        "total_ap": total_ap,
        "tsbc_ap": tsbc_ap,
        "motley_ap": motley_ap,
        "open_vendors": open_vendors,
        "total_credits": total_credits,
        "scheduled_payments": scheduled_payments,
        "paid_this_period": total_paid,
        "period_days": period_days,
    }

    return {"kpis": kpis, "vendors": vendors}
