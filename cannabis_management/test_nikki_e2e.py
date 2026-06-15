"""
End-to-end test simulating Nikki's web form submission.
Tests both Expense (money_out, no receipt) and Reimbursement (money_in) cases.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.test_nikki_e2e.run
"""
import frappe


def run():
    # Use nikki's actual user account
    nikki_user = "nikki@motleyterpz.com"
    frappe.set_user(nikki_user)

    print(f"=== Testing as user: {nikki_user} ===\n")

    # --- Test 1: Expense (money_out, no receipt) ---
    print("--- Test 1: Expense entry (money_out=300, no receipt) ---")
    doc1 = frappe.get_doc({
        "doctype": "Nikki Expense Entry",
        "expense_type": "Motley",
        "transaction_date": "2026-06-08",
        "money_in": 0,
        "money_out": 300.0,
        "business": "Motley Terpz",
        "transaction_notes": "E2E test Expense — lab supplies",
    })
    doc1.insert(ignore_permissions=True)
    frappe.db.commit()

    doc1.reload()
    ete_name = frappe.db.get_value("Nikki Expense Entry", doc1.name, "expense_tracker_entry")
    print(f"  Nikki Expense Entry: {doc1.name}")
    print(f"  expense_tracker_entry: {ete_name}")

    if ete_name:
        ete = frappe.get_doc("Expense Tracker Entry", ete_name)
        print(f"  ETE docstatus={ete.docstatus} | direction={ete.direction} | amount={ete.amount} | person={ete.cash_tracker_person}")
        if ete.docstatus == 1:
            print("  ✓ SUCCESS: ETE created and submitted")
        else:
            print("  ✗ FAIL: ETE not submitted (docstatus != 1)")
    else:
        print("  ✗ FAIL: expense_tracker_entry not set")

    print()

    # --- Test 2: Reimbursement (money_in, no receipt needed) ---
    print("--- Test 2: Reimbursement entry (money_in=150) ---")
    doc2 = frappe.get_doc({
        "doctype": "Nikki Expense Entry",
        "expense_type": "Motley",
        "transaction_date": "2026-06-08",
        "money_in": 150.0,
        "money_out": 0,
        "business": "Motley Terpz",
        "transaction_notes": "E2E test Reimbursement — travel",
    })
    doc2.insert(ignore_permissions=True)
    frappe.db.commit()

    doc2.reload()
    ete_name2 = frappe.db.get_value("Nikki Expense Entry", doc2.name, "expense_tracker_entry")
    print(f"  Nikki Expense Entry: {doc2.name}")
    print(f"  expense_tracker_entry: {ete_name2}")

    if ete_name2:
        ete2 = frappe.get_doc("Expense Tracker Entry", ete_name2)
        print(f"  ETE docstatus={ete2.docstatus} | direction={ete2.direction} | amount={ete2.amount} | person={ete2.cash_tracker_person}")
        if ete2.docstatus == 1:
            print("  ✓ SUCCESS: ETE created and submitted")
        else:
            print("  ✗ FAIL: ETE not submitted (docstatus != 1)")
    else:
        print("  ✗ FAIL: expense_tracker_entry not set")

    print()

    # Check for any new error logs during this test
    errors = frappe.db.sql("""
        SELECT name, method, error
        FROM `tabError Log`
        ORDER BY creation DESC LIMIT 5
    """, as_dict=True)
    print("=== Recent Error Logs ===")
    for e in errors:
        print(f"  [{e.name}] {e.method}: {(e.error or '')[:200]}")
