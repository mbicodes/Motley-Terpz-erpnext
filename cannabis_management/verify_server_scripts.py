"""
Verify that the Nikki Server Scripts are saved correctly and test
the ETE creation logic on an existing Nikki Expense Entry.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.verify_server_scripts.run
"""
import frappe


def run():
    frappe.set_user("Administrator")

    # 1. Print the current Server Script content
    for script_name in ["Nikki Expense → Expense Tracker Entry", "Nikki Cash → Cash Ledger Entry"]:
        ss = frappe.get_doc("Server Script", script_name)
        print(f"\n=== {script_name} ===")
        print(f"  disabled: {ss.disabled}")
        print(f"  doctype_event: {ss.doctype_event}")
        print(f"  reference_doctype: {ss.reference_doctype}")
        print(f"  script (first 200 chars): {ss.script[:200]}")

    # 2. Test: create a Nikki Expense Entry via db_insert (bypasses payment entry),
    #    then manually run the Server Script logic to verify ETE creation.
    print("\n\n=== Testing ETE creation on db_inserted entry ===")

    # Set user to nikki so the Cash Tracker Person lookup works
    frappe.set_user("nikki@motleyterpz.com")

    # Create Nikki Expense Entry directly (bypassing all hooks)
    nee = frappe.new_doc("Nikki Expense Entry")
    nee.expense_type = "Motley"
    nee.transaction_date = "2026-06-08"
    nee.money_in = 0
    nee.money_out = 250.0
    nee.business = "Motley Terpz"
    nee.transaction_notes = "Server Script verify test — no receipt expense"
    nee.db_insert()
    frappe.db.commit()
    print(f"Created Nikki Expense Entry: {nee.name}")

    # Now simulate what the Server Script does
    from frappe.utils import getdate

    expense_tracker_entry = frappe.db.get_value("Nikki Expense Entry", nee.name, "expense_tracker_entry")
    print(f"expense_tracker_entry before script: {expense_tracker_entry}")

    if not expense_tracker_entry:
        doc = nee  # simulate doc available in Server Script context
        if doc.money_out and doc.money_out > 0:
            direction = "Expense"
            amount = doc.money_out
        elif doc.money_in and doc.money_in > 0:
            direction = "Reimbursement"
            amount = doc.money_in
        else:
            direction = None
            amount = None

        if direction and amount:
            person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")
            print(f"Cash Tracker Person: {person}")

            ete = frappe.new_doc("Expense Tracker Entry")
            ete.date = doc.transaction_date
            ete.month = getdate(doc.transaction_date).strftime("%b %Y")
            ete.direction = direction
            ete.amount = amount
            ete.receipt = doc.receipt or None
            ete.notes = ("[Web Form] Source: Nikki Expense Entry " + doc.name + ". " + (doc.transaction_notes or "")).strip()
            ete.company = doc.business or None
            ete.cash_tracker_person = person or None
            ete.transaction_type = "Reimbursement" if direction == "Reimbursement" else "Other"
            ete.entity = "Motley Terpz"

            ete.db_insert()
            frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)

            if person:
                try:
                    from cannabis_management.cash_management.utils.cash_utils import update_expense_balance, publish_realtime_balance
                    ete.docstatus = 1
                    update_expense_balance(ete, None)
                    publish_realtime_balance(ete, None)
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "ETE submit balance hooks failed")

            frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", ete.name)
            frappe.db.commit()

            print(f"\nETE created: {ete.name}")
            ete_from_db = frappe.get_doc("Expense Tracker Entry", ete.name)
            print(f"  docstatus: {ete_from_db.docstatus}")
            print(f"  direction: {ete_from_db.direction}")
            print(f"  amount: {ete_from_db.amount}")
            print(f"  cash_tracker_person: {ete_from_db.cash_tracker_person}")

            linked = frappe.db.get_value("Nikki Expense Entry", nee.name, "expense_tracker_entry")
            print(f"\nNikki Expense Entry expense_tracker_entry: {linked}")

            if ete_from_db.docstatus == 1 and linked == ete.name:
                print("\n✓ SUCCESS — ETE created and submitted, linked back to Nikki Expense Entry")
            else:
                print("\n✗ FAIL — check above")
