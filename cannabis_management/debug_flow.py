"""
Debug the Server Script error.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.debug_flow.run
"""
import frappe


def run():
    frappe.set_user("Administrator")

    # Get the most recent error logs
    errors = frappe.db.sql("""
        SELECT name, method, error, creation
        FROM `tabError Log`
        ORDER BY creation DESC LIMIT 15
    """, as_dict=True)
    print("=== Most Recent Error Logs ===")
    for e in errors:
        print(f"\n[{e.name}] {e.creation} | method: {e.method}")
        print((e.error or '')[:400])
