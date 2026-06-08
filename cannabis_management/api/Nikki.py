import frappe


# ── Cash Management ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_cash_summary():
    """
    Returns cash on hand, net owed, and pending count for the logged-in user.
    Used by the Nikki Dashboard custom HTML block number cards.
    """
    user = frappe.session.user
    person = frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")
    if not person:
        return {"cash_in_hand": 0, "net_owed": 0, "pending_approvals": 0, "person": None}

    ledger = frappe.db.get_value(
        "Cash Balance Ledger",
        {"cash_tracker_person": person},
        ["net_cash", "net_owed", "total_cash_in", "total_cash_out",
         "total_expenses", "total_reimbursed"],
        as_dict=True,
    )

    pending = frappe.db.sql("""
        SELECT
            (SELECT COUNT(*) FROM `tabCash Ledger Entry`
             WHERE cash_tracker_person=%s AND docstatus=1 AND approval_status='Pending') +
            (SELECT COUNT(*) FROM `tabExpense Tracker Entry`
             WHERE cash_tracker_person=%s AND docstatus=1 AND approval_status='Pending')
        AS cnt
    """, (person, person))[0][0] or 0

    return {
        "cash_in_hand":     float(ledger.net_cash if ledger else 0),
        "net_owed":         float(ledger.net_owed if ledger else 0),
        "total_cash_in":    float(ledger.total_cash_in if ledger else 0),
        "total_cash_out":   float(ledger.total_cash_out if ledger else 0),
        "total_expenses":   float(ledger.total_expenses if ledger else 0),
        "total_reimbursed": float(ledger.total_reimbursed if ledger else 0),
        "pending_approvals": int(pending),
        "person":           person,
    }


@frappe.whitelist()
def get_nikki_cash_entries(limit=20):
    """
    Returns the most recent Cash Ledger Entries and Expense Tracker Entries
    for the logged-in user — used by the dashboard transaction list.
    """
    user = frappe.session.user
    person = frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")
    if not person:
        return []

    cash_rows = frappe.db.sql("""
        SELECT name, date, entity, direction, amount, invoice_number,
               notes, receipt, approval_status, transaction_type,
               'Cash' AS source
        FROM `tabCash Ledger Entry`
        WHERE cash_tracker_person=%s AND docstatus=1
        ORDER BY date DESC, creation DESC
        LIMIT %s
    """, (person, int(limit)), as_dict=True)

    exp_rows = frappe.db.sql("""
        SELECT name, date, entity, direction, amount,
               '' AS invoice_number, notes, receipt,
               approval_status, transaction_type,
               'Expense' AS source
        FROM `tabExpense Tracker Entry`
        WHERE cash_tracker_person=%s AND docstatus=1
        ORDER BY date DESC, creation DESC
        LIMIT %s
    """, (person, int(limit)), as_dict=True)

    rows = []
    for r in cash_rows:
        rows.append({
            "name":             r.name,
            "date":             str(r.date),
            "entity":           r.entity or "",
            "direction":        r.direction,
            "money_in":         float(r.amount) if r.direction == "Cash In" else 0,
            "money_out":        float(r.amount) if r.direction == "Cash Out" else 0,
            "invoice_number":   r.invoice_number or "",
            "notes":            r.notes or "",
            "receipt":          r.receipt or "",
            "approval_status":  r.approval_status,
            "transaction_type": r.transaction_type,
            "source":           "Cash",
        })
    for r in exp_rows:
        rows.append({
            "name":             r.name,
            "date":             str(r.date),
            "entity":           r.entity or "",
            "direction":        r.direction,
            "money_in":         float(r.amount) if r.direction == "Reimbursement" else 0,
            "money_out":        float(r.amount) if r.direction == "Expense" else 0,
            "invoice_number":   "",
            "notes":            r.notes or "",
            "receipt":          r.receipt or "",
            "approval_status":  r.approval_status,
            "transaction_type": r.transaction_type,
            "source":           "Expense",
        })

    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows[:int(limit)]


# ── Accounts Receivable ───────────────────────────────────────────────────────

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