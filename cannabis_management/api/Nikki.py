import frappe


@frappe.whitelist()
def get_ar_by_client():
    """
    Accounts Receivable grouped by Bill To (customer).
    Returns unpaid / partially paid Sales Invoices.
    """
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    rows = frappe.db.sql(
        """
        SELECT
            si.customer                                     AS client,
            si.customer_name                                AS client_name,
            COUNT(si.name)                                  AS invoice_count,
            SUM(si.grand_total)                             AS total_billed,
            SUM(si.outstanding_amount)                      AS total_outstanding,
            SUM(si.grand_total - si.outstanding_amount)     AS total_paid,
            MAX(si.due_date)                                AS latest_due_date,
            MIN(si.due_date)                                AS oldest_due_date
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
        GROUP BY si.customer, si.customer_name
        ORDER BY total_outstanding DESC
        """,
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_all_invoices(limit=25, offset=0, search=None):
    """
    All submitted Sales Invoices — read-only reference view.
    Supports optional search by customer name or invoice ID.
    """
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    if search in (None, "None", "", "null"):
        search = None

    search_clause = ""
    params = {"limit": int(limit), "offset": int(offset)}

    if search:
        search_clause = "AND (si.name LIKE %(search)s OR si.customer_name LIKE %(search)s)"
        params["search"] = f"%{search}%"

    rows = frappe.db.sql(
        f"""
        SELECT
            si.name                 AS invoice_id,
            si.customer_name        AS client,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            si.status,
            si.currency
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          {search_clause}
        ORDER BY si.posting_date DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        params,
        as_dict=True,
    )
    return rows


@frappe.whitelist()
def get_ar_summary():
    """
    Top-level AR numbers for the KPI cards.
    """
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    result = frappe.db.sql(
        """
        SELECT
            COUNT(name)                              AS total_invoices,
            SUM(grand_total)                         AS total_billed,
            SUM(outstanding_amount)                  AS total_outstanding,
            SUM(grand_total - outstanding_amount)    AS total_collected,
            COUNT(DISTINCT customer)                 AS total_clients
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND outstanding_amount > 0
        """,
        as_dict=True,
    )
    return result[0] if result else {}