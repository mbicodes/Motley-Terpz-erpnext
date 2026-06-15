"""
Check for error logs related to the Cash Ledger Server Script.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.check_cash_error.run
"""
import frappe


def run():
    frappe.set_user("Administrator")

    # All recent error logs
    errors = frappe.db.sql("""
        SELECT name, method, error, creation
        FROM `tabError Log`
        ORDER BY creation DESC LIMIT 10
    """, as_dict=True)
    print("=== Most Recent Error Logs ===")
    for e in errors:
        print(f"\n[{e.name}] {e.creation} | {e.method}")
        print((e.error or '')[:600])

    # Check the cash entry we just created
    cash = frappe.db.sql("""
        SELECT name, date, entity, amount, cash_ledger_entry
        FROM `tabNikki Cash Ledger Entry`
        ORDER BY creation DESC LIMIT 3
    """, as_dict=True)
    print("\n=== Recent Nikki Cash Ledger Entries ===")
    for c in cash:
        print(f"  {c.name} | entity={c.entity} | amount={c.amount} | cle={c.cash_ledger_entry}")

    # Check CLE table
    cles = frappe.db.sql("""
        SELECT name, entity, direction, amount, creation
        FROM `tabCash Ledger Entry`
        ORDER BY creation DESC LIMIT 3
    """, as_dict=True)
    print("\n=== Recent Cash Ledger Entries ===")
    for c in cles:
        print(f"  {c.name} | entity={c.entity} | direction={c.direction} | amount={c.amount}")
