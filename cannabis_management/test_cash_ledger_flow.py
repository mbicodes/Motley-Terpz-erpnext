"""
Test the Nikki Cash Ledger Entry → Cash Ledger Entry bridge.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.test_cash_ledger_flow.run
"""
import frappe


def run():
    frappe.set_user("nikki@motleyterpz.com")
    print(f"Running as: {frappe.session.user}\n")

    doc = frappe.get_doc({
        "doctype": "Nikki Cash Ledger Entry",
        "date": "2026-06-08",
        "entity": "Motley Terpz",
        "transaction_type": "Other",
        "direction": "Cash In",
        "amount": 1500.0,
        "notes": "Cash ledger flow test",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    doc.reload()
    cle_name = frappe.db.get_value("Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry")
    print(f"Nikki Cash Ledger Entry: {doc.name}")
    print(f"cash_ledger_entry: {cle_name}")

    if cle_name:
        cle = frappe.get_doc("Cash Ledger Entry", cle_name)
        print(f"CLE: entity={cle.entity} | direction={cle.direction} | amount={cle.amount} | docstatus={cle.docstatus}")
        print("✓ SUCCESS — Cash Ledger Entry auto-created (Finance-only draft)")
    else:
        print("✗ FAIL — cash_ledger_entry not set")

    errors = frappe.db.sql("""
        SELECT name, method FROM `tabError Log`
        WHERE method LIKE 'Nikki Cash%'
        ORDER BY creation DESC LIMIT 3
    """, as_dict=True)
    if errors:
        print("Recent Cash errors:", [e.method for e in errors])
