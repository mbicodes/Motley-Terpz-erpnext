"""
Diagnose the Nikki expense tracker flow.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.diagnose.run
"""
import frappe


def run():
    frappe.set_user("Administrator")

    # 1. List all Cash Tracker Persons
    persons = frappe.db.sql("""
        SELECT name, user, employee, is_active
        FROM `tabCash Tracker Person`
        ORDER BY name
    """, as_dict=True)
    print("=== Cash Tracker Persons ===")
    for p in persons:
        print(f"  {p.name} | user={p.user} | employee={p.employee} | active={p.is_active}")

    # 2. Check NIKKIEXP-2026-00013 in detail
    entry = frappe.db.sql("""
        SELECT name, owner, expense_type, money_in, money_out, business,
               expense_tracker_entry, payment_entry
        FROM `tabNikki Expense Entry`
        WHERE name = 'NIKKIEXP-2026-00013'
    """, as_dict=True)
    print("\n=== NIKKIEXP-2026-00013 ===")
    for r in entry:
        print(r)

    # 3. Recent Error Logs
    errors = frappe.db.sql("""
        SELECT name, method, error
        FROM `tabError Log`
        ORDER BY creation DESC LIMIT 10
    """, as_dict=True)
    print("\n=== Recent Error Logs ===")
    for e in errors:
        snippet = (e.error or '')[:300]
        if 'Nikki' in snippet or 'expense' in snippet.lower() or 'cash_tracker' in snippet.lower():
            print(f"  [{e.name}] method={e.method}")
            print(f"  {snippet[:200]}")
            print()

    # 4. Recent Expense Tracker Entries
    etes = frappe.db.sql("""
        SELECT name, date, direction, amount, cash_tracker_person, docstatus, creation
        FROM `tabExpense Tracker Entry`
        ORDER BY creation DESC LIMIT 5
    """, as_dict=True)
    print("=== Recent Expense Tracker Entries ===")
    for e in etes:
        print(f"  {e.name} | {e.direction} | {e.amount} | person={e.cash_tracker_person} | docstatus={e.docstatus}")
