import frappe
from frappe import _


@frappe.whitelist()
def get_nikki_ledger_summary():
    """
    Lightweight summary of Nikki Cash Ledger Entry data for the workspace widget.
    Finance roles see all entries; non-Finance sees only their own.
    """
    user = frappe.session.user
    finance_roles = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}
    is_finance = bool(finance_roles.intersection(set(frappe.get_roles(user))))

    user_filter = "" if is_finance else f"AND submitted_by_user = {frappe.db.escape(user)}"

    totals = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS total_out,
            COUNT(*) AS txn_count
        FROM `tabNikki Cash Ledger Entry`
        WHERE 1=1 {user_filter}
    """, as_dict=True)[0]

    recent = frappe.db.sql(f"""
        SELECT name, date, entity, direction, amount, status
        FROM `tabNikki Cash Ledger Entry`
        WHERE 1=1 {user_filter}
        ORDER BY date DESC, creation DESC
        LIMIT 10
    """, as_dict=True)

    for r in recent:
        r["date"]   = str(r["date"])
        r["amount"] = float(r["amount"] or 0)

    total_in  = float(totals.total_in)
    total_out = float(totals.total_out)

    return {
        "total_in":  total_in,
        "total_out": total_out,
        "net":       total_in - total_out,
        "count":     int(totals.txn_count),
        "recent":    recent,
    }


@frappe.whitelist()
def get_dashboard_data(person=None):
    """
    Full dashboard data sourced from Nikki Cash Ledger Entry.
    Finance roles see all entries or a specific submitter; others see only their own.
    """
    user = frappe.session.user
    finance_roles = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}
    is_finance = bool(finance_roles.intersection(set(frappe.get_roles(user))))

    if not is_finance:
        user_filter = f"AND n.submitted_by_user = {frappe.db.escape(user)}"
        person = user
    elif person:
        user_filter = f"AND n.submitted_by_user = {frappe.db.escape(person)}"
    else:
        user_filter = ""

    totals = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS total_out,
            COUNT(*) AS txn_count,
            COALESCE(SUM(CASE WHEN status='Open' THEN 1 ELSE 0 END), 0) AS open_count
        FROM `tabNikki Cash Ledger Entry` n
        WHERE 1=1 {user_filter}
    """, as_dict=True)[0]

    total_in  = float(totals.total_in)
    total_out = float(totals.total_out)

    summary = {
        "total_cash_in":    total_in,
        "total_cash_out":   total_out,
        "cash_in_hand":     total_in - total_out,
        "total_txns":       int(totals.txn_count),
        "pending_approvals": int(totals.open_count),
        "display_name":     person if (is_finance and person and person != user) else "",
        "total_expenses": 0.0,
        "reimbursed":     0.0,
        "net_owed":       0.0,
    }

    rows = frappe.db.sql(f"""
        SELECT name, date, entity, direction, amount, transaction_type,
               invoice_number, notes, receipt, status, submitted_by_user
        FROM `tabNikki Cash Ledger Entry` n
        WHERE 1=1 {user_filter}
        ORDER BY date DESC, creation DESC
        LIMIT 50
    """, as_dict=True)

    transactions = []
    for r in rows:
        transactions.append({
            "name":             r.name,
            "date":             str(r.date),
            "entity":           r.entity or "",
            "direction":        r.direction or "",
            "amount":           float(r.amount or 0),
            "money_in":         float(r.amount) if r.direction == "Cash In" else 0,
            "money_out":        float(r.amount) if r.direction == "Cash Out" else 0,
            "transaction_type": r.transaction_type or "",
            "invoice_number":   r.invoice_number or "",
            "notes":            r.notes or "",
            "receipt":          r.receipt or "",
            "approval_status":  r.status or "Open",
            "submitted_by_user": r.submitted_by_user or "",
        })

    monthly_rows = frappe.db.sql(f"""
        SELECT DATE_FORMAT(date, '%b %Y') AS month,
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS cash_out,
            COUNT(*) AS txn_count
        FROM `tabNikki Cash Ledger Entry` n
        WHERE 1=1 {user_filter}
        GROUP BY DATE_FORMAT(date, '%b %Y')
    """, as_dict=True)

    monthly_map = {}
    for row in monthly_rows:
        m = row.month or "Unknown"
        monthly_map[m] = {
            "month": m,
            "cash_in":   float(row.cash_in),
            "cash_out":  float(row.cash_out),
            "net_cash":  float(row.cash_in) - float(row.cash_out),
            "expenses":  0.0, "reimbursed": 0.0, "net_owed": 0.0,
            "txn_count": int(row.txn_count),
        }
    monthly = sorted(monthly_map.values(), key=lambda r: _month_sort_key(r["month"]))

    entity_rows = frappe.db.sql(f"""
        SELECT entity,
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS cash_out
        FROM `tabNikki Cash Ledger Entry` n
        WHERE 1=1 {user_filter}
        GROUP BY entity
    """, as_dict=True)

    entities = sorted([{
        "entity":    r.entity or "Unknown",
        "cash_in":   float(r.cash_in),
        "cash_out":  float(r.cash_out),
        "net_cash":  float(r.cash_in) - float(r.cash_out),
        "expenses":  0.0, "reimbursed": 0.0, "net_owed": 0.0,
    } for r in entity_rows], key=lambda r: r["entity"])

    persons = []
    if is_finance:
        persons = frappe.db.sql("""
            SELECT DISTINCT submitted_by_user AS name, submitted_by_user AS full_name
            FROM `tabNikki Cash Ledger Entry`
            WHERE submitted_by_user IS NOT NULL AND submitted_by_user != ''
            ORDER BY submitted_by_user
        """, as_dict=True)

    return {
        "summary":        summary,
        "monthly":        monthly,
        "entities":       entities,
        "transactions":   transactions,
        "persons":        persons,
        "is_finance":     is_finance,
        "current_person": person,
    }


def _month_sort_key(month_str):
    months = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
              "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
    try:
        parts = month_str.split()
        return int(parts[1]) * 100 + months.get(parts[0], 0)
    except Exception:
        return 0
