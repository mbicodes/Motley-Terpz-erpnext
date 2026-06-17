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
    else:
        return None, None


INTERNAL_CUSTOMERS = ('Motley Terpz', 'MT', 'MTPZ')  # legacy fallback only


def _get_excluded_customers():
    """
    Returns a tuple of customer names that must never appear in any dashboard:
      1. Every Company name (exact match — TSBC Ranch, MTM, LA Canna Distro, etc.)
      2. Every Customer flagged is_internal_customer = 1
      3. Every Customer linked to a company via represents_company
    Safe to call per-request — tabCompany is tiny (< 20 rows).
    """
    company_names = frappe.db.sql_list("SELECT name FROM `tabCompany`")
    internal = frappe.db.sql_list("""
        SELECT name FROM `tabCustomer`
        WHERE is_internal_customer = 1
           OR (represents_company IS NOT NULL AND represents_company != '')
    """)
    excluded = set(company_names) | set(internal) | set(INTERNAL_CUSTOMERS)
    return tuple(excluded) if excluded else ('__none__',)

# Tolling actuals come from a specific item, not an item group
TOLLING_ROW_KEY  = "Tolling"
TOLLING_ITEM_CODE = "toll-processing-fee"

# "Other" aggregates BHO (all descendants) — add more groups here as needed
OTHER_ROW_KEY       = "Other"
OTHER_SOURCE_GROUPS = ["BHO"]

# Fixed display order matching the Excel layout (names match exact item group names in ERPNext)
DISPLAY_ORDER = [
    "Packaged goods",
    "Rosins",
    "Bubble Cured",
    TOLLING_ROW_KEY,
    "Static",
    "Gummies",
    "Pre Rolls",
    OTHER_ROW_KEY,
    "Frozen",
]


# ─────────────────────────────────────────────────────────
# Helpers — Item Group hierarchy
# ─────────────────────────────────────────────────────────

def _get_target_detail_fields():
    """Fields to fetch from Target Detail, including the SI flag if it exists."""
    fields = ["item_group", "target_qty", "average_rate", "target_amount"]
    try:
        meta = frappe.get_meta("Target Detail")
        if meta.get_field("sales_invoice_"):
            fields.append("sales_invoice_")
    except Exception:
        pass
    return fields


def _build_descendants_map(parent_item_groups):
    """
    For a list of parent item groups, return:
      child_to_parent: dict mapping every descendant (and the parent itself) -> parent
      all_descendants: flat list of all descendant item group names

    Uses a recursive CTE on parent_item_group so it works even when the Item Group
    nested-set (lft/rgt) is inconsistent (e.g. a child inserted outside its parent's range).
    """
    child_to_parent = {}
    all_descendants = []

    if not parent_item_groups:
        return child_to_parent, all_descendants

    for parent_name in parent_item_groups:
        descs = frappe.db.sql_list("""
            WITH RECURSIVE ig_tree AS (
                SELECT name
                FROM `tabItem Group`
                WHERE name = %(parent)s
                UNION ALL
                SELECT ig.name
                FROM `tabItem Group` ig
                JOIN ig_tree ON ig.parent_item_group = ig_tree.name
            )
            SELECT name FROM ig_tree
        """, {'parent': parent_name})
        for c in descs:
            child_to_parent[c] = parent_name
            all_descendants.append(c)

    return child_to_parent, all_descendants


# ─────────────────────────────────────────────────────────
# Sales Invoices
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_by_period(period='monthly'):
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)

    from_date, to_date = _get_date_range(period)

    excluded = _get_excluded_customers()
    conditions = 'si.docstatus = 1 AND si.customer NOT IN %(internal_customers)s'
    args = {'internal_customers': excluded}

    if from_date:
        conditions += ' AND si.posting_date >= %(from_date)s'
        args['from_date'] = from_date
    if to_date:
        conditions += ' AND si.posting_date <= %(to_date)s'
        args['to_date'] = to_date

    invoices = frappe.db.sql(f"""
        SELECT
            si.name, si.customer, si.customer_name, si.company,
            si.posting_date, si.due_date, si.grand_total,
            si.outstanding_amount, si.status, si.currency,
            st.sales_person     AS sales_person,
            st.commission_rate  AS commission_rate,
            st.incentives       AS sales_incentive
        FROM `tabSales Invoice` si
        LEFT JOIN `tabSales Team` st
            ON st.parent     = si.name
           AND st.parenttype = 'Sales Invoice'
           AND st.idx        = 1
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
# AR / AP / Batches / Timesheets / Samples / Bank
# (unchanged — keeping them as-is)
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ar_summary():
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)
    result = frappe.db.sql("""
        SELECT COUNT(name) AS total_invoices,
               SUM(grand_total) AS total_billed,
               SUM(outstanding_amount) AS total_outstanding,
               SUM(grand_total - outstanding_amount) AS total_collected,
               COUNT(DISTINCT customer) AS total_clients
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
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
        SELECT si.name AS invoice_id, si.customer AS client, si.customer_name AS client_name,
               si.company, si.posting_date, si.due_date, si.grand_total,
               si.outstanding_amount, si.status, si.currency
        FROM `tabSales Invoice` si
        WHERE {conditions}
        ORDER BY si.due_date ASC
    """, args, as_dict=True)
    return rows


@frappe.whitelist()
def get_ar_by_client():
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)
    return frappe.db.sql("""
        SELECT si.customer AS client, si.customer_name AS client_name,
               COUNT(si.name) AS invoice_count,
               SUM(si.grand_total) AS total_billed,
               SUM(si.outstanding_amount) AS total_outstanding,
               SUM(si.grand_total - si.outstanding_amount) AS total_paid,
               MAX(si.due_date) AS latest_due_date,
               MIN(si.due_date) AS oldest_due_date
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 AND si.outstanding_amount > 0
        GROUP BY si.customer, si.customer_name
        ORDER BY total_outstanding DESC
    """, as_dict=True)


@frappe.whitelist()
def get_ap_summary():
    if not frappe.has_permission('Purchase Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)
    result = frappe.db.sql("""
        SELECT COUNT(name) AS total_bills,
               SUM(grand_total) AS total_billed,
               SUM(outstanding_amount) AS total_outstanding
        FROM `tabPurchase Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
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
    return frappe.db.sql(f"""
        SELECT pi.name AS invoice_id, pi.supplier AS client, pi.supplier_name AS client_name,
               pi.company, pi.posting_date, pi.due_date, pi.grand_total,
               pi.outstanding_amount, pi.status, pi.currency
        FROM `tabPurchase Invoice` pi
        WHERE {conditions}
        ORDER BY pi.due_date ASC
    """, args, as_dict=True)


@frappe.whitelist()
def get_ap_by_supplier():
    if not frappe.has_permission('Purchase Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)
    return frappe.db.sql("""
        SELECT pi.supplier AS client, pi.supplier_name AS client_name,
               COUNT(pi.name) AS invoice_count,
               SUM(pi.grand_total) AS total_billed,
               SUM(pi.outstanding_amount) AS total_outstanding,
               SUM(pi.grand_total - pi.outstanding_amount) AS total_paid,
               MAX(pi.due_date) AS latest_due_date,
               MIN(pi.due_date) AS oldest_due_date
        FROM `tabPurchase Invoice` pi
        WHERE pi.docstatus = 1 AND pi.outstanding_amount > 0
        GROUP BY pi.supplier, pi.supplier_name
        ORDER BY total_outstanding DESC
    """, as_dict=True)


@frappe.whitelist()
def get_batches_in_production():
    if not frappe.has_permission('Project', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)
    return frappe.db.sql("""
        SELECT p.name, p.project_name, p.company, p.status,
               p.expected_start_date, p.expected_end_date, p.percent_complete
        FROM `tabProject` p
        WHERE p.status NOT IN ('Completed', 'Cancelled')
        ORDER BY p.expected_start_date ASC
    """, as_dict=True)


@frappe.whitelist()
def create_purchase_request(qty, uom, schedule_date, why_need=None, type_val=None):
    doc = frappe.new_doc('Material Request')
    doc.material_request_type = 'Purchase'
    doc.transaction_date      = frappe.utils.today()
    doc.schedule_date         = schedule_date
    doc.company               = 'Motley Terpz'
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=False)
    frappe.db.commit()
    return doc.name


@frappe.whitelist()
def get_timesheets_by_period(period='monthly'):
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
    return frappe.db.sql(f"""
        SELECT ts.name, ts.employee, ts.employee_name, ts.company,
               ts.start_date, ts.end_date, ts.total_hours,
               ts.total_billable_hours, ts.docstatus
        FROM `tabTimesheet` ts
        WHERE {conditions}
        ORDER BY ts.start_date DESC, ts.employee_name ASC
    """, args, as_dict=True)


# ── Sample Giveaway / Legacy aliases / Bank payments unchanged ──

@frappe.whitelist()
def get_sample_giveaway(period='monthly', month_offset=0):
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)
    month_offset = cint(month_offset)
    if period == 'monthly' and month_offset != 0:
        ref_date  = add_months(nowdate(), month_offset)
        from_date = get_first_day(ref_date)
        to_date   = get_last_day(ref_date)
        label = datetime.date(int(str(from_date)[:4]), int(str(from_date)[5:7]), 1).strftime('%B %Y')
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
        SELECT si.posting_date AS given_on, si.customer_name AS given_to,
               si.customer AS customer_id, si.name AS invoice_id, si.company,
               sii.item_code, sii.item_name, sii.item_group, sii.qty, sii.uom
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE {conditions}
        ORDER BY si.posting_date DESC, si.customer_name ASC, sii.item_name ASC
    """, args, as_dict=True)
    total_qty = sum(float(r.qty or 0) for r in rows)
    return {
        'period': period, 'month_offset': month_offset,
        'from_date': str(from_date) if from_date else None,
        'to_date':   str(to_date) if to_date else None,
        'label': label, 'total_qty': total_qty,
        'count': len(rows), 'rows': rows,
    }


@frappe.whitelist()
def get_sample_by_client(period='monthly', month_offset=0):
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
    return frappe.db.sql(f"""
        SELECT si.customer_name AS client_name, si.customer AS client_id,
               COUNT(sii.name) AS line_count,
               COUNT(DISTINCT sii.item_code) AS item_count,
               COUNT(DISTINCT si.name) AS invoice_count,
               SUM(sii.qty) AS total_qty
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE {conditions}
        GROUP BY si.customer, si.customer_name
        ORDER BY total_qty DESC
    """, args, as_dict=True)


@frappe.whitelist()
def get_sample_product_by_month(num_months=6):
    if not frappe.has_permission('Sales Invoice', 'read'):
        frappe.throw('Not permitted', frappe.PermissionError)
    num_months = min(cint(num_months) or 6, 24)
    today = nowdate()
    month_labels, month_ranges = [], []
    for i in range(num_months):
        ref = add_months(today, -i)
        fd  = get_first_day(ref)
        ld  = get_last_day(ref)
        dt  = datetime.date(int(str(fd)[:4]), int(str(fd)[5:7]), 1)
        lbl = dt.strftime('%b %Y')
        month_labels.append(lbl)
        month_ranges.append((str(fd), str(ld), lbl))
    from_date = month_ranges[-1][0]
    to_date   = month_ranges[0][1]
    rows = frappe.db.sql("""
        SELECT sii.item_name, sii.item_code, sii.item_group, sii.qty, si.posting_date
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE si.docstatus = 1 AND si.custom_order_type = 'Samples'
          AND si.posting_date >= %(from_date)s AND si.posting_date <= %(to_date)s
        ORDER BY sii.item_name ASC
    """, {'from_date': from_date, 'to_date': to_date}, as_dict=True)
    product_map = {}
    for r in rows:
        key = r.item_name or r.item_code
        if key not in product_map:
            product_map[key] = {
                'item_name': r.item_name, 'item_code': r.item_code,
                'item_group': r.item_group, 'months': {}, 'total_qty': 0.0,
            }
        pd = str(r.posting_date)
        dt = datetime.date(int(pd[:4]), int(pd[5:7]), 1)
        lbl = dt.strftime('%b %Y')
        qty = float(r.qty or 0)
        product_map[key]['months'][lbl] = product_map[key]['months'].get(lbl, 0) + qty
        product_map[key]['total_qty'] += qty
    products = sorted(product_map.values(), key=lambda x: -x['total_qty'])
    return {'months': month_labels, 'products': products,
            'from_date': from_date, 'to_date': to_date}


@frappe.whitelist()
def get_sales_this_month():
    return get_sales_by_period(period='monthly')


@frappe.whitelist()
def get_timesheets_this_month():
    return get_timesheets_by_period(period='monthly')


@frappe.whitelist()
def get_bank_payments_received(from_date, to_date, payment_type='Bank'):
    if payment_type not in ('Bank', 'Cash'):
        payment_type = 'Bank'
    return frappe.db.sql("""
        SELECT bank_gle.posting_date, bank_gle.voucher_no, bank_gle.voucher_type,
               bank_gle.account AS bank_account, bank_gle.debit AS amount,
               bank_gle.company, bank_gle.remarks,
               cust_gle.party, cust_gle.against AS party_name,
               COALESCE(cust.customer_name, cust_gle.party) AS customer_name
        FROM `tabGL Entry` bank_gle
        INNER JOIN `tabAccount` acc
            ON acc.name = bank_gle.account AND acc.account_type = %(account_type)s
        INNER JOIN `tabGL Entry` cust_gle
            ON cust_gle.voucher_no = bank_gle.voucher_no
           AND cust_gle.party_type = 'Customer'
           AND cust_gle.party != '' AND cust_gle.is_cancelled = 0
        LEFT JOIN `tabCustomer` cust ON cust.name = cust_gle.party
        WHERE bank_gle.posting_date >= %(from_date)s
          AND bank_gle.posting_date <= %(to_date)s
          AND bank_gle.debit > 0 AND bank_gle.is_cancelled = 0
        ORDER BY bank_gle.posting_date ASC, customer_name ASC
    """, {'from_date': from_date, 'to_date': to_date, 'account_type': payment_type}, as_dict=True)


# ─────────────────────────────────────────────────────────
# Sales Dashboard
# ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_territories():
    return frappe.db.sql("""
        SELECT DISTINCT t.name
        FROM `tabTerritory` t
        INNER JOIN `tabTarget Detail` td
            ON td.parent = t.name AND td.parenttype = 'Territory'
        WHERE td.target_qty > 0 OR td.target_amount > 0
        ORDER BY t.name
    """, as_dict=True)


@frappe.whitelist()
def get_sales_dashboard_data(period='weekly', territory=None, company=None):
    """
    KPI summary: pro-rated targets vs actuals.
    Now uses Item Group descendants rollup (parents → children) and respects
    Target Detail.sales_invoice_ flag.
    """
    import datetime as dt_mod
    from frappe.utils import getdate, get_first_day, flt as _flt

    today = getdate(nowdate())

    # Date window
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
        first_of_this_month = getdate(str(get_first_day(today)))
        last_month_end      = first_of_this_month - dt_mod.timedelta(days=1)
        last_month_start    = getdate(str(get_first_day(last_month_end)))
        from_date, to_date  = str(last_month_start), str(last_month_end)
        window_days         = (last_month_end - last_month_start).days + 1
        period_label        = 'Last Month'
    else:
        month_start = getdate(str(get_first_day(today)))
        from_date, to_date = str(month_start), str(today)
        window_days = (today - month_start).days + 1
        period_label = 'This Month'

    # Resolve fiscal year
    target_fy = None
    fy_days = 365
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
                JOIN `tabTarget Detail` td
                  ON td.fiscal_year = fy.name
                 AND td.parent = %(terr)s AND td.parenttype = 'Territory'
                ORDER BY fy.year_start_date DESC LIMIT 1
            """, {'terr': territory}, as_dict=True)
            if fy_latest:
                target_fy = fy_latest[0]
        if target_fy:
            fy_days = (getdate(str(target_fy.year_end_date)) -
                       getdate(str(target_fy.year_start_date))).days + 1

    # Targets — fetch ALL fiscal years so every configured row always appears.
    # Current-FY rows take priority when deduplicating by item_group.
    targets = []
    si_parent_groups = []
    if territory:
        all_td = frappe.get_all(
            "Target Detail",
            filters={"parent": territory, "parenttype": "Territory"},
            fields=_get_target_detail_fields() + ["fiscal_year"],
            order_by="fiscal_year desc, idx asc",
        )
        seen_ig = {}
        for t in all_td:
            ig = t.item_group
            if ig not in seen_ig:
                seen_ig[ig] = t
            elif target_fy and t.fiscal_year == target_fy.name:
                seen_ig[ig] = t
        rows = sorted(seen_ig.values(),
                      key=lambda t: (DISPLAY_ORDER.index(t.item_group)
                                     if t.item_group in DISPLAY_ORDER else 999))
        for t in rows:
            from_si = bool(t.get('sales_invoice_', 1))
            t_qty   = _flt(t.get('target_qty'))
            avg_rate = _flt(t.get('average_rate'))
            t_amount = _flt(t.get('target_amount')) or (t_qty * avg_rate)
            p_qty = (t_qty / fy_days) * window_days if fy_days else 0
            p_rev = (t_amount / fy_days) * window_days if fy_days else 0
            targets.append({
                "item_group":        t.item_group,
                "from_sales_invoice": from_si,
                "avg_rate":          avg_rate,
                "annual_target_qty": t_qty,
                "annual_target_rev": t_amount,
                "period_target_qty": p_qty,
                "period_target_rev": p_rev,
            })
            if from_si:
                si_parent_groups.append(t.item_group)

    # Build child→parent map for SI-tracked targets
    child_to_parent, all_si_item_groups = _build_descendants_map(si_parent_groups)

    # Actuals — only for SI targets, scoped by descendant item groups
    actuals_map = {}
    if all_si_item_groups:
        actuals_raw = frappe.db.sql("""
            SELECT
                COALESCE(i.item_group, 'Other') AS item_group,
                SUM(sii.qty) AS total_qty,
                SUM(sii.base_net_amount) AS total_rev
            FROM `tabSales Invoice Item` sii
            JOIN  `tabSales Invoice` si ON si.name = sii.parent
            LEFT JOIN `tabItem` i       ON i.name = sii.item_code
            WHERE si.docstatus = 1
              AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND si.is_return = 0
              AND si.customer NOT IN %(internal_customers)s
              AND i.item_group IN %(ig)s
            GROUP BY i.item_group
        """, {
            'from_date': from_date, 'to_date': to_date,
            'internal_customers': _get_excluded_customers(),
            'ig': tuple(all_si_item_groups),
        }, as_dict=True)

        for r in actuals_raw:
            raw_ig = r.item_group or 'Other'
            parent_ig = child_to_parent.get(raw_ig, raw_ig)
            if parent_ig not in actuals_map:
                actuals_map[parent_ig] = {'qty': 0.0, 'rev': 0.0}
            actuals_map[parent_ig]['qty'] += _flt(r.total_qty)
            actuals_map[parent_ig]['rev'] += _flt(r.total_rev)

    # Build product rows
    products, total_target, total_actual = [], 0.0, 0.0
    for t in targets:
        ig = t['item_group']
        actual_qty = actuals_map.get(ig, {}).get('qty', 0.0)
        actual_rev = actuals_map.get(ig, {}).get('rev', 0.0)
        p_target   = t['period_target_rev']
        variance_amt = actual_rev - p_target
        variance_pct = (variance_amt / p_target * 100.0) if p_target else 0.0
        progress_pct = min((actual_rev / p_target * 100.0) if p_target else 0.0, 150.0)
        products.append({
            "item_group":        ig,
            "from_sales_invoice": t['from_sales_invoice'],
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

    total_variance = total_actual - total_target
    total_variance_pct = (total_variance / total_target * 100.0) if total_target else 0.0
    pending_count = frappe.db.count("Sales Invoice", {"docstatus": 0})

    return {
        "period": period, "period_label": period_label,
        "from_date": from_date, "to_date": to_date,
        "window_days": window_days,
        "fiscal_year": target_fy.name if target_fy else None,
        "fiscal_year_days": fy_days,
        "period_fraction": (window_days / float(fy_days)) if fy_days else 0,
        "territory": territory, "products": products,
        "total_target_rev": total_target, "total_actual_rev": total_actual,
        "total_variance": total_variance, "total_variance_pct": total_variance_pct,
        "on_target": total_actual >= total_target,
        "pending_invoices": pending_count,
    }


LEGACY_AR_CUTOFF    = "2026-06-01"   # pre-June 1 = Legacy AR; June 1 onwards = New AR
LEGACY_AR_TARGET    = 2_000_000.0
LEGACY_MONTHLY_PACE = 400_000.0


@frappe.whitelist()
def get_ar_matrix():
    """
    AR tracking matrix for the sales dashboard.
    Rows: Total AR | Legacy AR (pre-Jun 1) | New AR (Jun 1+)
    Columns: monthly period blocks.
    Values: amount collected from each AR category within each period.
    """
    import datetime as dt_mod
    from frappe.utils import getdate, get_first_day, get_last_day, flt as _flt

    today = getdate(nowdate())
    excluded = _get_excluded_customers()

    # ── Current AR balance snapshots ──────────────────────────────────────────
    def _bal(extra_where, args=None):
        rows = frappe.db.sql(f"""
            SELECT COALESCE(SUM(si.outstanding_amount), 0) AS bal
            FROM `tabSales Invoice` si
            LEFT JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1
              AND si.outstanding_amount > 0.01
              AND si.customer NOT IN %(exc)s
              AND COALESCE(c.is_internal_customer, 0) = 0
              AND (c.represents_company IS NULL OR c.represents_company = '')
              AND si.customer NOT IN (SELECT name FROM `tabCompany`)
              {extra_where}
        """, {"exc": excluded, **(args or {})}, as_dict=True)
        return _flt(rows[0].bal) if rows else 0.0

    total_ar  = _bal("")
    legacy_ar = _bal("AND si.posting_date < %(cutoff)s",  {"cutoff": LEGACY_AR_CUTOFF})
    new_ar    = _bal("AND si.posting_date >= %(cutoff)s", {"cutoff": LEGACY_AR_CUTOFF})

    # ── Build period columns — monthly only for AR tracking ───────────────────
    monthly_columns = []
    for m in range(1, today.month + 1):
        mstart = today.replace(month=m, day=1)
        mend_dt = getdate(str(get_last_day(mstart)))
        mend = min(mend_dt, today)
        monthly_columns.append({
            "label": mstart.strftime('%b'),
            "from_date": str(mstart), "to_date": str(mend),
        })

    # AR matrix always uses full months only — no weekly sub-blocks
    all_columns = monthly_columns

    min_date = min(c["from_date"] for c in all_columns) if all_columns else str(today)
    max_date = max(c["to_date"]   for c in all_columns) if all_columns else str(today)

    # ── Collections per period via Payment Entry Reference ────────────────────
    pay_rows = frappe.db.sql("""
        SELECT
            pe.posting_date,
            per.allocated_amount,
            si.posting_date   AS invoice_date,
            si.due_date       AS invoice_due
        FROM `tabPayment Entry Reference` per
        JOIN `tabPayment Entry` pe  ON pe.name  = per.parent
        JOIN `tabSales Invoice` si  ON si.name  = per.reference_name
        LEFT JOIN `tabCustomer` c   ON c.name   = si.customer
        WHERE pe.docstatus = 1
          AND pe.payment_type = 'Receive'
          AND pe.posting_date BETWEEN %(s)s AND %(e)s
          AND si.customer NOT IN %(exc)s
          AND COALESCE(c.is_internal_customer, 0) = 0
          AND (c.represents_company IS NULL OR c.represents_company = '')
          AND si.customer NOT IN (SELECT name FROM `tabCompany`)
    """, {"s": min_date, "e": max_date, "exc": excluded}, as_dict=True)

    # Bucket into period columns
    cutoff_date = getdate(LEGACY_AR_CUTOFF)

    col_labels = [c["label"] for c in all_columns]
    col_ranges = [(c["label"], getdate(c["from_date"]), getdate(c["to_date"])) for c in all_columns]

    totals  = {l: 0.0 for l in col_labels}
    legacy  = {l: 0.0 for l in col_labels}
    new_ar_coll = {l: 0.0 for l in col_labels}

    for r in pay_rows:
        if not r.posting_date:
            continue
        pd  = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        amt = _flt(r.allocated_amount)
        inv_date = getdate(str(r.invoice_date)) if r.invoice_date else today

        is_legacy = inv_date < cutoff_date

        for label, fd, td in col_ranges:
            if fd <= pd <= td:
                totals[label] += amt
                if is_legacy:
                    legacy[label] += amt
                else:
                    new_ar_coll[label] += amt
                break

    # ── Monthly pace target per column (same frac logic as revenue matrix) ────
    pace_by_col = {}
    for c in all_columns:
        fd = getdate(c["from_date"]); td = getdate(c["to_date"])
        col_days = (td - fd).days + 1
        month_days = (getdate(str(get_last_day(fd))) - getdate(str(get_first_day(fd)))).days + 1
        frac = col_days / float(month_days)
        pace_by_col[c["label"]] = LEGACY_MONTHLY_PACE * frac

    n = len(col_labels)
    def _avg(d): return sum(d.values()) / n if n else 0.0

    return {
        "columns": col_labels,
        "column_dates": [[c["from_date"], c["to_date"]] for c in all_columns],
        "balances": {
            "total":  total_ar,
            "legacy": legacy_ar,
            "new_ar": new_ar,
        },
        "collected": {
            "total":  totals,
            "legacy": legacy,
            "new_ar": new_ar_coll,
        },
        "pace_by_col":          pace_by_col,
        "legacy_monthly_target": LEGACY_MONTHLY_PACE,
        "legacy_ar_target":      LEGACY_AR_TARGET,
        "avg": {
            "total":  _avg(totals),
            "legacy": _avg(legacy),
            "new_ar": _avg(new_ar_coll),
        },
    }


@frappe.whitelist()
def get_dashboard_inventory(company=None):
    return frappe.db.sql("""
        SELECT COALESCE(i.item_group, 'Other') AS item_group,
               SUM(b.actual_qty) AS qty_on_hand,
               SUM(b.actual_qty * b.valuation_rate) AS stock_value
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE b.actual_qty > 0
        GROUP BY i.item_group
        HAVING qty_on_hand > 0
        ORDER BY stock_value DESC
    """, as_dict=True)


def _calendar_blocks_before(date, count):
    """
    Return `count` most-recent fixed-7-day calendar blocks ending at or before `date`.
    Blocks are defined as:  days 1-7 (week 1), 8-14 (week 2), 15-21 (week 3), 22-end (week 4).
    The last block of any month stretches to the last day of that month so all revenue is captured.
    """
    import calendar as _cal
    import datetime as _dt

    STARTS = [1, 8, 15, 22]

    def _bsd(day):
        for s in reversed(STARTS):
            if day >= s:
                return s
        return 1

    def _bed(bsd, year, month):
        if bsd < 22:
            return bsd + 6
        return _cal.monthrange(year, month)[1]

    blocks = []
    d = date
    for _ in range(count):
        bsd = _bsd(d.day)
        bed = _bed(bsd, d.year, d.month)
        b_start    = d.replace(day=bsd)
        b_end_full = d.replace(day=bed)
        b_end      = min(b_end_full, date)
        wk_num     = STARTS.index(bsd) + 1
        blocks.insert(0, {
            "label":     b_start.strftime('%B') + ' ' + str(wk_num),
            "from_date": str(b_start),
            "to_date":   str(b_end),
            "is_full":   b_end == b_end_full,
            "col_type":  "weekly",
        })
        d = b_start - _dt.timedelta(days=1)

    return blocks


@frappe.whitelist()
def get_sales_matrix(territory=None):
    """
    Monthly/Weekly/Daily revenue matrices.
    Targets live on parent item groups; actuals live on child item groups.
    Rolls up via Item Group nested set. Respects Target Detail.sales_invoice_:
    targets with sales_invoice_ = 0 still appear as rows but pull no SI actuals
    (other data sources to be wired up later).
    """
    import datetime as dt_mod
    from frappe.utils import getdate, get_first_day, get_last_day, flt as _flt

    today = getdate(nowdate())

    # Settings
    try:
        settings = frappe.get_single("Sales Dashboard Settings")
        monthly_oh = _flt(settings.monthly_overhead) or 35000.0
        default_margin_pct = _flt(settings.default_margin_pct) or 40.0
    except Exception:
        monthly_oh = 35000.0
        default_margin_pct = 40.0

    # Resolve fiscal year
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

    # Targets — fetch ALL fiscal years so every configured row always appears.
    # Current-FY rows take priority when deduplicating by item_group.
    targets_raw = []
    if territory:
        all_td = frappe.get_all(
            "Target Detail",
            filters={"parent": territory, "parenttype": "Territory"},
            fields=_get_target_detail_fields() + ["fiscal_year"],
            order_by="fiscal_year desc, idx asc",
        )
        seen_ig = {}
        for t in all_td:
            ig = t.item_group
            if ig not in seen_ig:
                seen_ig[ig] = t
            elif target_fy and t.fiscal_year == target_fy.name:
                seen_ig[ig] = t
        # Re-sort by DISPLAY_ORDER then by original idx to preserve Territory row order
        def _td_sort(t):
            ig = t.item_group
            try:
                return (0, DISPLAY_ORDER.index(ig))
            except ValueError:
                return (1, t.get("idx") or 999)
        targets_raw = sorted(seen_ig.values(), key=_td_sort)

    target_index = {}
    si_parent_groups = []
    for t in targets_raw:
        from_si = bool(t.get('sales_invoice_', 1))
        t_qty  = _flt(t.target_qty)
        avg_rt = _flt(t.average_rate)
        t_amt  = _flt(t.target_amount) or (t_qty * avg_rt)
        target_index[t.item_group] = {
            "target_units":       t_qty,
            "avg_price":          avg_rt,
            "target_rev":         t_amt,
            "from_sales_invoice": from_si,
        }
        if from_si:
            si_parent_groups.append(t.item_group)

    # Ensure Tolling + Other always appear as rows even if not in Territory targets
    if TOLLING_ROW_KEY not in target_index:
        target_index[TOLLING_ROW_KEY] = {
            "target_units": 4000,
            "avg_price": 35,
            "target_rev": 4000 * 35,   # 140,000 monthly
            "from_sales_invoice": True,
    }
    if OTHER_ROW_KEY not in target_index:
        target_index[OTHER_ROW_KEY] = {
            "target_units": 0, "avg_price": 0,
            "target_rev": 0, "from_sales_invoice": True,
        }

    # Build excluded-customer list once for all queries in this request
    excluded_customers = _get_excluded_customers()

    # Tolling actuals come from item_code, not item_group — exclude from group lookup
    si_parent_groups_adj = [g for g in si_parent_groups if g != TOLLING_ROW_KEY]

    # BHO + Distillate feed into "Other" — add them to the group lookup
    for og in OTHER_SOURCE_GROUPS:
        if og not in si_parent_groups_adj:
            si_parent_groups_adj.append(og)

    # Build child→parent rollup map
    child_to_parent, all_si_item_groups = _build_descendants_map(si_parent_groups_adj)

    # Override: every BHO/Distillate descendant maps to "Other"
    for og in OTHER_SOURCE_GROUPS:
        _, og_descs = _build_descendants_map([og])
        for d in og_descs:
            child_to_parent[d] = OTHER_ROW_KEY

    # Build columns
    # Monthly: one col per month YTD + last 4 fixed calendar-week blocks
    monthly_columns = []
    for m in range(1, today.month + 1):
        mstart = today.replace(month=m, day=1)
        mend_dt = getdate(str(get_last_day(mstart)))
        mend = min(mend_dt, today)
        monthly_columns.append({
            "label": mstart.strftime('%b'),
            "from_date": str(mstart), "to_date": str(mend),
            "is_full": mend == mend_dt,
            "col_type": "monthly",
        })
    # 4 most-recent fixed 7-day calendar blocks (days 1-7, 8-14, 15-21, 22-end)
    for blk in _calendar_blocks_before(today, 4):
        monthly_columns.append(blk)

    # Weekly: last 8 fixed calendar-week blocks
    weekly_columns = _calendar_blocks_before(today, 8)

    # Daily: Mon–Fri of the current calendar week (÷20 working days/month)
    daily_columns = []
    week_monday = today - dt_mod.timedelta(days=today.weekday())
    for d in range(5):
        day = week_monday + dt_mod.timedelta(days=d)
        if day > today:
            break
        daily_columns.append({
            "label": day.strftime('%a'),
            "from_date": str(day), "to_date": str(day),
            "is_full": True,
            "col_type": "daily",
        })

    all_ranges = []
    for c in monthly_columns: all_ranges.append((c['from_date'], c['to_date']))
    for c in weekly_columns:  all_ranges.append((c['from_date'], c['to_date']))
    for c in daily_columns:   all_ranges.append((c['from_date'], c['to_date']))

    if not all_ranges:
        return {
            "monthly": _empty_matrix(monthly_columns, target_index, DISPLAY_ORDER),
            "weekly":  _empty_matrix(weekly_columns,  target_index, DISPLAY_ORDER),
            "daily":   _empty_matrix(daily_columns,   target_index, DISPLAY_ORDER),
            "fiscal_year": target_fy.name if target_fy else None,
            "territory": territory,
            "monthly_oh": monthly_oh,
            "default_margin_pct": default_margin_pct,
        }

    min_date = min(r[0] for r in all_ranges)
    max_date = max(r[1] for r in all_ranges)

    # Queries — item-group-based actuals (BHO/Distillate now included via all_si_item_groups)
    if all_si_item_groups:
        rev_rows = frappe.db.sql("""
            SELECT si.posting_date, si.company,
                   COALESCE(i.item_group, 'Other') AS item_group,
                   SUM(sii.qty) AS qty,
                   SUM(sii.base_net_amount) AS rev
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si  ON si.name = sii.parent
            LEFT JOIN `tabItem` i       ON i.name = sii.item_code
            WHERE si.docstatus = 1 AND si.is_return = 0
                AND si.posting_date BETWEEN %(s)s AND %(e)s
                AND si.customer NOT IN %(ic)s
                AND i.item_group IN %(ig)s
            GROUP BY si.posting_date, si.company, i.item_group
        """, {'s': min_date, 'e': max_date,
              'ic': excluded_customers, 'ig': tuple(all_si_item_groups)}, as_dict=True)

        cogs_rows = frappe.db.sql("""
            SELECT sle.posting_date,
                   ABS(SUM(sle.stock_value_difference)) AS cogs
            FROM `tabStock Ledger Entry` sle
            JOIN `tabSales Invoice` si ON si.name = sle.voucher_no
            JOIN `tabItem` i           ON i.name = sle.item_code
            WHERE sle.voucher_type = 'Sales Invoice' AND sle.is_cancelled = 0
              AND sle.posting_date BETWEEN %(s)s AND %(e)s
              AND si.docstatus = 1 AND si.is_return = 0
              AND si.customer NOT IN %(ic)s
              AND i.item_group IN %(ig)s
            GROUP BY sle.posting_date
        """, {'s': min_date, 'e': max_date,
              'ic': excluded_customers, 'ig': tuple(all_si_item_groups)}, as_dict=True)

        company_rev_rows = frappe.db.sql("""
            SELECT si.posting_date, si.company,
                   SUM(sii.base_net_amount) AS rev
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            JOIN `tabItem` i           ON i.name = sii.item_code
            WHERE si.docstatus = 1 AND si.is_return = 0
              AND si.posting_date BETWEEN %(s)s AND %(e)s
              AND si.customer NOT IN %(ic)s
              AND (i.item_group IN %(ig)s OR sii.item_code = %(toll)s)
            GROUP BY si.posting_date, si.company
        """, {'s': min_date, 'e': max_date,
              'ic': excluded_customers, 'ig': tuple(all_si_item_groups),
              'toll': TOLLING_ITEM_CODE}, as_dict=True)
    else:
        rev_rows, cogs_rows, company_rev_rows = [], [], []

    # All-companies, all item groups — used to build the company_ig_map (company-wise display)
    all_company_ig_rows = frappe.db.sql("""
        SELECT si.posting_date, si.company,
               COALESCE(i.item_group, 'Other') AS item_group,
               SUM(sii.qty) AS qty,
               SUM(sii.base_net_amount) AS rev
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabItem` i ON i.name = sii.item_code
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND si.posting_date BETWEEN %(s)s AND %(e)s
          AND si.customer NOT IN %(ic)s
        GROUP BY si.posting_date, si.company, i.item_group
    """, {'s': min_date, 'e': max_date, 'ic': excluded_customers}, as_dict=True) if min_date and max_date else []

    # MTM + LA Canna: all items, no item-group filter (separate companies)
    mtm_lacanna_rows = frappe.db.sql("""
        SELECT si.posting_date, si.company,
               SUM(sii.base_net_amount) AS rev
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND si.posting_date BETWEEN %(s)s AND %(e)s
          AND si.company IN ('Master Touch Manufacturing', 'LA Canna Distro')
        GROUP BY si.posting_date, si.company
    """, {'s': min_date, 'e': max_date}, as_dict=True) if min_date and max_date else []

    # Tolling: actuals by specific item_code (toll-processing-fee), not item_group
    toll_rows = frappe.db.sql("""
        SELECT si.posting_date,
               %(toll_key)s AS item_group,
               SUM(sii.qty)             AS qty,
               SUM(sii.base_net_amount) AS rev
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND si.posting_date BETWEEN %(s)s AND %(e)s
          AND si.customer NOT IN %(ic)s
          AND sii.item_code = %(toll)s
        GROUP BY si.posting_date
    """, {'s': min_date, 'e': max_date,
          'ic': excluded_customers,
          'toll': TOLLING_ITEM_CODE,
          'toll_key': TOLLING_ROW_KEY}, as_dict=True)

    rev_rows = list(rev_rows) + list(toll_rows)

    # Build month cols and rolling-week sub-cols in separate passes so they don't
    # steal each other's rows (month dates overlap with the weekly sub-cols).
    _month_only = [c for c in monthly_columns if c.get('col_type') == 'monthly']
    _week_subs  = [c for c in monthly_columns if c.get('col_type') == 'weekly']
    _m1 = _build_matrix(_month_only, target_index, rev_rows, cogs_rows,
                        company_rev_rows, monthly_oh, default_margin_pct,
                        'monthly', child_to_parent, DISPLAY_ORDER, mtm_lacanna_rows, all_company_ig_rows)
    _m2 = _build_matrix(_week_subs, target_index, rev_rows, cogs_rows,
                        company_rev_rows, monthly_oh, default_margin_pct,
                        'weekly', child_to_parent, DISPLAY_ORDER, mtm_lacanna_rows, all_company_ig_rows)
    monthly = _merge_matrices(_m1, _m2)
    weekly = _build_matrix(weekly_columns, target_index, rev_rows, cogs_rows,
                           company_rev_rows, monthly_oh, default_margin_pct,
                           'weekly', child_to_parent, DISPLAY_ORDER, mtm_lacanna_rows, all_company_ig_rows)
    daily = _build_matrix(daily_columns, target_index, rev_rows, cogs_rows,
                          company_rev_rows, monthly_oh, default_margin_pct,
                          'daily', child_to_parent, DISPLAY_ORDER, mtm_lacanna_rows, all_company_ig_rows)

    return {
        "monthly": monthly, "weekly": weekly, "daily": daily,
        "fiscal_year": target_fy.name if target_fy else None,
        "territory": territory,
        "monthly_oh": monthly_oh,
        "default_margin_pct": default_margin_pct,
    }


def _merge_company_ig(a, b):
    """Merge two company_ig_map dicts (from different column sets)."""
    result = {}
    for co in set(a) | set(b):
        result[co] = {}
        for ig in set(a.get(co, {})) | set(b.get(co, {})):
            a_cols = a.get(co, {}).get(ig, {})
            b_cols = b.get(co, {}).get(ig, {})
            merged = {}
            for col in set(a_cols) | set(b_cols):
                av = a_cols.get(col, {"qty": 0.0, "rev": 0.0})
                bv = b_cols.get(col, {"qty": 0.0, "rev": 0.0})
                merged[col] = {"qty": av["qty"] + bv["qty"], "rev": av["rev"] + bv["rev"]}
            result[co][ig] = merged
    return result


def _merge_matrices(a, b):
    """Concatenate two matrices (different column sets, same products) into one."""
    merged_cols  = a["columns"] + b["columns"]
    merged_dates = a["column_dates"] + b["column_dates"]

    # Merge simple column-keyed dicts
    def _md(*dicts):
        out = {}
        for d in dicts:
            out.update(d)
        return out

    # Merge per-product data
    a_by_ig = {p["item_group"]: p for p in a["products"]}
    b_by_ig = {p["item_group"]: p for p in b["products"]}
    all_igs  = list(dict.fromkeys(
        [p["item_group"] for p in a["products"]] +
        [p["item_group"] for p in b["products"]]
    ))
    merged_products = []
    for ig in all_igs:
        pa = a_by_ig.get(ig, {})
        pb = b_by_ig.get(ig, {})
        base = pa or pb
        merged_products.append({
            "item_group":         ig,
            "has_target":         base.get("has_target", False),
            "from_sales_invoice": base.get("from_sales_invoice", True),
            "target_units":       base.get("target_units", 0),
            "avg_price":          base.get("avg_price", 0),
            "target_rev":         base.get("target_rev", 0),
            "monthly_target":     base.get("monthly_target", 0),
            "actuals":      _md(pa.get("actuals", {}),      pb.get("actuals", {})),
            "units":        _md(pa.get("units", {}),        pb.get("units", {})),
            "cell_targets": _md(pa.get("cell_targets", {}), pb.get("cell_targets", {})),
            "row_total":    pa.get("row_total", 0) + pb.get("row_total", 0),
        })

    all_cols = merged_cols
    n = len(all_cols)
    def _recompute_avg(merged_dict):
        return sum(merged_dict.values()) / n if n else 0.0

    mot     = _md(a["motley_totals"],        b["motley_totals"])
    tsbc    = _md(a["tsbc_totals"],          b["tsbc_totals"])
    mtm     = _md(a.get("mtm_totals", {}),   b.get("mtm_totals", {}))
    lacanna = _md(a.get("la_canna_totals",{}),b.get("la_canna_totals",{}))
    all_cols_merged = merged_cols
    grnd = {c: mot.get(c,0) + tsbc.get(c,0) + mtm.get(c,0) + lacanna.get(c,0)
            for c in all_cols_merged}
    tsbc_tgt = _md(a.get("tsbc_target_by_col", {}), b.get("tsbc_target_by_col", {}))

    return {
        "columns":          merged_cols,
        "column_dates":     merged_dates,
        "products":         merged_products,
        "totals":           _md(a["totals"],         b["totals"]),
        "cogs":             _md(a["cogs"],           b["cogs"]),
        "margin":           _md(a["margin"],         b["margin"]),
        "margin_pct":       _md(a["margin_pct"],     b["margin_pct"]),
        "oh":               _md(a["oh"],             b["oh"]),
        "target_net":       _md(a["target_net"],     b["target_net"]),
        "target_rev_by_col":_md(a["target_rev_by_col"], b["target_rev_by_col"]),
        "motley_totals":    mot,
        "tsbc_totals":      tsbc,
        "mtm_totals":       mtm,
        "la_canna_totals":  lacanna,
        "other_totals":     _md(a["other_totals"],   b["other_totals"]),
        "company_ig_map":   _merge_company_ig(a.get("company_ig_map",{}), b.get("company_ig_map",{})),
        "grand_totals":     grnd,
        "tsbc_target_by_col": tsbc_tgt,
        "avg_motley":      _recompute_avg(mot),
        "avg_tsbc":        _recompute_avg(tsbc),
        "avg_mtm":         _recompute_avg(mtm),
        "avg_la_canna":    _recompute_avg(lacanna),
        "avg_grand":       _recompute_avg(grnd),
        "avg_tsbc_target": _recompute_avg(tsbc_tgt),
        "avg_net":         a.get("avg_net", 0),
        "tsbc_monthly_target": a.get("tsbc_monthly_target", 400000.0),
    }


def _empty_matrix(columns, target_index=None, display_order=None):
    col_labels = [c['label'] for c in columns]
    products = []
    if target_index:
        _order = display_order or list(target_index.keys())
        all_igs = sorted(
            target_index.keys(),
            key=lambda ig: _order.index(ig) if ig in _order else 999,
        )
        for ig in all_igs:
            t = target_index[ig]
            products.append({
                "item_group": ig, "has_target": True,
                "from_sales_invoice": t.get("from_sales_invoice", True),
                "target_units": t.get("target_units", 0),
                "avg_price":    t.get("avg_price", 0),
                "target_rev":   t.get("target_rev", 0),
                "monthly_target": t.get("target_rev", 0),
                "actuals":      {c: 0.0 for c in col_labels},
                "units":        {c: 0.0 for c in col_labels},
                "cell_targets": {c: 0.0 for c in col_labels},
                "row_total":    0.0,
            })
    empty_cols = {c: 0.0 for c in col_labels}
    return {
        "columns": col_labels,
        "column_dates": [[c['from_date'], c['to_date']] for c in columns],
        "products": products, "totals": dict(empty_cols), "cogs": dict(empty_cols),
        "margin": dict(empty_cols), "margin_pct": dict(empty_cols),
        "oh": dict(empty_cols), "target_net": dict(empty_cols),
        "target_rev_by_col": dict(empty_cols),
        "motley_totals": dict(empty_cols), "tsbc_totals": dict(empty_cols),
        "mtm_totals": dict(empty_cols), "la_canna_totals": dict(empty_cols),
        "other_totals": dict(empty_cols), "company_ig_map": {},
        "grand_totals": dict(empty_cols), "tsbc_target_by_col": dict(empty_cols),
        "avg_motley": 0, "avg_tsbc": 0, "avg_mtm": 0, "avg_la_canna": 0,
        "avg_grand": 0, "avg_tsbc_target": 0, "avg_net": 0,
        "tsbc_monthly_target": 400000.0,
    }


def _build_matrix(columns, target_index, rev_rows, cogs_rows,
                  company_rev_rows, monthly_oh, default_margin_pct, granularity,
                  child_to_parent=None, display_order=None, mtm_lacanna_rows=None,
                  all_company_ig_rows=None):
    import datetime as dt_mod
    from frappe.utils import getdate, get_first_day, get_last_day, flt as _flt

    if child_to_parent is None:
        child_to_parent = {}

    col_labels = [c['label'] for c in columns]
    col_ranges = [
        (c['label'], getdate(c['from_date']), getdate(c['to_date']), c.get('col_type', granularity))
        for c in columns
    ]

    products_map = {ig: {col: {"qty": 0.0, "rev": 0.0} for col in col_labels}
                    for ig in target_index}
    totals = {col: 0.0 for col in col_labels}
    cogs   = {col: 0.0 for col in col_labels}

    # Bucket revenue — roll child item group up to parent target
    for r in rev_rows:
        if not r.posting_date:
            continue
        pd = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        raw_ig = r.item_group or 'Other'
        parent_ig = child_to_parent.get(raw_ig, raw_ig)
        for label, fd, td, _ct in col_ranges:
            if fd <= pd <= td:
                if parent_ig in products_map:
                    products_map[parent_ig][label]["qty"] += _flt(r.qty)
                    products_map[parent_ig][label]["rev"] += _flt(r.rev)
                totals[label] += _flt(r.rev)
                break

    # COGS by date (no rollup needed — just date bucketing)
    for r in cogs_rows:
        if not r.posting_date:
            continue
        pd = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        for label, fd, td, _ct in col_ranges:
            if fd <= pd <= td:
                cogs[label] += _flt(r.cogs)
                break

    motley_totals   = {col: 0.0 for col in col_labels}
    tsbc_totals     = {col: 0.0 for col in col_labels}
    mtm_totals      = {col: 0.0 for col in col_labels}
    la_canna_totals = {col: 0.0 for col in col_labels}
    other_totals    = {col: 0.0 for col in col_labels}

    for r in company_rev_rows:
        if not r.posting_date:
            continue
        pd = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        company = (r.company or '').strip().lower()
        for label, fd, td, _ct in col_ranges:
            if fd <= pd <= td:
                if 'motley' in company or 'mtpz' in company:
                    motley_totals[label] += _flt(r.rev)
                elif 'tsbc' in company:
                    tsbc_totals[label] += _flt(r.rev)
                else:
                    other_totals[label] += _flt(r.rev)
                break

    for r in (mtm_lacanna_rows or []):
        if not r.posting_date:
            continue
        pd = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        company = (r.company or '').strip().lower()
        for label, fd, td, _ct in col_ranges:
            if fd <= pd <= td:
                if 'master' in company or 'touch' in company:
                    mtm_totals[label] += _flt(r.rev)
                elif 'canna' in company:
                    la_canna_totals[label] += _flt(r.rev)
                break

    # company_ig_map: {company_name: {item_group: {col: {qty, rev}}}}
    company_ig_map = {}
    for r in (all_company_ig_rows or []):
        if not r.posting_date:
            continue
        pd  = r.posting_date if isinstance(r.posting_date, dt_mod.date) else getdate(str(r.posting_date))
        co  = (r.company or 'Other').strip()
        raw_ig = r.item_group or 'Other'
        ig  = child_to_parent.get(raw_ig, raw_ig) if child_to_parent else raw_ig
        if co not in company_ig_map:
            company_ig_map[co] = {}
        if ig not in company_ig_map[co]:
            company_ig_map[co][ig] = {col: {"qty": 0.0, "rev": 0.0} for col in col_labels}
        for label, fd, td, _ct in col_ranges:
            if fd <= pd <= td:
                company_ig_map[co][ig][label]["qty"] += _flt(r.qty)
                company_ig_map[co][ig][label]["rev"]  += _flt(r.rev)
                break

    # TSBC frozen-sales target: 2,000 lbs/week @ $50/lb = $100K/week = $400K/month
    TSBC_MONTHLY_TARGET = 400_000.0

    # Per-column aggregates — col_frac respects per-column granularity
    margin, margin_pct, oh = {}, {}, {}
    target_net, target_rev_by_col = {}, {}
    tsbc_target_by_col = {}
    product_col_targets = {ig: {} for ig in target_index}

    for label, fd, td, col_type in col_ranges:
        col_days = (td - fd).days + 1
        if col_type == 'monthly':
            month_full_days = (getdate(str(get_last_day(fd))) - getdate(str(get_first_day(fd)))).days + 1
            col_frac = col_days / float(month_full_days)
        elif col_type == 'daily':
            col_frac = col_days / 20.0   # 4 weeks × 5 working days
        else:                            # 'weekly'
            col_frac = col_days / 28.0

        oh[label] = monthly_oh * col_frac
        tsbc_target_by_col[label] = TSBC_MONTHLY_TARGET * col_frac

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

    grand_totals = {col: motley_totals[col] + tsbc_totals[col] + mtm_totals[col] + la_canna_totals[col]
                   for col in col_labels}

    products = []
    for ig, cols in products_map.items():
        t = target_index.get(ig, {"target_units": 0, "avg_price": 0,
                                  "target_rev": 0, "from_sales_invoice": True})
        actuals = {col: cols[col]["rev"] for col in col_labels}
        units   = {col: cols[col]["qty"] for col in col_labels}
        cell_targets = product_col_targets.get(ig, {col: 0 for col in col_labels})
        products.append({
            "item_group":         ig,
            "has_target":         ig in target_index,
            "from_sales_invoice": t.get("from_sales_invoice", True),
            "target_units":       t["target_units"],
            "avg_price":          t["avg_price"],
            "target_rev":         t["target_rev"],
            "monthly_target":     _flt(t["target_rev"]),
            "actuals":            actuals,
            "units":              units,
            "cell_targets":       cell_targets,
            "row_total":          sum(actuals.values()),
        })

    _order = display_order or list(target_index.keys())
    def sort_key(p):
        ig = p["item_group"]
        try:
            return (0, _order.index(ig))
        except ValueError:
            pass
        if p["has_target"]:
            try:
                return (1, list(target_index.keys()).index(ig))
            except ValueError:
                pass
        return (2, -p["row_total"])
    products.sort(key=sort_key)

    n = len(col_labels)
    def _avg(d):
        return sum(d.values()) / n if n else 0.0

    return {
        "columns": col_labels,
        "column_dates": [[c['from_date'], c['to_date']] for c in columns],
        "products": products, "totals": totals, "cogs": cogs,
        "margin": margin, "margin_pct": margin_pct,
        "oh": oh, "target_net": target_net, "target_rev_by_col": target_rev_by_col,
        "motley_totals":    motley_totals,
        "tsbc_totals":      tsbc_totals,
        "mtm_totals":       mtm_totals,
        "la_canna_totals":  la_canna_totals,
        "other_totals":     other_totals,
        "company_ig_map":   company_ig_map,
        "grand_totals":     grand_totals,
        "tsbc_target_by_col": tsbc_target_by_col,
        "avg_motley":     _avg(motley_totals),
        "avg_tsbc":       _avg(tsbc_totals),
        "avg_mtm":        _avg(mtm_totals),
        "avg_la_canna":   _avg(la_canna_totals),
        "avg_grand":      _avg(grand_totals),
        "avg_tsbc_target":_avg(tsbc_target_by_col),
        "avg_net":        _avg(target_net),
        "tsbc_monthly_target": TSBC_MONTHLY_TARGET,
    }


@frappe.whitelist()
def create_dashboard_item_groups():
    """Create standard Sales Dashboard item groups if they don't already exist."""
    GROUPS = [
        "Packaged Goods", "Total Rosin", "Bubble Cured", "Tolling",
        "Static", "Gummies", "Pre-Rolls", "Other", "Frozen",
    ]
    created, skipped = [], []
    for name in GROUPS:
        if frappe.db.exists("Item Group", name):
            skipped.append(name)
            continue
        ig = frappe.get_doc({
            "doctype": "Item Group",
            "item_group_name": name,
            "parent_item_group": "All Item Groups",
            "is_group": 0,
        })
        ig.insert(ignore_permissions=True)
        created.append(name)
    frappe.db.commit()
    return {"created": created, "skipped": skipped}

@frappe.whitelist()
def get_jamie_expense_summary():
    """Returns expense summary for the currently logged-in user (Jamie).
    Filters strictly by owner = session user — no Finance bypass."""
    user = frappe.session.user
    user_filter = "AND owner = {escaped_user}".format(escaped_user=frappe.db.escape(user))

    summary = frappe.db.sql("""
        SELECT
            COALESCE(SUM(CASE WHEN money_out > 0 THEN money_out ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN money_in > 0 THEN money_in ELSE 0 END), 0)  AS total_reimbursed,
            COUNT(*) AS count
        FROM `tabJamie Expense Entry`
        WHERE docstatus = 1 {user_filter}
    """.format(user_filter=user_filter), as_dict=True)

    row = summary[0] if summary else {}
    total_expenses   = float(row.get("total_expenses")   or 0)
    total_reimbursed = float(row.get("total_reimbursed") or 0)
    net_owed = total_expenses - total_reimbursed

    recent = frappe.db.sql("""
        SELECT
            transaction_date AS date,
            CASE WHEN money_out > 0 THEN 'Expense' ELSE 'Reimbursement' END AS direction,
            CASE WHEN money_out > 0 THEN money_out ELSE money_in END AS amount,
            expense_type AS transaction_type,
            transaction_notes AS notes
        FROM `tabJamie Expense Entry`
        WHERE docstatus = 1 {user_filter}
        ORDER BY transaction_date DESC
        LIMIT 20
    """.format(user_filter=user_filter), as_dict=True)

    return {
        "total_expenses":   total_expenses,
        "total_reimbursed": total_reimbursed,
        "net_owed":         net_owed,
        "count":            int(row.get("count") or 0),
        "recent":           recent,
    }


@frappe.whitelist()
def get_matt_sales_matrix(territory=None):
    """
    Like get_sales_matrix but collapses all non-TSBC companies
    (MTM, LA Canna, etc.) into the 'Motley Terpz' bucket in the
    company_ig_map.  Used by the Matt sales target dashboard so that
    item-group totals reflect ALL companies without a company breakdown.
    """
    result = get_sales_matrix(territory=territory)

    MERGE_INTO_MOTLEY = {'Master Touch Manufacturing', 'LA Canna Distro'}

    def _collapse(matrix):
        cig = matrix.get('company_ig_map', {})
        motley = cig.setdefault('Motley Terpz', {})

        for co in list(cig.keys()):
            if co in MERGE_INTO_MOTLEY:
                for ig, col_data in cig.pop(co).items():
                    ig_entry = motley.setdefault(ig, {})
                    for col, vals in col_data.items():
                        bucket = ig_entry.setdefault(col, {'qty': 0.0, 'rev': 0.0})
                        bucket['qty'] += vals.get('qty', 0.0)
                        bucket['rev'] += vals.get('rev', 0.0)

        # Roll MTM + LA Canna totals into motley_totals
        motley_tot = matrix.get('motley_totals', {})
        cols = matrix.get('columns', [])
        for src_key in ('mtm_totals', 'la_canna_totals'):
            for col, v in matrix.get(src_key, {}).items():
                motley_tot[col] = motley_tot.get(col, 0.0) + v
            matrix[src_key] = {c: 0.0 for c in cols}

        matrix['motley_totals'] = motley_tot
        n = len(cols)
        matrix['avg_motley']   = sum(motley_tot.values()) / n if n else 0.0
        matrix['avg_mtm']      = 0.0
        matrix['avg_la_canna'] = 0.0
        return matrix

    result['monthly'] = _collapse(result['monthly'])
    result['weekly']  = _collapse(result['weekly'])
    result['daily']   = _collapse(result['daily'])
    return result
