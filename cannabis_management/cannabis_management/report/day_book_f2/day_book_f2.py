import frappe
from frappe import _
from frappe.utils import today


def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "label": _("Type"),
            "fieldname": "type",
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "label": _("Opening Balance"),
            "fieldname": "opening_balance",
            "fieldtype": "Float",
            "width": 140,
        },
        {
            "label": _("Receipt"),
            "fieldname": "receipt",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Payment"),
            "fieldname": "payment",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Closing Balance"),
            "fieldname": "closing_balance",
            "fieldtype": "Float",
            "width": 150,
        },
    ]


def get_data(filters):
    from_date = filters.get("from_date") or today()
    to_date = filters.get("to_date") or today()
    company = filters.get("company")
    account = filters.get("account")

    conditions = ""
    gl_conditions = ""

    if company:
        conditions += " AND a.company = %(company)s"
        gl_conditions += " AND ge.company = %(company)s"
    if account:
        conditions += " AND a.name = %(account)s"
        gl_conditions += " AND ge.account = %(account)s"

    query = f"""
    WITH
# v1.1 - Clean labels
    accounts AS (
        SELECT
            a.name AS account,
            COALESCE(NULLIF(a.account_name, ''), a.name) AS account_label,
            a.account_type
        FROM tabAccount a
        WHERE a.is_group = 0
          AND IFNULL(a.disabled,0) = 0
          AND a.account_type IN ('Cash','Bank')
          {conditions}
    ),

    opening AS (
        SELECT
            ge.account,
            SUM(IFNULL(ge.debit,0) - IFNULL(ge.credit,0)) AS opening_balance
        FROM `tabGL Entry` ge
        WHERE ge.is_cancelled = 0
          AND ge.posting_date < DATE(%(from_date)s)
          {gl_conditions}
        GROUP BY ge.account
    ),

    period_mov AS (
        SELECT
            ge.account,
            SUM(IFNULL(ge.debit,0))  AS receipt,
            SUM(IFNULL(ge.credit,0)) AS payment
        FROM `tabGL Entry` ge
        WHERE ge.is_cancelled = 0
          AND ge.posting_date BETWEEN DATE(%(from_date)s) AND DATE(%(to_date)s)
          {gl_conditions}
        GROUP BY ge.account
    ),
    """ + """
    base AS (
        SELECT
            ac.account_type,
            ac.account_label AS type,
            IFNULL(op.opening_balance,0) AS opening_balance,
            IFNULL(pm.receipt,0) AS receipt,
            IFNULL(pm.payment,0) AS payment,
            ( IFNULL(op.opening_balance,0)
              + IFNULL(pm.receipt,0)
              - IFNULL(pm.payment,0)
            ) AS closing_balance
        FROM accounts ac
        LEFT JOIN opening op
            ON op.account = ac.account
        LEFT JOIN period_mov pm
            ON pm.account = ac.account
    ),

    cash_total AS (
        SELECT
            SUM(opening_balance) AS opening_balance,
            SUM(receipt) AS receipt,
            SUM(payment) AS payment,
            SUM(closing_balance) AS closing_balance
        FROM base
        WHERE account_type = 'Cash'
    ),

    bank_total AS (
        SELECT
            SUM(opening_balance) AS opening_balance,
            SUM(receipt) AS receipt,
            SUM(payment) AS payment,
            SUM(closing_balance) AS closing_balance
        FROM base
        WHERE account_type = 'Bank'
    ),

    grand_total AS (
        SELECT
            SUM(opening_balance) AS opening_balance,
            SUM(receipt) AS receipt,
            SUM(payment) AS payment,
            SUM(closing_balance) AS closing_balance
        FROM base
    )

    /* ===== FINAL OUTPUT ===== */
    SELECT
        r.type,
        r.opening_balance,
        r.receipt,
        r.payment,
        r.closing_balance
    FROM (
        /* ---------- CASH HEADER ---------- */
        SELECT
            'Cash' AS type,
            NULL AS opening_balance,
            NULL AS receipt,
            NULL AS payment,
            NULL AS closing_balance,
            10 AS sort_key,
            '' AS sort2

        UNION ALL

        /* Cash accounts */
        SELECT
            b.type,
            b.opening_balance,
            b.receipt,
            b.payment,
            b.closing_balance,
            20 AS sort_key,
            b.type AS sort2
        FROM base b
        WHERE b.account_type = 'Cash'

        UNION ALL

        /* Total Cash */
        SELECT
            'Total Cash' AS type,
            ct.opening_balance,
            ct.receipt,
            ct.payment,
            ct.closing_balance,
            30 AS sort_key,
            '' AS sort2
        FROM cash_total ct

        UNION ALL

        /* ---------- BANK HEADER ---------- */
        SELECT
            'Bank' AS type,
            NULL,
            NULL,
            NULL,
            NULL,
            40 AS sort_key,
            '' AS sort2

        UNION ALL

        /* Bank accounts */
        SELECT
            b.type,
            b.opening_balance,
            b.receipt,
            b.payment,
            b.closing_balance,
            50 AS sort_key,
            b.type AS sort2
        FROM base b
        WHERE b.account_type = 'Bank'

        UNION ALL

        /* Total Bank */
        SELECT
            'Total Bank' AS type,
            bt.opening_balance,
            bt.receipt,
            bt.payment,
            bt.closing_balance,
            60 AS sort_key,
            '' AS sort2
        FROM bank_total bt

        UNION ALL

        /* ---------- GRAND TOTAL ---------- */
        SELECT
            'Grand Total' AS type,
            gt.opening_balance,
            gt.receipt,
            gt.payment,
            gt.closing_balance,
            70 AS sort_key,
            '' AS sort2
        FROM grand_total gt

    ) r
    ORDER BY r.sort_key, r.sort2;
    """

    data = frappe.db.sql(
        query,
        {
            "from_date": from_date,
            "to_date": to_date,
            "company": company,
            "account": account,
        },
        as_dict=True,
    )
    return data
