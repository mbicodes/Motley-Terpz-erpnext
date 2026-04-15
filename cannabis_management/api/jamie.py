import frappe
from frappe.utils import nowdate, get_first_day, get_last_day, add_days


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
# Timesheets
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
# Legacy aliases — keep old callers working
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_this_month():
    return get_sales_by_period(period='monthly')


@frappe.whitelist()
def get_timesheets_this_month():
    return get_timesheets_by_period(period='monthly')