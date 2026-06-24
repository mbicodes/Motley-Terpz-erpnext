import frappe
from frappe.utils import nowdate

MBI_COMPANIES = ('TSBC Ranch', 'Master Touch Manufacturing')

MBI_ITEM_GROUPS = (
    'Fresh Frozen', 'Primes', 'Subprimes', 'Full Spec', 'Food Grade',
    'VRR', 'LLR', 'Distillate', 'BHO', 'Vapes', 'Gummies', 'Jars',
)

# Conversion view: same groups minus Fresh Frozen, plus Jars
MBI_CONV_GROUPS = (
    'Vapes', 'Primes', 'Subprimes', 'Full Spec', 'Food Grade',
    'VRR', 'LLR', 'Distillate', 'BHO', 'Gummies', 'Jars',
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


# ── KPI Summary ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_summary_kpis(companies=None):
    cos = _cos(companies)

    open_so = frappe.db.sql("""
        SELECT COUNT(*) AS cnt, COALESCE(SUM(grand_total), 0) AS total
        FROM `tabSales Order`
        WHERE company IN %(cos)s AND docstatus = 1
          AND status IN ('To Deliver and Bill', 'To Deliver', 'To Bill')
    """, {"cos": cos}, as_dict=True)[0]

    draft_si = frappe.db.sql("""
        SELECT COUNT(*) AS cnt FROM `tabSales Invoice`
        WHERE company IN %(cos)s AND docstatus = 0
    """, {"cos": cos}, as_dict=True)[0].cnt

    ar = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0) AS bal
        FROM `tabSales Invoice`
        WHERE company IN %(cos)s AND docstatus = 1 AND outstanding_amount > 0.01
          AND (COALESCE(inter_company_invoice_reference, '') = '')
    """, {"cos": cos}, as_dict=True)[0].bal

    ap = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0) AS bal
        FROM `tabPurchase Invoice`
        WHERE company IN %(cos)s AND docstatus = 1 AND outstanding_amount > 0.01
          AND (COALESCE(inter_company_invoice_reference, '') = '')
    """, {"cos": cos}, as_dict=True)[0].bal

    so_no_dn = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled','Closed','Completed')
          AND so.name NOT IN (
              SELECT DISTINCT dni.against_sales_order
              FROM `tabDelivery Note Item` dni
              JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
              WHERE dni.against_sales_order IS NOT NULL AND dni.against_sales_order != ''
          )
    """, {"cos": cos})[0][0]

    so_no_si = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled','Closed','Completed')
          AND so.name NOT IN (
              SELECT DISTINCT sii.sales_order
              FROM `tabSales Invoice Item` sii
              JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
              WHERE sii.sales_order IS NOT NULL AND sii.sales_order != ''
          )
    """, {"cos": cos})[0][0]

    so_no_both = frappe.db.sql("""
        SELECT COUNT(*) FROM `tabSales Order` so
        WHERE so.company IN %(cos)s AND so.docstatus = 1
          AND so.status NOT IN ('Cancelled','Closed','Completed')
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
        ORDER BY si.posting_date DESC
        LIMIT %(limit)s
    """, {"cos": cos, "limit": limit}, as_dict=True)


@frappe.whitelist()
def get_delivery_notes(companies=None, limit=100):
    cos = _cos(companies)
    limit = min(int(limit or 100), 500)
    return frappe.db.sql("""
        SELECT dn.name, dn.customer_name, dn.company,
               dn.posting_date, dn.lr_no,
               dn.grand_total, dn.total_qty, dn.status
        FROM `tabDelivery Note` dn
        WHERE dn.company IN %(cos)s AND dn.docstatus = 1
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
    ig  = MBI_ITEM_GROUPS

    so_rows = frappe.db.sql("""
        SELECT COALESCE(i.item_group,'Other') AS item_group,
               SUM(soi.amount) AS amount, SUM(soi.qty) AS qty
        FROM `tabSales Order Item` soi
        JOIN `tabSales Order` so ON so.name=soi.parent
        LEFT JOIN `tabItem` i ON i.name=soi.item_code
        WHERE so.company IN %(cos)s AND so.docstatus=1 AND so.status!='Cancelled'
          AND i.item_group IN %(ig)s
        GROUP BY i.item_group
    """, {"cos": cos, "ig": ig}, as_dict=True)

    si_rows = frappe.db.sql("""
        SELECT COALESCE(i.item_group,'Other') AS item_group,
               SUM(sii.amount) AS amount, SUM(sii.qty) AS qty
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name=sii.parent
        LEFT JOIN `tabItem` i ON i.name=sii.item_code
        WHERE si.company IN %(cos)s AND si.docstatus=1
          AND i.item_group IN %(ig)s
        GROUP BY i.item_group
    """, {"cos": cos, "ig": ig}, as_dict=True)

    dn_rows = frappe.db.sql("""
        SELECT COALESCE(i.item_group,'Other') AS item_group,
               SUM(dni.amount) AS amount, SUM(dni.qty) AS qty
        FROM `tabDelivery Note Item` dni
        JOIN `tabDelivery Note` dn ON dn.name=dni.parent
        LEFT JOIN `tabItem` i ON i.name=dni.item_code
        WHERE dn.company IN %(cos)s AND dn.docstatus=1
          AND i.item_group IN %(ig)s
        GROUP BY i.item_group
    """, {"cos": cos, "ig": ig}, as_dict=True)

    empty = {"so_qty": 0, "so_value": 0, "dn_qty": 0, "dn_value": 0, "si_qty": 0, "si_value": 0}
    merged = {g: dict(item_group=g, **empty) for g in ig}

    for r in so_rows:
        g = r.item_group
        if g in merged:
            merged[g]["so_qty"]   += float(r.qty or 0)
            merged[g]["so_value"] += float(r.amount or 0)
    for r in si_rows:
        g = r.item_group
        if g in merged:
            merged[g]["si_qty"]   += float(r.qty or 0)
            merged[g]["si_value"] += float(r.amount or 0)
    for r in dn_rows:
        g = r.item_group
        if g in merged:
            merged[g]["dn_qty"]   += float(r.qty or 0)
            merged[g]["dn_value"] += float(r.amount or 0)

    return [merged[g] for g in ig]


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

    HW = [
        {"label": "Vapes (All)",   "pat": "%vap%"},
        {"label": "1g Vapes",      "pat": "%1g%vap%"},
        {"label": "0.5g Vapes",    "pat": "%0.5g%vap%"},
        {"label": "0.3g Vapes",    "pat": "%0.3g%vap%"},
        {"label": "1g Jars",       "pat": "%1g Jar%"},
        {"label": "3.5g Jars",     "pat": "%3.5g Jar%"},
        {"label": "7g Jars",       "pat": "%7g Jar%"},
    ]

    results = []
    for hw in HW:
        so_r = frappe.db.sql("""
            SELECT COALESCE(SUM(soi.qty),0) AS qty, COALESCE(SUM(soi.amount),0) AS amount
            FROM `tabSales Order Item` soi
            JOIN `tabSales Order` so ON so.name=soi.parent
            WHERE so.company IN %(cos)s AND so.docstatus=1 AND so.status!='Cancelled'
              AND (soi.item_name LIKE %(pat)s OR soi.item_code LIKE %(pat)s OR soi.item_group LIKE %(pat)s)
        """, {"cos": cos, "pat": hw["pat"]}, as_dict=True)[0]

        dn_r = frappe.db.sql("""
            SELECT COALESCE(SUM(dni.qty),0) AS qty
            FROM `tabDelivery Note Item` dni
            JOIN `tabDelivery Note` dn ON dn.name=dni.parent
            WHERE dn.company IN %(cos)s AND dn.docstatus=1
              AND (dni.item_name LIKE %(pat)s OR dni.item_code LIKE %(pat)s OR dni.item_group LIKE %(pat)s)
        """, {"cos": cos, "pat": hw["pat"]}, as_dict=True)[0]

        si_r = frappe.db.sql("""
            SELECT COALESCE(SUM(sii.qty),0) AS qty
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name=sii.parent
            WHERE si.company IN %(cos)s AND si.docstatus=1
              AND (sii.item_name LIKE %(pat)s OR sii.item_code LIKE %(pat)s OR sii.item_group LIKE %(pat)s)
        """, {"cos": cos, "pat": hw["pat"]}, as_dict=True)[0]

        so_qty = float(so_r.qty or 0)
        dn_qty = float(dn_r.qty or 0)
        si_qty = float(si_r.qty or 0)

        results.append({
            "hardware_type": hw["label"],
            "so_qty":        so_qty,
            "dn_qty":        dn_qty,
            "si_qty":        si_qty,
            "so_amount":     float(so_r.amount or 0),
            "dn_conv_pct":   round(dn_qty / so_qty * 100, 1) if so_qty else 0,
            "si_conv_pct":   round(si_qty / so_qty * 100, 1) if so_qty else 0,
        })

    return results


# ── Tolling Check (MTM) ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_tolling_check():
    return frappe.db.sql("""
        SELECT
            so.name AS so_name, so.customer_name, so.transaction_date,
            so.grand_total, so.status,
            soi.item_code, soi.item_name,
            soi.qty AS ordered_qty, soi.uom,
            COALESCE(b.actual_qty, 0) AS available_qty,
            CASE WHEN COALESCE(b.actual_qty, 0) < soi.qty THEN 1 ELSE 0 END AS shortage
        FROM `tabSales Order` so
        JOIN `tabSales Order Item` soi ON soi.parent = so.name
        LEFT JOIN `tabBin` b
            ON b.item_code = soi.item_code
           AND b.warehouse LIKE '%%MTM%%'
        WHERE so.company = 'Master Touch Manufacturing'
          AND so.docstatus = 1
          AND so.status IN ('To Deliver and Bill','To Deliver','To Bill')
        ORDER BY so.transaction_date ASC
        LIMIT 200
    """, as_dict=True)


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
