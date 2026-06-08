import frappe
from frappe import _


@frappe.whitelist()
def get_dashboard_data(person=None):
    """
    Returns summary cards, monthly breakdown, entity breakdown,
    transaction list, and pending approval count.
    Finance roles see all persons or a specific one via `person` filter.
    Cash Tracker Users always see only their own data — enforced server-side.
    """
    user = frappe.session.user
    finance_roles = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}
    is_finance = bool(finance_roles.intersection(set(frappe.get_roles(user))))

    # Cash Tracker Users always get their own person — ignore any passed `person`
    if not is_finance:
        person = frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")
        if not person:
            return _empty_response()

    person_filter_cash = f"AND c.cash_tracker_person = {frappe.db.escape(person)}" if person else ""
    person_filter_exp  = f"AND e.cash_tracker_person = {frappe.db.escape(person)}" if person else ""

    # ------------------------------------------------------------------ #
    # Summary totals
    # ------------------------------------------------------------------ #
    cash_totals = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS total_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS total_out,
            COUNT(*) AS txn_count
        FROM `tabCash Ledger Entry` c
        WHERE c.docstatus = 1
        {person_filter_cash}
    """, as_dict=True)[0]

    exp_totals = frappe.db.sql(f"""
        SELECT
            COALESCE(SUM(CASE WHEN direction='Expense'       THEN amount ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN direction='Reimbursement' THEN amount ELSE 0 END), 0) AS total_reimbursed,
            COUNT(*) AS exp_count
        FROM `tabExpense Tracker Entry` e
        WHERE e.docstatus = 1
        {person_filter_exp}
    """, as_dict=True)[0]

    # Pending approvals — submitted entries not yet approved
    pending_cash = frappe.db.sql(f"""
        SELECT COUNT(*) AS cnt FROM `tabCash Ledger Entry` c
        WHERE c.docstatus = 1 AND c.approval_status = 'Pending'
        {person_filter_cash}
    """, as_dict=True)[0].cnt or 0

    pending_exp = frappe.db.sql(f"""
        SELECT COUNT(*) AS cnt FROM `tabExpense Tracker Entry` e
        WHERE e.docstatus = 1 AND e.approval_status = 'Pending'
        {person_filter_exp}
    """, as_dict=True)[0].cnt or 0

    total_in         = float(cash_totals.total_in)
    total_out        = float(cash_totals.total_out)
    cash_in_hand     = total_in - total_out
    total_expenses   = float(exp_totals.total_expenses)
    total_reimbursed = float(exp_totals.total_reimbursed)
    net_owed         = total_expenses - total_reimbursed
    txn_count        = int(cash_totals.txn_count) + int(exp_totals.exp_count)

    # Display name for the hero card
    display_name = ""
    if person:
        display_name = frappe.db.get_value("Cash Tracker Person", person, "full_name") or person

    summary = {
        "total_cash_in":    total_in,
        "total_cash_out":   total_out,
        "cash_in_hand":     cash_in_hand,
        "total_expenses":   total_expenses,
        "reimbursed":       total_reimbursed,
        "net_owed":         net_owed,
        "total_txns":       txn_count,
        "pending_approvals": int(pending_cash) + int(pending_exp),
        "display_name":     display_name,
    }

    # ------------------------------------------------------------------ #
    # Recent transactions list (last 50, newest first)
    # ------------------------------------------------------------------ #
    cash_rows = frappe.db.sql(f"""
        SELECT
            name, date, entity, direction, amount, invoice_number,
            notes, receipt, approval_status, transaction_type,
            'Cash Ledger' AS source
        FROM `tabCash Ledger Entry` c
        WHERE c.docstatus = 1
        {person_filter_cash}
        ORDER BY date DESC, creation DESC
        LIMIT 50
    """, as_dict=True)

    exp_rows = frappe.db.sql(f"""
        SELECT
            name, date, entity, direction, amount, '' AS invoice_number,
            notes, receipt, approval_status, transaction_type,
            'Expense' AS source
        FROM `tabExpense Tracker Entry` e
        WHERE e.docstatus = 1
        {person_filter_exp}
        ORDER BY date DESC, creation DESC
        LIMIT 50
    """, as_dict=True)

    # Merge and sort by date desc
    all_txns = []
    for r in cash_rows:
        all_txns.append({
            "name":            r.name,
            "date":            str(r.date),
            "entity":          r.entity or "",
            "direction":       r.direction,
            "amount":          float(r.amount),
            "money_in":        float(r.amount) if r.direction == "Cash In" else 0,
            "money_out":       float(r.amount) if r.direction == "Cash Out" else 0,
            "invoice_number":  r.invoice_number or "",
            "notes":           r.notes or "",
            "receipt":         r.receipt or "",
            "approval_status": r.approval_status,
            "transaction_type": r.transaction_type,
            "source":          "Cash Ledger",
        })
    for r in exp_rows:
        all_txns.append({
            "name":            r.name,
            "date":            str(r.date),
            "entity":          r.entity or "",
            "direction":       r.direction,
            "amount":          float(r.amount),
            "money_in":        float(r.amount) if r.direction == "Reimbursement" else 0,
            "money_out":       float(r.amount) if r.direction == "Expense" else 0,
            "invoice_number":  "",
            "notes":           r.notes or "",
            "receipt":         r.receipt or "",
            "approval_status": r.approval_status,
            "transaction_type": r.transaction_type,
            "source":          "Expense",
        })

    all_txns.sort(key=lambda x: x["date"], reverse=True)
    transactions = all_txns[:50]

    # ------------------------------------------------------------------ #
    # Monthly breakdown
    # ------------------------------------------------------------------ #
    monthly_cash = frappe.db.sql(f"""
        SELECT
            month,
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS cash_out,
            COUNT(*) AS txn_count
        FROM `tabCash Ledger Entry` c
        WHERE c.docstatus = 1
        {person_filter_cash}
        GROUP BY month
    """, as_dict=True)

    monthly_exp = frappe.db.sql(f"""
        SELECT
            month,
            COALESCE(SUM(CASE WHEN direction='Expense'       THEN amount ELSE 0 END), 0) AS expenses,
            COALESCE(SUM(CASE WHEN direction='Reimbursement' THEN amount ELSE 0 END), 0) AS reimbursed
        FROM `tabExpense Tracker Entry` e
        WHERE e.docstatus = 1
        {person_filter_exp}
        GROUP BY month
    """, as_dict=True)

    monthly_map = {}
    for row in monthly_cash:
        m = row.month or "Unknown"
        monthly_map[m] = {
            "month": m,
            "cash_in":    float(row.cash_in),
            "cash_out":   float(row.cash_out),
            "net_cash":   float(row.cash_in) - float(row.cash_out),
            "expenses":   0.0,
            "reimbursed": 0.0,
            "net_owed":   0.0,
            "txn_count":  int(row.txn_count),
        }
    for row in monthly_exp:
        m = row.month or "Unknown"
        if m not in monthly_map:
            monthly_map[m] = {"month": m, "cash_in": 0.0, "cash_out": 0.0,
                               "net_cash": 0.0, "expenses": 0.0,
                               "reimbursed": 0.0, "net_owed": 0.0, "txn_count": 0}
        monthly_map[m]["expenses"]   = float(row.expenses)
        monthly_map[m]["reimbursed"] = float(row.reimbursed)
        monthly_map[m]["net_owed"]   = float(row.expenses) - float(row.reimbursed)

    monthly = sorted(monthly_map.values(), key=lambda r: _month_sort_key(r["month"]))

    # ------------------------------------------------------------------ #
    # Entity breakdown
    # ------------------------------------------------------------------ #
    entity_cash = frappe.db.sql(f"""
        SELECT
            entity,
            COALESCE(SUM(CASE WHEN direction='Cash In'  THEN amount ELSE 0 END), 0) AS cash_in,
            COALESCE(SUM(CASE WHEN direction='Cash Out' THEN amount ELSE 0 END), 0) AS cash_out
        FROM `tabCash Ledger Entry` c
        WHERE c.docstatus = 1
        {person_filter_cash}
        GROUP BY entity
    """, as_dict=True)

    entity_exp = frappe.db.sql(f"""
        SELECT
            entity,
            COALESCE(SUM(CASE WHEN direction='Expense'       THEN amount ELSE 0 END), 0) AS expenses,
            COALESCE(SUM(CASE WHEN direction='Reimbursement' THEN amount ELSE 0 END), 0) AS reimbursed
        FROM `tabExpense Tracker Entry` e
        WHERE e.docstatus = 1
        {person_filter_exp}
        GROUP BY entity
    """, as_dict=True)

    entity_map = {}
    for row in entity_cash:
        ent = row.entity or "Unknown"
        entity_map[ent] = {
            "entity":     ent,
            "cash_in":    float(row.cash_in),
            "cash_out":   float(row.cash_out),
            "net_cash":   float(row.cash_in) - float(row.cash_out),
            "expenses":   0.0,
            "reimbursed": 0.0,
            "net_owed":   0.0,
        }
    for row in entity_exp:
        ent = row.entity or "Unknown"
        if ent not in entity_map:
            entity_map[ent] = {"entity": ent, "cash_in": 0.0, "cash_out": 0.0,
                                "net_cash": 0.0, "expenses": 0.0,
                                "reimbursed": 0.0, "net_owed": 0.0}
        entity_map[ent]["expenses"]   = float(row.expenses)
        entity_map[ent]["reimbursed"] = float(row.reimbursed)
        entity_map[ent]["net_owed"]   = float(row.expenses) - float(row.reimbursed)

    entities = sorted(entity_map.values(), key=lambda r: r["entity"])

    # ------------------------------------------------------------------ #
    # Person list (Finance only — for the filter dropdown)
    # ------------------------------------------------------------------ #
    persons = []
    if is_finance:
        persons = frappe.db.get_all(
            "Cash Tracker Person", filters={"is_active": 1},
            fields=["name", "full_name"], order_by="full_name"
        )

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
    months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
              "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    try:
        parts = month_str.split()
        return int(parts[1]) * 100 + months.get(parts[0], 0)
    except Exception:
        return 0


def _empty_response():
    return {
        "summary": {
            "total_cash_in": 0, "total_cash_out": 0, "cash_in_hand": 0,
            "total_expenses": 0, "reimbursed": 0, "net_owed": 0,
            "total_txns": 0, "pending_approvals": 0, "display_name": "",
        },
        "monthly": [],
        "entities": [],
        "transactions": [],
        "persons": [],
        "is_finance": False,
        "current_person": None,
    }
