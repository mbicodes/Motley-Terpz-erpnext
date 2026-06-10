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
        SELECT name, date, entity, direction, amount, status,
               transaction_type, invoice_number, notes
        FROM `tabNikki Cash Ledger Entry`
        WHERE 1=1 {user_filter}
        ORDER BY date DESC, creation DESC
        LIMIT 10
    """, as_dict=True)

    for r in recent:
        r["date"]             = str(r["date"])
        r["amount"]           = float(r["amount"] or 0)
        r["transaction_type"] = r.get("transaction_type") or ""
        r["invoice_number"]   = r.get("invoice_number") or ""
        r["notes"]            = r.get("notes") or ""

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


@frappe.whitelist()
def get_full_dashboard_data(person=None):
    """
    Full Financial Command Center data — aggregated from Cash Ledger Entry + Expense Tracker Entry.
    Finance roles see all or can filter by Cash Tracker Person; others see only their own.
    """
    user = frappe.session.user
    finance_roles = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}
    is_finance = bool(finance_roles.intersection(set(frappe.get_roles(user))))

    if not is_finance:
        person = frappe.db.get_value("Cash Tracker Person", {"user": user}, "name") or ""

    cle_filter = f"AND cash_tracker_person = {frappe.db.escape(person)}" if person else ""
    ete_filter = f"AND cash_tracker_person = {frappe.db.escape(person)}" if person else ""

    # ── Summary totals ──────────────────────────────────────────────────────────
    cle_tot = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS total_out,
            COUNT(*) AS txn_count
        FROM `tabCash Ledger Entry`
        WHERE docstatus = 1 {cle_filter}
    """, as_dict=True)[0]

    ete_tot = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(CASE WHEN direction='Expense'       THEN amount ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN direction='Reimbursement' THEN amount ELSE 0 END), 0) AS total_reimbursed
        FROM `tabExpense Tracker Entry`
        WHERE docstatus = 1 {ete_filter}
    """, as_dict=True)[0]

    cash_in    = float(cle_tot.total_in)
    cash_out   = float(cle_tot.total_out)
    expenses   = float(ete_tot.total_expenses)
    reimbursed = float(ete_tot.total_reimbursed)

    summary = {
        "total_cash_in":  cash_in,
        "total_cash_out": cash_out,
        "cash_in_hand":   cash_in - cash_out,
        "total_expenses": expenses,
        "reimbursed":     reimbursed,
        "net_owed":       expenses - reimbursed,
        "txn_count":      int(cle_tot.txn_count),
    }

    # ── Monthly breakdown ───────────────────────────────────────────────────────
    monthly_cle = frappe.db.sql(f"""
        SELECT
            DATE_FORMAT(date, '%b %Y') AS month,
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS cash_out,
            COUNT(*) AS txn_count
        FROM `tabCash Ledger Entry`
        WHERE docstatus = 1 {cle_filter}
        GROUP BY DATE_FORMAT(date, '%b %Y')
    """, as_dict=True)

    monthly_ete = frappe.db.sql(f"""
        SELECT
            DATE_FORMAT(date, '%b %Y') AS month,
            COALESCE(SUM(CASE WHEN direction='Expense'       THEN amount ELSE 0 END), 0) AS expenses,
            COALESCE(SUM(CASE WHEN direction='Reimbursement' THEN amount ELSE 0 END), 0) AS reimbursed
        FROM `tabExpense Tracker Entry`
        WHERE docstatus = 1 {ete_filter}
        GROUP BY DATE_FORMAT(date, '%b %Y')
    """, as_dict=True)

    ete_month_map = {r.month: r for r in monthly_ete}
    all_months = set(r.month for r in monthly_cle) | set(ete_month_map.keys())

    cle_month_map = {r.month: r for r in monthly_cle}
    monthly = []
    for m in all_months:
        cle = cle_month_map.get(m)
        ete = ete_month_map.get(m)
        ci  = float(cle.cash_in  if cle else 0)
        co  = float(cle.cash_out if cle else 0)
        ep  = float(ete.expenses   if ete else 0)
        rb  = float(ete.reimbursed if ete else 0)
        monthly.append({
            "month":     m,
            "cash_in":   ci,
            "cash_out":  co,
            "net_cash":  ci - co,
            "expenses":  ep,
            "reimbursed": rb,
            "net_owed":  ep - rb,
            "txn_count": int(cle.txn_count) if cle else 0,
        })
    monthly.sort(key=lambda r: _month_sort_key(r["month"]))

    # ── Entity breakdown ────────────────────────────────────────────────────────
    entity_cle = frappe.db.sql(f"""
        SELECT
            COALESCE(entity, 'Unknown') AS entity,
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS cash_out
        FROM `tabCash Ledger Entry`
        WHERE docstatus = 1 {cle_filter}
        GROUP BY entity
    """, as_dict=True)

    entity_ete = frappe.db.sql(f"""
        SELECT
            COALESCE(entity, 'Unknown') AS entity,
            COALESCE(SUM(CASE WHEN direction='Expense'       THEN amount ELSE 0 END), 0) AS expenses,
            COALESCE(SUM(CASE WHEN direction='Reimbursement' THEN amount ELSE 0 END), 0) AS reimbursed
        FROM `tabExpense Tracker Entry`
        WHERE docstatus = 1 {ete_filter}
        GROUP BY entity
    """, as_dict=True)

    ete_ent_map = {r.entity: r for r in entity_ete}
    all_entities = set(r.entity for r in entity_cle) | set(ete_ent_map.keys())
    cle_ent_map  = {r.entity: r for r in entity_cle}

    entities = []
    for ent in sorted(all_entities):
        cle = cle_ent_map.get(ent)
        ete = ete_ent_map.get(ent)
        ci  = float(cle.cash_in  if cle else 0)
        co  = float(cle.cash_out if cle else 0)
        ep  = float(ete.expenses   if ete else 0)
        rb  = float(ete.reimbursed if ete else 0)
        entities.append({
            "entity":     ent,
            "cash_in":    ci,
            "cash_out":   co,
            "net_cash":   ci - co,
            "expenses":   ep,
            "reimbursed": rb,
            "net_owed":   ep - rb,
        })

    # ── Recent transactions from Cash Ledger Entry ─────────────────────────────
    tx_rows = frappe.db.sql(f"""
        SELECT name, date, entity, direction, amount, transaction_type,
               invoice_number, notes, running_balance, cash_tracker_person
        FROM `tabCash Ledger Entry`
        WHERE docstatus = 1 {cle_filter}
        ORDER BY date DESC, creation DESC
        LIMIT 75
    """, as_dict=True)

    transactions = []
    for r in tx_rows:
        transactions.append({
            "name":             r.name,
            "date":             str(r.date),
            "entity":           r.entity or "",
            "direction":        r.direction or "",
            "amount":           float(r.amount or 0),
            "transaction_type": r.transaction_type or "",
            "invoice_number":   r.invoice_number or "",
            "notes":            r.notes or "",
            "running_balance":  float(r.running_balance or 0),
        })

    # ── Expense Tracker Entries ────────────────────────────────────────────────
    ete_rows = frappe.db.sql(f"""
        SELECT name, date, entity, direction, amount, transaction_type,
               notes, cash_tracker_person, employee
        FROM `tabExpense Tracker Entry`
        WHERE docstatus = 1 {ete_filter}
        ORDER BY date DESC, creation DESC
        LIMIT 75
    """, as_dict=True)

    expense_entries = []
    for r in ete_rows:
        expense_entries.append({
            "name":             r.name,
            "date":             str(r.date),
            "entity":           r.entity or "",
            "direction":        r.direction or "",
            "amount":           float(r.amount or 0),
            "transaction_type": r.transaction_type or "",
            "notes":            r.notes or "",
            "employee":         r.employee or "",
        })

    # ── Finance person filter list ──────────────────────────────────────────────
    persons = []
    if is_finance:
        persons = frappe.db.sql(
            "SELECT name, name AS full_name FROM `tabCash Tracker Person` ORDER BY name",
            as_dict=True
        )

    return {
        "summary":         summary,
        "monthly":         monthly,
        "entities":        entities,
        "transactions":    transactions,
        "expense_entries": expense_entries,
        "persons":         persons,
        "is_finance":      is_finance,
        "current_person":  person or "",
    }


@frappe.whitelist()
def get_nikki_expense_summary():
    """
    Lightweight summary of Expense Tracker Entry data for the workspace widget.
    Non-Finance users see only their own CTP's entries.
    """
    user = frappe.session.user
    finance_roles = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}
    is_finance = bool(finance_roles.intersection(set(frappe.get_roles(user))))

    if is_finance:
        ctp_filter = ""
    else:
        person = frappe.db.get_value("Cash Tracker Person", {"user": user}, "name") or ""
        ctp_filter = f"AND cash_tracker_person = {frappe.db.escape(person)}" if person else "AND 1=0"

    totals = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(CASE WHEN direction='Expense'       THEN amount ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN direction='Reimbursement' THEN amount ELSE 0 END), 0) AS total_reimbursed,
            COUNT(*) AS entry_count
        FROM `tabExpense Tracker Entry`
        WHERE docstatus = 1 {ctp_filter}
    """, as_dict=True)[0]

    recent = frappe.db.sql(f"""
        SELECT name, date, direction, amount, transaction_type, notes, entity
        FROM `tabExpense Tracker Entry`
        WHERE docstatus = 1 {ctp_filter}
        ORDER BY date DESC, creation DESC
        LIMIT 10
    """, as_dict=True)

    for r in recent:
        r["date"]             = str(r["date"])
        r["amount"]           = float(r["amount"] or 0)
        r["transaction_type"] = r.get("transaction_type") or ""
        r["notes"]            = r.get("notes") or ""
        r["entity"]           = r.get("entity") or ""

    expenses   = float(totals.total_expenses)
    reimbursed = float(totals.total_reimbursed)

    return {
        "total_expenses":   expenses,
        "total_reimbursed": reimbursed,
        "net_owed":         expenses - reimbursed,
        "count":            int(totals.entry_count),
        "recent":           recent,
    }
