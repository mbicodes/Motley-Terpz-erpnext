"""
End-to-end test: insert a Nikki Expense Entry and verify Expense Tracker Entry is auto-created + submitted.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.test_e2e.run
"""
import frappe


def run():
    frappe.set_user("Administrator")

    # Create a new Nikki Expense Entry simulating a web form submission
    doc = frappe.get_doc({
        "doctype": "Nikki Expense Entry",
        "expense_type": "Motley",
        "transaction_date": "2026-06-08",
        "money_in": 0,
        "money_out": 500.0,
        "business": "Motley Terpz",
        "transaction_notes": "E2E test — lab supplies",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    print(f"Created Nikki Expense Entry: {doc.name}")
    print(f"expense_tracker_entry field: {doc.expense_tracker_entry}")

    # Reload to see the updated value written by the Server Script
    doc.reload()
    ete_name = doc.expense_tracker_entry
    print(f"After reload — expense_tracker_entry: {ete_name}")

    if ete_name:
        ete = frappe.get_doc("Expense Tracker Entry", ete_name)
        print(f"ETE name={ete.name}  docstatus={ete.docstatus}  direction={ete.direction}  amount={ete.amount}  company={ete.company}")
        print("SUCCESS — Expense Tracker Entry auto-created and submitted" if ete.docstatus == 1 else "PARTIAL — not submitted")
    else:
        print("FAIL — expense_tracker_entry not set on Nikki Expense Entry")
