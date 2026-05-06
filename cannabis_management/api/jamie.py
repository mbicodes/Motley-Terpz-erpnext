import frappe
import datetime
from frappe.utils import nowdate, get_first_day, get_last_day, add_days, add_months, cint


def _get_date_range(period):
    today = nowdate()
    if period == 'weekly':
        return add_days(today, -7), today
    elif period == 'monthly':
        return get_first_day(today), get_last_day(today)
    elif period == 'last_month':
        last_month_ref = add_months(today, -1)
        return get_first_day(last_month_ref), get_last_day(last_month_ref)
    else:  # 'overall'
        return None, None


# ─────────────────────────────────────────────────────────
# Sales Invoices
# ─────────────────────────────────────────────────────────

INTERNAL_CUSTOMERS = ('Motley Terpz', 'MT', 'MTPZ')

@frappe.whitelist()
def get_sales_by_period(period='monthly'):
    """
    All submitted Sales Invoices filtered by period (cross-company).
    Excludes internal customers.
    period: 'weekly' | 'monthly' | 'overall'
    """
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    from_date, to_date = _get_date_range(period)

    conditions = 'si.docstatus = 1 AND si.customer NOT IN %(internal_customers)s'
    args = {'internal_customers': INTERNAL_CUSTOMERS}

    if from_date:
        conditions += ' AND si.posting_date >= %(from_date)s'
        args['from_date'] = from_date
    if to_date:
        conditions += ' AND si.posting_date <= %(to_date)s'
        args['to_date'] = to_date

    invoices = frappe.db.sql(f"""
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.company,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            si.status,
            si.currency
        FROM `tabSales Invoice` si
        WHERE {conditions}
        ORDER BY si.posting_date DESC
    """, args, as_dict=True)

    total = sum(float(i.grand_total or 0) for i in invoices)

    return {
        'period':    period,
        'from_date': from_date,
        'to_date':   to_date,
        'total':     total,
        'count':     len(invoices),
        'invoices':  invoices,
    }


# ─────────────────────────────────────────────────────────
# AR
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ar_summary():
    """
    Top-level AR numbers for KPI cards (cross-company).
    """
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    result = frappe.db.sql("""
        SELECT
            COUNT(name)                              AS total_invoices,
            SUM(grand_total)                         AS total_billed,
            SUM(outstanding_amount)                  AS total_outstanding,
            SUM(grand_total - outstanding_amount)    AS total_collected,
            COUNT(DISTINCT customer)                 AS total_clients
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
    """, as_dict=True)

    return result[0] if result else {}


@frappe.whitelist()
def get_ar_detail(period='overall'):
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    from_date, to_date = _get_date_range(period)

    conditions = 'si.docstatus = 1 AND si.outstanding_amount > 0'
    args = {}

    if from_date:
        conditions += ' AND si.posting_date >= %(from_date)s'
        args['from_date'] = from_date
    if to_date:
        conditions += ' AND si.posting_date <= %(to_date)s'
        args['to_date'] = to_date

    rows = frappe.db.sql(f"""
        SELECT
            si.name                                      AS invoice_id,
            si.customer                                  AS client,
            si.customer_name                             AS client_name,
            si.company,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            si.status,
            si.currency
        FROM `tabSales Invoice` si
        WHERE {conditions}
        ORDER BY si.due_date ASC
    """, args, as_dict=True)

    return rows


@frappe.whitelist()
def get_ar_by_client():
    """
    Accounts Receivable grouped by customer (cross-company).
    """
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    rows = frappe.db.sql("""
        SELECT
            si.customer                                  AS client,
            si.customer_name                             AS client_name,
            COUNT(si.name)                               AS invoice_count,
            SUM(si.grand_total)                          AS total_billed,
            SUM(si.outstanding_amount)                   AS total_outstanding,
            SUM(si.grand_total - si.outstanding_amount)  AS total_paid,
            MAX(si.due_date)                             AS latest_due_date,
            MIN(si.due_date)                             AS oldest_due_date
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
        GROUP BY si.customer, si.customer_name
        ORDER BY total_outstanding DESC
    """, as_dict=True)

    return rows


# ─────────────────────────────────────────────────────────
# AP
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ap_summary():
    """
    Top-level AP numbers for KPI cards (cross-company).
    """
    if not frappe.has_permission('Purchase Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    result = frappe.db.sql("""
        SELECT
            COUNT(name)             AS total_bills,
            SUM(grand_total)        AS total_billed,
            SUM(outstanding_amount) AS total_outstanding
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
    """, as_dict=True)

    return result[0] if result else {}


@frappe.whitelist()
def get_ap_detail(period='overall'):
    if not frappe.has_permission('Purchase Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    from_date, to_date = _get_date_range(period)

    conditions = 'pi.docstatus = 1 AND pi.outstanding_amount > 0'
    args = {}

    if from_date:
        conditions += ' AND pi.posting_date >= %(from_date)s'
        args['from_date'] = from_date
    if to_date:
        conditions += ' AND pi.posting_date <= %(to_date)s'
        args['to_date'] = to_date

    rows = frappe.db.sql(f"""
        SELECT
            pi.name                 AS invoice_id,
            pi.supplier             AS client,
            pi.supplier_name        AS client_name,
            pi.company,
            pi.posting_date,
            pi.due_date,
            pi.grand_total,
            pi.outstanding_amount,
            pi.status,
            pi.currency
        FROM `tabPurchase Invoice` pi
        WHERE {conditions}
        ORDER BY pi.due_date ASC
    """, args, as_dict=True)

    return rows


@frappe.whitelist()
def get_ap_by_supplier():
    """
    Accounts Payable grouped by supplier (cross-company).
    """
    if not frappe.has_permission('Purchase Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    rows = frappe.db.sql("""
        SELECT
            pi.supplier                                  AS client,
            pi.supplier_name                             AS client_name,
            COUNT(pi.name)                               AS invoice_count,
            SUM(pi.grand_total)                          AS total_billed,
            SUM(pi.outstanding_amount)                   AS total_outstanding,
            SUM(pi.grand_total - pi.outstanding_amount)  AS total_paid,
            MAX(pi.due_date)                             AS latest_due_date,
            MIN(pi.due_date)                             AS oldest_due_date
        FROM `tabPurchase Invoice` pi
        WHERE pi.docstatus = 1
          AND pi.outstanding_amount > 0
        GROUP BY pi.supplier, pi.supplier_name
        ORDER BY total_outstanding DESC
    """, as_dict=True)

    return rows


# ─────────────────────────────────────────────────────────
# Batches
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_batches_in_production():
    """
    All active (non-completed, non-cancelled) batch projects (cross-company).
    """
    if not frappe.has_permission('Project', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    rows = frappe.db.sql("""
        SELECT
            p.name,
            p.project_name,
            p.company,
            p.status,
            p.expected_start_date,
            p.expected_end_date,
            p.percent_complete
        FROM `tabProject` p
        WHERE p.status NOT IN ('Completed', 'Cancelled')
        ORDER BY p.expected_start_date ASC
    """, as_dict=True)

    return rows


# ─────────────────────────────────────────────────────────
# Purchase Requests
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def create_purchase_request(qty, uom, schedule_date, why_need=None, type_val=None):
    doc = frappe.new_doc('Material Request')
    doc.material_request_type  = 'Purchase'
    doc.transaction_date       = frappe.utils.today()
    doc.schedule_date          = schedule_date
    doc.company                = 'Motley Terpz'
    doc.custom_quantity        = frappe.utils.flt(qty)
    doc.custom_why_need        = why_need or ''
    doc.custom_select_skxu     = type_val or ''
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=False)
    frappe.db.commit()
    return doc.name


# ─────────────────────────────────────────────────────────
# Timesheets
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_timesheets_by_period(period='monthly'):
    """
    Timesheets filtered by period (cross-company).
    period: 'weekly' | 'monthly' | 'overall'
    """
    if not frappe.has_permission('Timesheet', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    from_date, to_date = _get_date_range(period)

    conditions = 'ts.docstatus IN (0, 1)'
    args = {}

    if from_date:
        conditions += ' AND ts.start_date >= %(from_date)s'
        args['from_date'] = from_date
    if to_date:
        conditions += ' AND ts.start_date <= %(to_date)s'
        args['to_date'] = to_date

    rows = frappe.db.sql(f"""
        SELECT
            ts.name,
            ts.employee,
            ts.employee_name,
            ts.company,
            ts.start_date,
            ts.end_date,
            ts.total_hours,
            ts.total_billable_hours,
            ts.docstatus
        FROM `tabTimesheet` ts
        WHERE {conditions}
        ORDER BY ts.start_date DESC, ts.employee_name ASC
    """, args, as_dict=True)

    return rows


# ─────────────────────────────────────────────────────────
# Sample Giveaway
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sample_giveaway(period='monthly', month_offset=0):
    """
    All submitted Sales Invoice line items where the parent invoice has
    custom_order_type = 'Samples', filtered by period.
    Returns one row per line item: item_name, item_group, qty, uom,
    customer (given_to), posting_date (given_on), company.

    period:       'weekly' | 'monthly' | 'overall'
    month_offset: integer — 0 = current month, -1 = last month, etc.
                  Only applied when period == 'monthly'
    """
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    month_offset = cint(month_offset)

    if period == 'monthly' and month_offset != 0:
        ref_date  = add_months(nowdate(), month_offset)
        from_date = get_first_day(ref_date)
        to_date   = get_last_day(ref_date)
        label = datetime.date(
            int(str(from_date)[:4]),
            int(str(from_date)[5:7]),
            1
        ).strftime('%B %Y')
    else:
        from_date, to_date = _get_date_range(period)
        label = None

    conditions = "si.docstatus = 1 AND si.custom_order_type = 'Samples'"
    args = {}

    if from_date:
        conditions += ' AND si.posting_date >= %(from_date)s'
        args['from_date'] = str(from_date)
    if to_date:
        conditions += ' AND si.posting_date <= %(to_date)s'
        args['to_date'] = str(to_date)

    rows = frappe.db.sql(f"""
        SELECT
            si.posting_date                 AS given_on,
            si.customer_name                AS given_to,
            si.customer                     AS customer_id,
            si.name                         AS invoice_id,
            si.company,
            sii.item_code,
            sii.item_name,
            sii.item_group,
            sii.qty,
            sii.uom
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE {conditions}
        ORDER BY si.posting_date DESC, si.customer_name ASC, sii.item_name ASC
    """, args, as_dict=True)

    total_qty = sum(float(r.qty or 0) for r in rows)

    return {
        'period':       period,
        'month_offset': month_offset,
        'from_date':    str(from_date) if from_date else None,
        'to_date':      str(to_date)   if to_date   else None,
        'label':        label,
        'total_qty':    total_qty,
        'count':        len(rows),
        'rows':         rows,
    }


@frappe.whitelist()
def get_sample_by_client(period='monthly', month_offset=0):
    """
    Sample giveaway aggregated by customer.
    Returns: customer_name, total_qty, line_count, item_count, invoice_count.
    """
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    month_offset = cint(month_offset)

    if period == 'monthly' and month_offset != 0:
        ref_date  = add_months(nowdate(), month_offset)
        from_date = get_first_day(ref_date)
        to_date   = get_last_day(ref_date)
    else:
        from_date, to_date = _get_date_range(period)

    conditions = "si.docstatus = 1 AND si.custom_order_type = 'Samples'"
    args = {}

    if from_date:
        conditions += ' AND si.posting_date >= %(from_date)s'
        args['from_date'] = str(from_date)
    if to_date:
        conditions += ' AND si.posting_date <= %(to_date)s'
        args['to_date'] = str(to_date)

    rows = frappe.db.sql(f"""
        SELECT
            si.customer_name                            AS client_name,
            si.customer                                 AS client_id,
            COUNT(sii.name)                             AS line_count,
            COUNT(DISTINCT sii.item_code)               AS item_count,
            COUNT(DISTINCT si.name)                     AS invoice_count,
            SUM(sii.qty)                                AS total_qty
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE {conditions}
        GROUP BY si.customer, si.customer_name
        ORDER BY total_qty DESC
    """, args, as_dict=True)

    return rows


@frappe.whitelist()
def get_sample_product_by_month(num_months=6):
    """
    Sample giveaway pivoted by product × month.
    Returns:
      months:   ['Apr 2026', 'Mar 2026', ...]
      products: [
        {
            item_name: '...',
            item_group: '...',
            months: { 'Apr 2026': qty, 'Mar 2026': qty, ... },
            total_qty: float
        }, ...
      ]
    """
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    num_months = min(cint(num_months) or 6, 24)
    today = nowdate()

    # Build month list (most recent first)
    month_labels = []
    month_ranges = []
    for i in range(num_months):
        ref = add_months(today, -i)
        fd  = get_first_day(ref)
        ld  = get_last_day(ref)
        dt  = datetime.date(int(str(fd)[:4]), int(str(fd)[5:7]), 1)
        lbl = dt.strftime('%b %Y')
        month_labels.append(lbl)
        month_ranges.append((str(fd), str(ld), lbl))

    # Fetch all sample lines in the full range
    from_date = month_ranges[-1][0]
    to_date   = month_ranges[0][1]

    rows = frappe.db.sql("""
        SELECT
            sii.item_name,
            sii.item_code,
            sii.item_group,
            sii.qty,
            si.posting_date
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1
          AND si.custom_order_type = 'Samples'
          AND si.posting_date >= %(from_date)s
          AND si.posting_date <= %(to_date)s
        ORDER BY sii.item_name ASC
    """, {'from_date': from_date, 'to_date': to_date}, as_dict=True)

    # Pivot: item → { month_label → qty }
    product_map = {}
    for r in rows:
        key = r.item_name or r.item_code
        if key not in product_map:
            product_map[key] = {
                'item_name':  r.item_name,
                'item_code':  r.item_code,
                'item_group': r.item_group,
                'months':     {},
                'total_qty':  0.0,
            }

        pd = str(r.posting_date)
        dt = datetime.date(int(pd[:4]), int(pd[5:7]), 1)
        lbl = dt.strftime('%b %Y')
        qty = float(r.qty or 0)

        product_map[key]['months'][lbl] = product_map[key]['months'].get(lbl, 0) + qty
        product_map[key]['total_qty'] += qty

    products = sorted(product_map.values(), key=lambda x: -x['total_qty'])

    return {
        'months':   month_labels,
        'products': products,
        'from_date': from_date,
        'to_date':   to_date,
    }


# ─────────────────────────────────────────────────────────
# Legacy aliases — keep old callers working
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_this_month():
    return get_sales_by_period(period='monthly')


@frappe.whitelist()
def get_timesheets_this_month():
    return get_timesheets_by_period(period='monthly')


@frappe.whitelist()
def get_bank_payments_received(from_date, to_date):
    frappe.errprint(f"[get_bank_payments_received] from_date={from_date} | to_date={to_date}")
    rows = frappe.db.sql("""
        SELECT
            bank_gle.posting_date,
            bank_gle.voucher_no,
            bank_gle.voucher_type,
            bank_gle.account                                        AS bank_account,
            bank_gle.debit                                          AS amount,
            bank_gle.company,
            bank_gle.remarks,
            cust_gle.party,
            cust_gle.against                                        AS party_name,
            COALESCE(cust.customer_name, cust_gle.party)            AS customer_name
        FROM `tabGL Entry` bank_gle

        -- Only bank-account rows that received money (credit > 0)
        INNER JOIN `tabAccount` acc
            ON acc.name = bank_gle.account
           AND acc.account_type = 'Bank'

        -- Match the customer-side row on the same voucher
        INNER JOIN `tabGL Entry` cust_gle
            ON cust_gle.voucher_no   = bank_gle.voucher_no
           AND cust_gle.party_type   = 'Customer'
           AND cust_gle.party        != ''
           AND cust_gle.is_cancelled = 0

        -- Resolve full customer display name
        LEFT JOIN `tabCustomer` cust
            ON cust.name = cust_gle.party

        WHERE
            bank_gle.posting_date  >= %(from_date)s
            AND bank_gle.posting_date <= %(to_date)s
            AND bank_gle.debit > 0
            AND bank_gle.is_cancelled  = 0

        ORDER BY
            bank_gle.posting_date ASC,
            customer_name         ASC
    """, {
        'from_date': from_date,
        'to_date':   to_date,
    }, as_dict=True)

    frappe.errprint(f"[get_bank_payments_received] rows returned={len(rows)}")

    return rows


# ─────────────────────────────────────────────────────────
# Sales Dashboard
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_territories():
    """Territories that have at least one Target Detail configured."""
    rows = frappe.db.sql("""
        SELECT DISTINCT t.name
        FROM `tabTerritory` t
        INNER JOIN `tabTarget Detail` td
            ON td.parent = t.name AND td.parenttype = 'Territory'
        WHERE td.target_qty > 0 OR td.target_amount > 0
        ORDER BY t.name
    """, as_dict=True)
    return rows

@frappe.whitelist()
def get_sales_dashboard_data(period='weekly', territory=None, company=None):
    """
    Annual targets (Territory > Target Detail, scoped to Fiscal Year) pro-rated
    to the selected period vs actual sales.

    Cross-company: pulls from ALL companies, no company filter applied.
    The `company` parameter is accepted for backward compatibility but ignored.

    period: 'daily' | 'weekly' | 'monthly'
    """
    import datetime as dt_mod
    from frappe.utils import getdate, get_first_day, flt as _flt

    today = getdate(nowdate())

    # ── Date window + days for pro-rating ──
    if period == 'daily':
        from_date = to_date = str(today)
        window_days = 1
        period_label = 'Today'
    elif period == 'weekly':
        week_start = today - dt_mod.timedelta(days=today.weekday())
        from_date, to_date = str(week_start), str(today)
        window_days = (today - week_start).days + 1
        period_label = 'This Week'
    elif period == 'last_month':
        # First/last day of the previous month
        first_of_this_month = getdate(str(get_first_day(today)))
        last_month_end      = first_of_this_month - dt_mod.timedelta(days=1)
        last_month_start    = getdate(str(get_first_day(last_month_end)))
        from_date, to_date  = str(last_month_start), str(last_month_end)
        window_days         = (last_month_end - last_month_start).days + 1
        period_label        = 'Last Month'
    else:  # monthly (this month)
        month_start = getdate(str(get_first_day(today)))
        from_date, to_date = str(month_start), str(today)
        window_days = (today - month_start).days + 1
        period_label = 'This Month'

    # ── Resolve fiscal year for targets ──
    target_fy = None
    fy_days = 365
    if territory:
        fy_today = frappe.db.sql("""
            SELECT fy.name, fy.year_start_date, fy.year_end_date
            FROM `tabFiscal Year` fy
            WHERE %(today)s BETWEEN fy.year_start_date AND fy.year_end_date
              AND EXISTS (
                  SELECT 1 FROM `tabTarget Detail` td
                  WHERE td.parent = %(terr)s
                    AND td.parenttype = 'Territory'
                    AND td.fiscal_year = fy.name
              )
            LIMIT 1
        """, {'today': str(today), 'terr': territory}, as_dict=True)

        if fy_today:
            target_fy = fy_today[0]
        else:
            fy_latest = frappe.db.sql("""
                SELECT fy.name, fy.year_start_date, fy.year_end_date
                FROM `tabFiscal Year` fy
                JOIN `tabTarget Detail` td
                  ON td.fiscal_year = fy.name
                 AND td.parent = %(terr)s
                 AND td.parenttype = 'Territory'
                ORDER BY fy.year_start_date DESC
                LIMIT 1
            """, {'terr': territory}, as_dict=True)
            if fy_latest:
                target_fy = fy_latest[0]

        if target_fy:
            fy_days = (getdate(str(target_fy.year_end_date)) -
                       getdate(str(target_fy.year_start_date))).days + 1

    # ── Targets, scoped to chosen fiscal year ──
    targets = []
    if territory and target_fy:
        rows = frappe.get_all(
            "Target Detail",
            filters={
                "parent": territory,
                "parenttype": "Territory",
                "fiscal_year": target_fy.name,
            },
            fields=["item_group", "target_qty", "average_rate", "target_amount"],
            order_by="idx",
        )
        for t in rows:
            t_qty    = _flt(t.get('target_qty'))
            avg_rate = _flt(t.get('average_rate'))
            t_amount = _flt(t.get('target_amount')) or (t_qty * avg_rate)

            p_qty = (t_qty    / fy_days) * window_days if fy_days else 0
            p_rev = (t_amount / fy_days) * window_days if fy_days else 0

            targets.append({
                "item_group":        t.item_group,
                "avg_rate":          avg_rate,
                "annual_target_qty": t_qty,
                "annual_target_rev": t_amount,
                "period_target_qty": p_qty,
                "period_target_rev": p_rev,
            })

    # ── Actuals — NO COMPANY FILTER, cross-company aggregation ──
    actuals_raw = frappe.db.sql("""
        SELECT
            COALESCE(i.item_group, 'Other') AS item_group,
            SUM(sii.qty)                    AS total_qty,
            SUM(sii.base_net_amount)        AS total_rev
        FROM `tabSales Invoice Item` sii
        JOIN  `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabItem` i       ON i.name = sii.item_code
        WHERE si.docstatus    = 1
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND si.is_return    = 0
          AND si.customer     NOT IN %(internal_customers)s
        GROUP BY i.item_group
    """, {
        'from_date': from_date,
        'to_date':   to_date,
        'internal_customers': INTERNAL_CUSTOMERS,
    }, as_dict=True)

    from cannabis_management.cannabis_management.page.weekly_summary.weekly_summary import get_category_for_item_group
    target_groups = [t['item_group'] for t in targets]

    actuals_map = {}
    for r in actuals_raw:
        raw_ig = r.item_group or 'Other'
        mapped = get_category_for_item_group(raw_ig)

        matched = None
        for tg in target_groups:
            if tg == mapped or tg == raw_ig:
                matched = tg; break
            if tg.lower() in mapped.lower() or mapped.lower() in tg.lower():
                matched = tg; break
            if tg.lower() in raw_ig.lower():
                matched = tg; break

        key = matched or raw_ig
        if key not in actuals_map:
            actuals_map[key] = {'qty': 0.0, 'rev': 0.0}
        actuals_map[key]['qty'] += _flt(r.total_qty)
        actuals_map[key]['rev'] += _flt(r.total_rev)

    # ── Build product rows: targets first ──
    products, total_target, total_actual = [], 0.0, 0.0
    mapped_keys = set()

    for t in targets:
        ig         = t['item_group']
        mapped_keys.add(ig)
        actual_qty = actuals_map.get(ig, {}).get('qty', 0.0)
        actual_rev = actuals_map.get(ig, {}).get('rev', 0.0)
        p_target   = t['period_target_rev']

        variance_amt = actual_rev - p_target
        variance_pct = (variance_amt / p_target * 100.0) if p_target else 0.0
        progress_pct = min((actual_rev / p_target * 100.0) if p_target else 0.0, 150.0)

        products.append({
            "item_group":        ig,
            "avg_rate":          t['avg_rate'],
            "annual_target_qty": t['annual_target_qty'],
            "annual_target_rev": t['annual_target_rev'],
            "period_target_qty": t['period_target_qty'],
            "period_target_rev": p_target,
            "actual_qty":        actual_qty,
            "actual_rev":        actual_rev,
            "variance_amt":      variance_amt,
            "variance_pct":      variance_pct,
            "on_target":         actual_rev >= p_target,
            "progress_pct":      progress_pct,
            "has_target":        True,
        })
        total_target += p_target
        total_actual += actual_rev

    # ── Surface UNMAPPED actuals ──
    for key, vals in actuals_map.items():
        if key in mapped_keys or vals['rev'] <= 0:
            continue
        products.append({
            "item_group":        key + ' (no target)',
            "avg_rate":          0,
            "annual_target_qty": 0,
            "annual_target_rev": 0,
            "period_target_qty": 0,
            "period_target_rev": 0,
            "actual_qty":        vals['qty'],
            "actual_rev":        vals['rev'],
            "variance_amt":      vals['rev'],
            "variance_pct":      0,
            "on_target":         True,
            "progress_pct":      100.0,
            "has_target":        False,
        })
        total_actual += vals['rev']

    total_variance     = total_actual - total_target
    total_variance_pct = (total_variance / total_target * 100.0) if total_target else 0.0

    pending_count = frappe.db.count("Sales Invoice", {"docstatus": 0})

    return {
        "period":             period,
        "period_label":       period_label,
        "from_date":          from_date,
        "to_date":            to_date,
        "window_days":        window_days,
        "fiscal_year":        target_fy.name if target_fy else None,
        "fiscal_year_days":   fy_days,
        "period_fraction":    (window_days / float(fy_days)) if fy_days else 0,
        "territory":          territory,
        "products":           products,
        "total_target_rev":   total_target,
        "total_actual_rev":   total_actual,
        "total_variance":     total_variance,
        "total_variance_pct": total_variance_pct,
        "on_target":          total_actual >= total_target,
        "pending_invoices":   pending_count,
    }


@frappe.whitelist()
def get_dashboard_inventory(company=None):
    """Stock on hand by item group with cost valuation. Cross-company."""
    rows = frappe.db.sql("""
        SELECT
            COALESCE(i.item_group, 'Other')      AS item_group,
            SUM(b.actual_qty)                    AS qty_on_hand,
            SUM(b.actual_qty * b.valuation_rate) AS stock_value
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE b.actual_qty > 0
        GROUP BY i.item_group
        HAVING qty_on_hand > 0
        ORDER BY stock_value DESC
    """, as_dict=True)

    return rows

@frappe.whitelist()
def get_sales_matrix(territory=None):
    """
    Returns 2 matrices (monthly / weekly) for the sales dashboard.
    Matrix columns are anchored to TODAY's calendar (not the FY of targets).

    monthly: Jan → current month of current year
    weekly:  last 4 weeks (Mon-Sun chunks ending today)
    """
    import datetime as dt_mod
    from frappe.utils import getdate, get_first_day, get_last_day, flt as _flt

    today = getdate(nowdate())

    # ── Settings ──
    try:
        settings = frappe.get_single("Sales Dashboard Settings")
        monthly_oh = _flt(settings.monthly_overhead) or 35000.0
        default_margin_pct = _flt(settings.default_margin_pct) or 40.0
    except Exception:
        monthly_oh = 35000.0
        default_margin_pct = 40.0

    # ── Resolve fiscal year for TARGETS ──
    target_fy = None
    if territory:
        fy_today = frappe.db.sql("""
            SELECT fy.name, fy.year_start_date, fy.year_end_date
            FROM `tabFiscal Year` fy
            WHERE %(today)s BETWEEN fy.year_start_date AND fy.year_end_date
              AND EXISTS (
                  SELECT 1 FROM `tabTarget Detail` td
                  WHERE td.parent = %(terr)s AND td.parenttype = 'Territory'
                    AND td.fiscal_year = fy.name
              )
            LIMIT 1
        """, {'today': str(today), 'terr': territory}, as_dict=True)
        if fy_today:
            target_fy = fy_today[0]
        else:
            fy_latest = frappe.db.sql("""
                SELECT fy.name, fy.year_start_date, fy.year_end_date
                FROM `tabFiscal Year` fy
                JOIN `tabTarget Detail` td ON td.fiscal_year = fy.name
                WHERE td.parent = %(terr)s AND td.parenttype = 'Territory'
                ORDER BY fy.year_start_date DESC LIMIT 1
            """, {'terr': territory}, as_dict=True)
            if fy_latest:
                target_fy = fy_latest[0]

    targets_raw = []
    if territory and target_fy:
        targets_raw = frappe.get_all(
            "Target Detail",
            filters={"parent": territory, "parenttype": "Territory", "fiscal_year": target_fy.name},
            fields=["item_group", "target_qty", "average_rate", "target_amount"],
            order_by="idx",
        )

    target_index = {}
    for t in targets_raw:
        t_qty   = _flt(t.target_qty)
        avg_rt  = _flt(t.average_rate)
        t_amt   = _flt(t.target_amount) or (t_qty * avg_rt)
        target_index[t.item_group] = {
            "target_units": t_qty,
            "avg_price":    avg_rt,
            "target_rev":   t_amt,
        }

    # ── MONTHLY: Jan → current month ──
    monthly_columns = []
    for m in range(1, today.month + 1):
        mstart = today.replace(month=m, day=1)
        mend_dt = getdate(str(get_last_day(mstart)))
        mend = min(mend_dt, today)
        monthly_columns.append({
            "label":     mstart.strftime('%b'),
            "from_date": str(mstart),
            "to_date":   str(mend),
            "is_full":   mend == mend_dt,
        })

    # ── WEEKLY: last 4 calendar weeks (Mon-Sun) ──
    weekly_columns = []
    for w in range(3, -1, -1):
        wk_start = today - dt_mod.timedelta(days=today.weekday() + 7 * w)
        wk_end_full = wk_start + dt_mod.timedelta(days=6)
        wk_end = min(wk_end_full, today)
        if wk_end < wk_start:
            continue
        weekly_columns.append({
            "label":     wk_start.strftime('%b %d'),
            "from_date": str(wk_start),
            "to_date":   str(wk_end),
            "is_full":   wk_end == wk_end_full,
        })

    daily_columns = []
    for d in range(6, -1, -1):
        day = today - dt_mod.timedelta(days=d)
        daily_columns.append({
            "label":     day.strftime('%a %d'),
            "from_date": str(day),
            "to_date":   str(day),
            "is_full":   True,
        })

    # ── Empty fallback ──
    all_ranges = []
    for c in monthly_columns: all_ranges.append((c['from_date'], c['to_date']))
    for c in weekly_columns:  all_ranges.append((c['from_date'], c['to_date']))
    for c in daily_columns:   all_ranges.append((c['from_date'], c['to_date']))


    if not all_ranges:
        return {
            "monthly":     _empty_matrix(monthly_columns),
            "weekly":      _empty_matrix(weekly_columns),
            "daily":       _empty_matrix(daily_columns),
            "fiscal_year": target_fy.name if target_fy else None,
            "territory":   territory,
            "monthly_oh":  monthly_oh,
            "default_margin_pct": default_margin_pct,
        }

    min_date = min(r[0] for r in all_ranges)
    max_date = max(r[1] for r in all_ranges)

    # ── Queries ──
    target_groups_list = list(target_index.keys())
    if not target_groups_list:
        rev_rows, cogs_rows, company_rev_rows = [], [], []
    else:
        # Revenue + qty per item group per posting_date (TARGETED ITEM GROUPS ONLY)
        rev_rows = frappe.db.sql("""
            SELECT
                si.posting_date,
                COALESCE(i.item_group, 'Other') AS item_group,
                SUM(sii.qty)             AS qty,
                SUM(sii.base_net_amount) AS rev
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si  ON si.name = sii.parent
            LEFT JOIN `tabItem` i       ON i.name = sii.item_code
            WHERE si.docstatus = 1
              AND si.is_return = 0
              AND si.posting_date BETWEEN %(s)s AND %(e)s
              AND i.item_group IN %(ig)s
            GROUP BY si.posting_date, i.item_group
        """, {
            's':  min_date,
            'e':  max_date,
            'ig': tuple(target_groups_list),
        }, as_dict=True)

        # COGS per posting_date for the targeted item groups
        cogs_rows = frappe.db.sql("""
            SELECT
                sle.posting_date,
                ABS(SUM(sle.stock_value_difference)) AS cogs
            FROM `tabStock Ledger Entry` sle
            JOIN `tabSales Invoice` si ON si.name = sle.voucher_no
            JOIN `tabItem` i           ON i.name = sle.item_code
            WHERE sle.voucher_type = 'Sales Invoice'
              AND sle.is_cancelled = 0
              AND sle.posting_date BETWEEN %(s)s AND %(e)s
              AND si.docstatus = 1
              AND si.is_return = 0
              AND si.customer NOT IN %(ic)s
              AND i.item_group IN %(ig)s
            GROUP BY sle.posting_date
        """, {
            's':  min_date,
            'e':  max_date,
            'ic': INTERNAL_CUSTOMERS,
            'ig': tuple(target_groups_list),
        }, as_dict=True)

        # Company-level revenue (ALL item groups, broken out by company)
        company_rev_rows = frappe.db.sql("""
            SELECT
                si.posting_date,
                si.company,
                SUM(sii.base_net_amount) AS rev
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            JOIN `tabItem` i           ON i.name = sii.item_code
            WHERE si.docstatus = 1
              AND si.is_return = 0
              AND si.posting_date BETWEEN %(s)s AND %(e)s
              AND si.customer NOT IN %(ic)s
              AND i.item_group IN %(ig)s
            GROUP BY si.posting_date, si.company
        """, {
            's':  min_date,
            'e':  max_date,
            'ic': INTERNAL_CUSTOMERS,
            'ig': tuple(target_groups_list),
        }, as_dict=True)

    monthly = _build_matrix(monthly_columns, target_index, rev_rows, cogs_rows,
                            company_rev_rows, monthly_oh, default_margin_pct, 'monthly')
    weekly  = _build_matrix(weekly_columns,  target_index, rev_rows, cogs_rows,
                            company_rev_rows, monthly_oh, default_margin_pct, 'weekly')
    daily = _build_matrix(daily_columns, target_index, rev_rows, cogs_rows,
                          company_rev_rows, monthly_oh, default_margin_pct, 'daily')
    return {
        "monthly":     monthly,
        "weekly":      weekly,
        "daily":       daily,
        "fiscal_year": target_fy.name if target_fy else None,
        "territory":   territory,
        "monthly_oh":  monthly_oh,
        "default_margin_pct": default_margin_pct,
    }


def _empty_matrix(columns):
    return {
        "columns":      [c['label'] for c in columns],
        "column_dates": [[c['from_date'], c['to_date']] for c in columns],
        "products":     [],
        "totals":       {},
        "cogs":         {},
        "margin":       {},
        "margin_pct":   {},
        "oh":           {},
        "target_net":   {},
        "target_rev_by_col": {},
        "motley_totals": {},
        "tsbc_totals":   {},
        "other_totals":  {},
    }

def _build_matrix(columns, target_index, rev_rows, cogs_rows,
                  company_rev_rows, monthly_oh, default_margin_pct, granularity):
    import datetime as dt_mod
    from frappe.utils import getdate, get_first_day, get_last_day, flt as _flt

    col_labels = [c['label'] for c in columns]
    col_ranges = [(c['label'], getdate(c['from_date']), getdate(c['to_date'])) for c in columns]

    # Only build product rows for item groups that have targets in this territory
    products_map = {ig: {col: {"qty": 0.0, "rev": 0.0} for col in col_labels}
                    for ig in target_index}

    totals = {col: 0.0 for col in col_labels}
    cogs   = {col: 0.0 for col in col_labels}

    # Bucket revenue (targeted item groups only)
    for r in rev_rows:
        if not r.posting_date:
            continue
        pd = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        ig = r.item_group or 'Other'
        for label, fd, td in col_ranges:
            if fd <= pd <= td:
                if ig in products_map:
                    products_map[ig][label]["qty"] += _flt(r.qty)
                    products_map[ig][label]["rev"] += _flt(r.rev)
                totals[label] += _flt(r.rev)
                break

    # Bucket COGS by date
    for r in cogs_rows:
        if not r.posting_date:
            continue
        pd = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        for label, fd, td in col_ranges:
            if fd <= pd <= td:
                cogs[label] += _flt(r.cogs)
                break

    # Bucket per-company totals (ALL item groups, by company)
    motley_totals = {col: 0.0 for col in col_labels}
    tsbc_totals   = {col: 0.0 for col in col_labels}
    other_totals  = {col: 0.0 for col in col_labels}

    for r in company_rev_rows:
        if not r.posting_date:
            continue
        pd = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        company = (r.company or '').strip().lower()
        for label, fd, td in col_ranges:
            if fd <= pd <= td:
                if 'motley' in company:
                    motley_totals[label] += _flt(r.rev)
                elif 'tsbc' in company:
                    tsbc_totals[label] += _flt(r.rev)
                else:
                    other_totals[label] += _flt(r.rev)
                break

    # ── Per-column aggregates: targets, OH, margin, NET ──
    margin             = {}
    margin_pct         = {}
    oh                 = {}
    target_net         = {}
    target_rev_by_col  = {}
    product_col_targets = {ig: {} for ig in target_index}

    for label, fd, td in col_ranges:
        col_days = (td - fd).days + 1

        if granularity == 'monthly':
            # Partial-month aware: weight by days in host month
            month_full_days = (getdate(str(get_last_day(fd))) - getdate(str(get_first_day(fd)))).days + 1
            col_frac = col_days / float(month_full_days)
        else:
            # Weekly or Daily: monthly target divided across 28 days (4 weeks)
            # Full week = 7/28 = monthly/4
            # Full day  = 1/28 = monthly/28
            col_frac = col_days / 28.0

        oh[label] = monthly_oh * col_frac

        # Per-product target for this column (Target Amount is monthly)
        col_target_rev = 0.0
        for ig, t in target_index.items():
            monthly_target = _flt(t['target_rev'])
            cell_target = monthly_target * col_frac
            product_col_targets[ig][label] = cell_target
            col_target_rev += cell_target
        target_rev_by_col[label] = col_target_rev

        rev_col  = totals[label]
        cogs_col = cogs[label]
        margin[label]     = rev_col - cogs_col
        margin_pct[label] = ((rev_col - cogs_col) / rev_col * 100.0) if rev_col else 0.0

        effective_margin_pct = margin_pct[label] if rev_col > 0 else default_margin_pct
        target_net[label] = (effective_margin_pct / 100.0) * col_target_rev

    # ── Build product rows ──
    products = []
    for ig, cols in products_map.items():
        t = target_index.get(ig, {"target_units": 0, "avg_price": 0, "target_rev": 0})
        actuals       = {col: cols[col]["rev"] for col in col_labels}
        units         = {col: cols[col]["qty"] for col in col_labels}
        cell_targets  = product_col_targets.get(ig, {col: 0 for col in col_labels})
        products.append({
            "item_group":     ig,
            "has_target":     ig in target_index,
            "target_units":   t["target_units"],
            "avg_price":      t["avg_price"],
            "target_rev":     t["target_rev"],
            "monthly_target": _flt(t["target_rev"]),
            "actuals":        actuals,
            "units":          units,
            "cell_targets":   cell_targets,
            "row_total":      sum(actuals.values()),
        })

    target_order = list(target_index.keys())
    def sort_key(p):
        if p["has_target"]:
            return (0, target_order.index(p["item_group"]))
        return (1, -p["row_total"])
    products.sort(key=sort_key)

    return {
        "columns":           col_labels,
        "column_dates":      [[c['from_date'], c['to_date']] for c in columns],
        "products":          products,
        "totals":            totals,
        "cogs":              cogs,
        "margin":            margin,
        "margin_pct":        margin_pct,
        "oh":                oh,
        "target_net":        target_net,
        "target_rev_by_col": target_rev_by_col,
        "motley_totals":     motley_totals,
        "tsbc_totals":       tsbc_totals,
        "other_totals":      other_totals,
    }