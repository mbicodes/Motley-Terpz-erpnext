import frappe
from frappe.utils import nowdate

MBI_COMPANIES = ('TSBC Ranch', 'Master Touch Manufacturing', 'Motley Terpz')

# 'Fresh Frozen - BHO' is merged into 'Fresh Frozen' at query time
MBI_ITEM_GROUPS = (
    'Fresh Frozen', 'Fresh Frozen - SHO',
    'Primes', 'Subprimes', 'Full Spec', 'Food Grade', 'VRR',
    'LIQUID LIVE RESIN', 'DISTALLATE', 'BHO', 'Rosin', 'Gummies',
    '0.5g O2 Vape', '1g O2 Vapes',
    '1g Jarred Rosin', '3g Jarred Rosin',
)

# Groups that are aliased/merged before aggregation
_IG_ALIAS = {'Fresh Frozen - BHO': 'Fresh Frozen'}

MBI_CONV_GROUPS = (
    'Primes', 'Subprimes', 'Full Spec', 'Food Grade', 'VRR',
    'LIQUID LIVE RESIN', 'DISTALLATE', 'BHO', 'Rosin', 'Gummies',
    '0.5g O2 Vape', '1g O2 Vapes',
    '1g Jarred Rosin', '3g Jarred Rosin',
)

_col_cache = {}

def _col_exists(doctype, fieldname):
    key = (doctype, fieldname)
    if key not in _col_cache:
        try:
            frappe.db.sql(f"SELECT `{fieldname}` FROM `tab{doctype}` LIMIT 0")
            _col_cache[key] = True
        except Exception:
            _col_cache[key] = False
    return _col_cache[key]


def _cos(companies=None):
    if not companies:
        return MBI_COMPANIES
    if isinstance(companies, str):
        import json
        try:
            c = json.loads(companies)
            return tuple(c) if c else MBI_COMPANIES
        except Exception:
            return (companies,) if companies else MBI_COMPANIES
    return tuple(companies) if companies else MBI_COMPANIES


def _intercompany_filter():
    """SQL fragment to exclude intercompany invoices."""
    return "(COALESCE(inter_company_invoice_reference, '') = '')"


# Subquery used in every query to exclude internal customers
_NOT_INTERNAL = "(SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)"


# ── KPI Summary ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_summary_kpis(companies=None):
    cos = _cos(companies)

    open_so = frappe.db.sql(f"""
        SELECT COUNT(*) AS cnt, COALESCE(SUM(grand_total), 0) AS total
        FROM `tabSales Order`
        WHERE company IN %(cos)s AND docstatus = 1
          AND status IN ('To Deliver and Bill', 'To Deliver', 'To Bill')
          AND customer NOT IN {_NOT_INTERNAL}
    """, {"cos": cos}, as_dict=True)[0]

    draft_si = frappe.db.sql("""
        SELECT COUNT(*) AS cnt FROM `tabSales Invoice`
        WHERE company IN %(cos)s AND docstatus = 0
    """, {"cos": cos}, as_dict=True)[0].cnt

    ar = frappe.db.sql(f"""
        SELECT COALESCE(SUM(outstanding_amount), 0) AS bal
        FROM `tabSales Invoice`
        WHERE company IN %(cos)s AND docstatus = 1 AND outstanding_amount > 0.01
          AND (COALESCE(inter_company_invoice_reference, '') = '')
          AND customer NOT IN {_NOT_INTERNAL}
    """, {"cos": cos}, as_dict=True)[0].bal

    ap = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0) AS bal
        FROM `tabPurchase Invoice`
        WHERE company IN %(cos)s AND docstatus = 1 AND outstanding_amount > 0.01
          AND (COALESCE(inter_company_invoice_reference, '') = '')
    """, {"cos": cos}, as_dict=True)[0].bal

    so_no_dn = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled','Closed','Completed')
          AND so.customer NOT IN {_NOT_INTERNAL}
          AND so.name NOT IN (
              SELECT DISTINCT dni.against_sales_order
              FROM `tabDelivery Note Item` dni
              JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
              WHERE dni.against_sales_order IS NOT NULL AND dni.against_sales_order != ''
          )
    """, {"cos": cos})[0][0]

    so_no_si = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled','Closed','Completed')
          AND so.customer NOT IN {_NOT_INTERNAL}
          AND so.name NOT IN (
              SELECT DISTINCT sii.sales_order
              FROM `tabSales Invoice Item` sii
              JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
              WHERE sii.sales_order IS NOT NULL AND sii.sales_order != ''
          )
    """, {"cos": cos})[0][0]

    so_no_both = frappe.db.sql(f"""
        SELECT COUNT(*) FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled','Closed','Completed')
          AND so.customer NOT IN {_NOT_INTERNAL}
          AND so.name NOT IN (
              SELECT DISTINCT dni.against_sales_order
              FROM `tabDelivery Note Item` dni
              JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
              WHERE dni.against_sales_order IS NOT NULL AND dni.against_sales_order != ''
          )
          AND so.name NOT IN (
              SELECT DISTINCT sii.sales_order
              FROM `tabSales Invoice Item` sii
              JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
              WHERE sii.sales_order IS NOT NULL AND sii.sales_order != ''
          )
    """, {"cos": cos})[0][0]

    draft_si_value = frappe.db.sql("""
        SELECT COALESCE(SUM(grand_total), 0) FROM `tabSales Invoice`
        WHERE company IN %(cos)s AND docstatus = 0
    """, {"cos": cos})[0][0]

    return {
        "open_so_count":    int(open_so.cnt or 0),
        "open_so_value":    float(open_so.total or 0),
        "draft_si_count":   int(draft_si or 0),
        "draft_si_value":   float(draft_si_value or 0),
        "ar_balance":       float(ar or 0),
        "ap_balance":       float(ap or 0),
        "so_no_dn_count":   int(so_no_dn or 0),
        "so_no_si_count":   int(so_no_si or 0),
        "so_no_both_count": int(so_no_both or 0),
    }


# ── Logistics Circuit ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_logistics_circuit(companies=None):
    cos = _cos(companies)
    has_logistics = _col_exists("Sales Order", "custom_logistics_status")
    STAGES = ['Need to Schedule', 'Scheduled', 'Preparing', 'Prepared', 'Staged', 'Closed Out']

    result = {}
    for company in cos:
        pending = frappe.db.sql("""
            SELECT COUNT(*) FROM `tabSales Order`
            WHERE company = %(co)s AND docstatus = 1
              AND status IN ('To Deliver and Bill','To Deliver','To Bill')
        """, {"co": company})[0][0]

        co_data = {"pending_so_count": int(pending or 0)}
        for s in STAGES:
            key = s.lower().replace(' ', '_') + '_count'
            if has_logistics:
                cnt = frappe.db.sql("""
                    SELECT COUNT(*) FROM `tabSales Order`
                    WHERE company = %(co)s AND docstatus = 1
                      AND custom_logistics_status = %(st)s
                """, {"co": company, "st": s})[0][0]
            else:
                cnt = 0
            co_data[key] = int(cnt or 0)

        result[company] = co_data

    return result


# ── Sales Documents ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_orders(companies=None, limit=100):
    cos = _cos(companies)
    limit = min(int(limit or 100), 500)
    order_type_col = (
        "COALESCE(so.custom_sales_order_type, so.order_type)"
        if _col_exists("Sales Order", "custom_sales_order_type")
        else "so.order_type"
    )
    logistics_col = (
        "so.custom_logistics_status"
        if _col_exists("Sales Order", "custom_logistics_status")
        else "NULL"
    )
    return frappe.db.sql(f"""
        SELECT so.name, so.customer_name, so.company,
               so.transaction_date, so.delivery_date,
               so.grand_total, so.total_qty, so.status,
               {order_type_col} AS order_type,
               {logistics_col} AS logistics_status
        FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled')
          AND so.customer NOT IN {_NOT_INTERNAL}
        ORDER BY so.transaction_date DESC
        LIMIT %(limit)s
    """, {"cos": cos, "limit": limit}, as_dict=True)


@frappe.whitelist()
def get_sales_invoices(companies=None, limit=100):
    cos = _cos(companies)
    limit = min(int(limit or 100), 500)
    order_type_col = (
        "COALESCE(si.custom_sales_order_type, '')"
        if _col_exists("Sales Invoice", "custom_sales_order_type")
        else "''"
    )
    return frappe.db.sql(f"""
        SELECT si.name, si.customer_name, si.company,
               si.posting_date, si.due_date,
               si.grand_total, si.outstanding_amount,
               si.grand_total - si.outstanding_amount AS paid_amount,
               si.status,
               {order_type_col} AS order_type
        FROM `tabSales Invoice` si
        WHERE si.company IN %(cos)s AND si.docstatus = 1
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND si.customer NOT IN {_NOT_INTERNAL}
        ORDER BY si.posting_date DESC
        LIMIT %(limit)s
    """, {"cos": cos, "limit": limit}, as_dict=True)


@frappe.whitelist()
def get_delivery_notes(companies=None, limit=100):
    cos = _cos(companies)
    limit = min(int(limit or 100), 500)
    return frappe.db.sql(f"""
        SELECT dn.name, dn.customer_name, dn.company,
               dn.posting_date, dn.lr_no,
               dn.grand_total, dn.total_qty, dn.status
        FROM `tabDelivery Note` dn
        WHERE dn.company IN %(cos)s AND dn.docstatus = 1
          AND dn.customer NOT IN {_NOT_INTERNAL}
        ORDER BY dn.posting_date DESC
        LIMIT %(limit)s
    """, {"cos": cos, "limit": limit}, as_dict=True)


# ── Gap Lists ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_gap_lists(companies=None):
    cos = _cos(companies)

    order_type_col = (
        "COALESCE(so.custom_sales_order_type, so.order_type)"
        if _col_exists("Sales Order", "custom_sales_order_type")
        else "so.order_type"
    )
    base = f"""
        SELECT so.name, so.customer_name, so.company,
               so.transaction_date, so.grand_total, so.total_qty, so.status,
               {order_type_col} AS order_type
        FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled','Closed','Completed')
          AND so.customer NOT IN {_NOT_INTERNAL}
    """

    no_dn = frappe.db.sql(base + """
          AND so.name NOT IN (
              SELECT DISTINCT dni.against_sales_order
              FROM `tabDelivery Note Item` dni
              JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
              WHERE dni.against_sales_order IS NOT NULL AND dni.against_sales_order != ''
          )
        ORDER BY so.transaction_date ASC LIMIT 200
    """, {"cos": cos}, as_dict=True)

    no_si = frappe.db.sql(base + """
          AND so.name NOT IN (
              SELECT DISTINCT sii.sales_order
              FROM `tabSales Invoice Item` sii
              JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
              WHERE sii.sales_order IS NOT NULL AND sii.sales_order != ''
          )
        ORDER BY so.transaction_date ASC LIMIT 200
    """, {"cos": cos}, as_dict=True)

    no_both = frappe.db.sql(base + """
          AND so.name NOT IN (
              SELECT DISTINCT dni.against_sales_order
              FROM `tabDelivery Note Item` dni
              JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
              WHERE dni.against_sales_order IS NOT NULL AND dni.against_sales_order != ''
          )
          AND so.name NOT IN (
              SELECT DISTINCT sii.sales_order
              FROM `tabSales Invoice Item` sii
              JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
              WHERE sii.sales_order IS NOT NULL AND sii.sales_order != ''
          )
        ORDER BY so.transaction_date ASC LIMIT 200
    """, {"cos": cos}, as_dict=True)

    return {
        "no_dn":       no_dn,      "no_dn_count":   len(no_dn),
        "no_si":       no_si,      "no_si_count":   len(no_si),
        "no_both":     no_both,    "no_both_count": len(no_both),
    }


# ── Invoices with Payments ────────────────────────────────────────────────────

@frappe.whitelist()
def get_invoices_with_payments(companies=None, limit=100):
    cos = _cos(companies)
    limit = min(int(limit or 100), 500)
    return frappe.db.sql("""
        SELECT
            si.name, si.customer_name, si.company,
            si.posting_date, si.due_date,
            si.grand_total, si.outstanding_amount,
            si.grand_total - si.outstanding_amount AS paid_amount,
            si.status,
            DATEDIFF(CURDATE(), si.due_date) AS days_overdue,
            GROUP_CONCAT(DISTINCT pe.mode_of_payment
                         ORDER BY pe.posting_date SEPARATOR ', ') AS payment_modes
        FROM `tabSales Invoice` si
        LEFT JOIN `tabPayment Entry Reference` per
            ON per.reference_doctype = 'Sales Invoice' AND per.reference_name = si.name
        LEFT JOIN `tabPayment Entry` pe
            ON pe.name = per.parent AND pe.docstatus = 1
        WHERE si.company IN %(cos)s AND si.docstatus = 1
          AND si.outstanding_amount > 0.01
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND si.customer NOT IN (SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)
        GROUP BY si.name
        ORDER BY si.due_date ASC
        LIMIT %(limit)s
    """, {"cos": cos, "limit": limit}, as_dict=True)


# ── Cash & Bank — pulled from Invoices ───────────────────────────────────────

@frappe.whitelist()
def get_cash_bank_payments(companies=None):
    cos = _cos(companies)

    by_company = frappe.db.sql("""
        SELECT
            si.company,
            COUNT(si.name)                                    AS invoice_count,
            COALESCE(SUM(si.grand_total), 0)                  AS total_billed,
            COALESCE(SUM(si.grand_total - si.outstanding_amount), 0) AS total_collected,
            COALESCE(SUM(si.outstanding_amount), 0)           AS total_outstanding
        FROM `tabSales Invoice` si
        WHERE si.company IN %(cos)s AND si.docstatus = 1
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND si.customer NOT IN (SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)
        GROUP BY si.company
        ORDER BY si.company
    """, {"cos": cos}, as_dict=True)

    total_billed      = sum(float(r.total_billed or 0) for r in by_company)
    total_collected   = sum(float(r.total_collected or 0) for r in by_company)
    total_outstanding = sum(float(r.total_outstanding or 0) for r in by_company)

    return {
        "by_company":        by_company,
        "total_billed":      total_billed,
        "total_collected":   total_collected,
        "total_outstanding": total_outstanding,
    }


# ── Conversion Overview ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_conversion_overview(companies=None):
    cos = _cos(companies)

    def _q(sql, args):
        return int(frappe.db.sql(sql, args)[0][0] or 0)

    total_so    = _q("SELECT COUNT(*) FROM `tabSales Order` WHERE company IN %(cos)s AND docstatus=1 AND status!='Cancelled'", {"cos": cos})
    so_with_dn  = _q("""SELECT COUNT(DISTINCT so.name) FROM `tabSales Order` so
                        JOIN `tabDelivery Note Item` dni ON dni.against_sales_order=so.name
                        JOIN `tabDelivery Note` dn ON dn.name=dni.parent AND dn.docstatus=1
                        WHERE so.company IN %(cos)s AND so.docstatus=1""", {"cos": cos})
    so_with_si  = _q("""SELECT COUNT(DISTINCT so.name) FROM `tabSales Order` so
                        JOIN `tabSales Invoice Item` sii ON sii.sales_order=so.name
                        JOIN `tabSales Invoice` si ON si.name=sii.parent AND si.docstatus=1
                        WHERE so.company IN %(cos)s AND so.docstatus=1""", {"cos": cos})
    so_with_both = _q("""SELECT COUNT(DISTINCT so.name) FROM `tabSales Order` so
                         JOIN `tabDelivery Note Item` dni ON dni.against_sales_order=so.name
                         JOIN `tabDelivery Note` dn ON dn.name=dni.parent AND dn.docstatus=1
                         JOIN `tabSales Invoice Item` sii ON sii.sales_order=so.name
                         JOIN `tabSales Invoice` si ON si.name=sii.parent AND si.docstatus=1
                         WHERE so.company IN %(cos)s AND so.docstatus=1""", {"cos": cos})
    total_si    = _q("SELECT COUNT(*) FROM `tabSales Invoice` WHERE company IN %(cos)s AND docstatus=1", {"cos": cos})
    si_paid     = _q("""SELECT COUNT(DISTINCT si.name) FROM `tabSales Invoice` si
                        JOIN `tabPayment Entry Reference` per ON per.reference_doctype='Sales Invoice' AND per.reference_name=si.name
                        JOIN `tabPayment Entry` pe ON pe.name=per.parent AND pe.docstatus=1
                        WHERE si.company IN %(cos)s AND si.docstatus=1""", {"cos": cos})

    def pct(a, b):
        return round(a / b * 100, 1) if b else 0

    return {
        "total_so":    total_so,
        "so_with_dn":  so_with_dn,   "so_dn_pct":  pct(so_with_dn, total_so),
        "so_with_si":  so_with_si,   "so_si_pct":  pct(so_with_si, total_so),
        "so_with_both": so_with_both, "so_both_pct": pct(so_with_both, total_so),
        "total_si":    total_si,
        "si_paid":     si_paid,       "si_paid_pct": pct(si_paid, total_si),
    }


# ── Item Group Totals ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_item_group_totals(companies=None):
    cos = _cos(companies)
    # query includes aliased groups too so their data gets merged
    ig_query = MBI_ITEM_GROUPS + tuple(_IG_ALIAS.keys())

    so_rows = frappe.db.sql("""
        SELECT COALESCE(i.item_group,'Other') AS item_group,
               SUM(soi.amount) AS amount, SUM(soi.qty) AS qty
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name=soi.parent
        LEFT JOIN `tabItem` i ON i.name=soi.item_code
        WHERE so.company IN %(cos)s AND so.docstatus=1 AND so.status!='Cancelled'
          AND i.item_group IN %(ig)s
        GROUP BY i.item_group
    """, {"cos": cos, "ig": ig_query}, as_dict=True)

    si_rows = frappe.db.sql("""
        SELECT COALESCE(i.item_group,'Other') AS item_group,
               SUM(sii.amount) AS amount, SUM(sii.qty) AS qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name=sii.parent
        LEFT JOIN `tabItem` i ON i.name=sii.item_code
        WHERE si.company IN %(cos)s AND si.docstatus=1
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND i.item_group IN %(ig)s
        GROUP BY i.item_group
    """, {"cos": cos, "ig": ig_query}, as_dict=True)

    dn_rows = frappe.db.sql("""
        SELECT COALESCE(i.item_group,'Other') AS item_group,
               SUM(dni.amount) AS amount, SUM(dni.qty) AS qty
        FROM `tabDelivery Note Item` dni
        JOIN `tabDelivery Note` dn ON dn.name=dni.parent
        LEFT JOIN `tabItem` i ON i.name=dni.item_code
        WHERE dn.company IN %(cos)s AND dn.docstatus=1
          AND i.item_group IN %(ig)s
        GROUP BY i.item_group
    """, {"cos": cos, "ig": ig_query}, as_dict=True)

    empty = {"so_qty": 0, "so_value": 0, "dn_qty": 0, "dn_value": 0, "si_qty": 0, "si_value": 0}
    merged = {g: dict(item_group=g, **empty) for g in MBI_ITEM_GROUPS}

    def _add(row, key_qty, key_val):
        g = _IG_ALIAS.get(row.item_group, row.item_group)
        if g in merged:
            merged[g][key_qty] += float(row.qty or 0)
            merged[g][key_val] += float(row.amount or 0)

    for r in so_rows: _add(r, "so_qty", "so_value")
    for r in si_rows: _add(r, "si_qty", "si_value")
    for r in dn_rows: _add(r, "dn_qty", "dn_value")

    return [merged[g] for g in MBI_ITEM_GROUPS]


# ── Item Group Conversion ─────────────────────────────────────────────────────

@frappe.whitelist()
def get_item_group_conversion(companies=None):
    cos = _cos(companies)
    params = {"cos": cos}

    def _union(slots, item_col, qty_col, ig_col):
        parts = []
        for n in slots:
            alias = f"i{n}"
            parts.append(
                f"SELECT COALESCE(cei.{ig_col.format(n=n)}, {alias}.item_group) AS ig,"
                f" SUM(COALESCE(cei.{qty_col.format(n=n)}, 0)) AS qty"
                f" FROM `tabConversion Entry Item` cei"
                f" JOIN `tabConversion Entry` ce ON ce.name=cei.parent"
                f"   AND ce.docstatus=1 AND ce.company IN %(cos)s"
                f" LEFT JOIN tabItem {alias} ON {alias}.name=cei.{item_col.format(n=n)}"
                f" WHERE COALESCE(cei.{item_col.format(n=n)}, '') != ''"
                f" GROUP BY 1"
            )
        inner = " UNION ALL ".join(parts)
        return (
            f"SELECT ig, SUM(qty) AS total"
            f" FROM ({inner}) t"
            f" WHERE ig IS NOT NULL AND ig != ''"
            f" GROUP BY ig ORDER BY total DESC"
        )

    rm_sql = _union(range(1, 8), "raw_material_{n}", "qty_rm_{n}", "rm_{n}_item_group")
    fg_sql = _union(range(1, 3), "finished_good_{n}", "qty_fg_{n}", "fg_{n}_item_group")

    rm_rows = frappe.db.sql(rm_sql, params, as_dict=True)
    fg_rows = frappe.db.sql(fg_sql, params, as_dict=True)

    rm_list = [{"item_group": r.ig, "qty": float(r.total or 0)} for r in rm_rows]
    fg_list = [{"item_group": r.ig, "qty": float(r.total or 0)} for r in fg_rows]

    total_rm = sum(r["qty"] for r in rm_list)
    total_fg = sum(r["qty"] for r in fg_list)

    for r in rm_list:
        r["pct"] = round(r["qty"] / total_rm * 100, 1) if total_rm else 0
    for r in fg_list:
        r["pct"] = round(r["qty"] / total_fg * 100, 1) if total_fg else 0

    return {
        "rm_groups":    rm_list,
        "fg_groups":    fg_list,
        "total_rm_qty": total_rm,
        "total_fg_qty": total_fg,
    }


# ── Hardware Counts (Vape Conversion) ────────────────────────────────────────

@frappe.whitelist()
def get_hardware_counts(companies=None):
    cos = _cos(companies)

    stock_rows = frappe.db.sql("""
        SELECT
            ig.name                          AS item_group,
            COALESCE(SUM(b.actual_qty), 0)   AS total_qty
        FROM `tabItem Group` ig
        LEFT JOIN tabItem i   ON i.item_group = ig.name
        LEFT JOIN tabBin  b   ON b.item_code  = i.name
        LEFT JOIN tabWarehouse w ON w.name    = b.warehouse AND w.company IN %(cos)s
        WHERE ig.parent_item_group = 'Packaged goods'
        GROUP BY ig.name
        ORDER BY ig.name
    """, {"cos": cos}, as_dict=True)

    in_rows = frappe.db.sql("""
        SELECT
            ig.name                                   AS item_group,
            COALESCE(SUM(sle.actual_qty), 0)          AS in_qty
        FROM `tabItem Group` ig
        LEFT JOIN tabItem i   ON i.item_group = ig.name
        LEFT JOIN `tabStock Ledger Entry` sle
            ON sle.item_code = i.name
            AND sle.actual_qty > 0
            AND sle.is_cancelled = 0
        LEFT JOIN tabWarehouse w ON w.name = sle.warehouse AND w.company IN %(cos)s
        WHERE ig.parent_item_group = 'Packaged goods'
        GROUP BY ig.name
    """, {"cos": cos}, as_dict=True)

    in_map = {r.item_group: float(r.in_qty or 0) for r in in_rows}

    return [
        {
            "item_group": r.item_group,
            "total_qty":  float(r.total_qty or 0),
            "in_qty":     in_map.get(r.item_group, 0),
        }
        for r in stock_rows
    ]


# ── Tolling Check (MTM) ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_tolling_check():
    cos = MBI_COMPANIES
    rows = frappe.db.sql("""
        SELECT
            so.name              AS so_name,
            so.customer_name,
            so.transaction_date,
            so.status,
            so.company,
            soi.item_code,
            soi.item_name,
            soi.uom,
            soi.qty                                    AS ordered_qty,
            COALESCE(soi.delivered_qty, 0)             AS delivered_qty,
            (soi.qty - COALESCE(soi.delivered_qty, 0)) AS pending_qty,
            COALESCE(b.actual_qty, 0)                  AS stock_qty
        FROM `tabSales Order` so
        JOIN `tabSales Order Item` soi ON soi.parent = so.name
        LEFT JOIN tabBin b ON b.item_code = soi.item_code AND b.warehouse = soi.warehouse
        WHERE so.company IN %(cos)s
          AND so.docstatus = 1
          AND so.status IN ('To Deliver and Bill', 'To Deliver')
          AND so.customer NOT IN (SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)
        ORDER BY so.transaction_date ASC
    """, {"cos": cos}, as_dict=True)

    so_map = {}
    for r in rows:
        key = r.so_name
        if key not in so_map:
            so_map[key] = {
                "so_name":         r.so_name,
                "customer_name":   r.customer_name,
                "transaction_date": str(r.transaction_date),
                "status":          r.status,
                "company":         r.company,
                "items":           [],
            }
        pending = float(r.pending_qty or 0)
        if pending <= 0:
            continue
        stock   = float(r.stock_qty or 0)
        short   = round(max(0.0, pending - stock), 4)
        so_map[key]["items"].append({
            "item_code":    r.item_code,
            "item_name":    r.item_name,
            "uom":          r.uom,
            "ordered_qty":  float(r.ordered_qty or 0),
            "delivered_qty":float(r.delivered_qty or 0),
            "pending_qty":  pending,
            "stock_qty":    stock,
            "shortage":     short,
            "covered":      stock >= pending,
        })

    result = []
    for so in so_map.values():
        items = so["items"]
        if not items:
            continue
        so["has_shortage"] = any(not i["covered"] for i in items)
        so["all_covered"]  = all(i["covered"] for i in items)
        so["shortage_count"] = sum(1 for i in items if not i["covered"])
        result.append(so)

    # SOs with shortages first, then date asc
    result.sort(key=lambda x: (not x["has_shortage"], x["transaction_date"]))
    return result


# ── AR / AP Summary ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ar_ap_summary(companies=None):
    cos = _cos(companies)

    ar = frappe.db.sql("""
        SELECT si.customer, si.customer_name, si.company,
               COUNT(si.name) AS invoice_count,
               SUM(si.grand_total) AS total_billed,
               SUM(si.outstanding_amount) AS outstanding,
               MAX(si.due_date) AS latest_due,
               SUM(CASE WHEN DATEDIFF(CURDATE(),si.due_date)>0
                        THEN si.outstanding_amount ELSE 0 END) AS overdue
        FROM `tabSales Invoice` si
        WHERE si.company IN %(cos)s AND si.docstatus=1 AND si.outstanding_amount>0.01
          AND (COALESCE(si.inter_company_invoice_reference, '') = '')
          AND si.customer NOT IN (SELECT name FROM `tabCustomer` WHERE is_internal_customer = 1)
        GROUP BY si.customer, si.customer_name, si.company
        ORDER BY outstanding DESC LIMIT 50
    """, {"cos": cos}, as_dict=True)

    ap = frappe.db.sql("""
        SELECT pi.supplier, pi.supplier_name, pi.company,
               COUNT(pi.name) AS invoice_count,
               SUM(pi.grand_total) AS total_billed,
               SUM(pi.outstanding_amount) AS outstanding,
               MAX(pi.due_date) AS latest_due,
               SUM(CASE WHEN DATEDIFF(CURDATE(),pi.due_date)>0
                        THEN pi.outstanding_amount ELSE 0 END) AS overdue
        FROM `tabPurchase Invoice` pi
        WHERE pi.company IN %(cos)s AND pi.docstatus=1 AND pi.outstanding_amount>0.01
          AND (COALESCE(pi.inter_company_invoice_reference, '') = '')
        GROUP BY pi.supplier, pi.supplier_name, pi.company
        ORDER BY outstanding DESC LIMIT 50
    """, {"cos": cos}, as_dict=True)

    return {
        "ar": ar, "ap": ap,
        "ar_total":   sum(float(r.outstanding or 0) for r in ar),
        "ap_total":   sum(float(r.outstanding or 0) for r in ap),
        "ar_overdue": sum(float(r.overdue or 0) for r in ar),
        "ap_overdue": sum(float(r.overdue or 0) for r in ap),
    }


# ── Sales by Type ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_sales_by_type(companies=None):
    cos = _cos(companies)
    if _col_exists("Sales Order", "custom_sales_order_type"):
        type_expr  = "COALESCE(NULLIF(custom_sales_order_type,''), order_type, 'Standard')"
        group_expr = "COALESCE(NULLIF(custom_sales_order_type,''), order_type, 'Standard'), company"
    else:
        type_expr  = "COALESCE(order_type, 'Standard')"
        group_expr = "COALESCE(order_type, 'Standard'), company"
    return frappe.db.sql(f"""
        SELECT
            {type_expr} AS type_label,
            company,
            COUNT(*) AS cnt,
            SUM(grand_total) AS total_amount,
            SUM(CASE WHEN status IN ('To Deliver and Bill','To Deliver','To Bill')
                     THEN 1 ELSE 0 END) AS open_count
        FROM `tabSales Order`
        WHERE company IN %(cos)s AND docstatus=1 AND status!='Cancelled'
        GROUP BY {group_expr}
        ORDER BY total_amount DESC
    """, {"cos": cos}, as_dict=True)
