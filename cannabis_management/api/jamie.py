import frappe
import datetime
from frappe.utils import nowdate, get_first_day, get_last_day, add_days, add_months, cint


def _get_date_range(period):
    today = nowdate()
    if period == 'weekly':
        return add_days(today, -7), today
    elif period == 'monthly':
        return get_first_day(today), get_last_day(today)
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