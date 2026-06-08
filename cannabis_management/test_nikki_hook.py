"""Run: bench --site stage.alltechvirtual.com execute cannabis_management.test_nikki_hook.run"""
import frappe
from frappe.utils import getdate


def run():
    frappe.set_user("Administrator")
    doc = frappe.get_doc("Nikki Expense Entry", "NIKKIEXP-2026-00013")

    print(f"money_in={doc.money_in} money_out={doc.money_out} business={doc.business}")

    # Determine direction/amount
    if doc.money_out and doc.money_out > 0:
        direction, amount = "Expense", doc.money_out
    elif doc.money_in and doc.money_in > 0:
        direction, amount = "Reimbursement", doc.money_in
    else:
        print("No amount — skipping")
        return

    person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")
    print(f"direction={direction} amount={amount} person={person}")

    ete = frappe.new_doc("Expense Tracker Entry")
    ete.date = doc.transaction_date
    ete.month = getdate(doc.transaction_date).strftime("%b %Y")
    ete.direction = direction
    ete.amount = amount
    ete.receipt = doc.receipt or None
    ete.notes = f"[Web Form] Source: Nikki Expense Entry {doc.name}. {doc.transaction_notes or ''}".strip()
    ete.company = doc.business or None
    ete.cash_tracker_person = person or None
    ete.transaction_type = "Reimbursement" if direction == "Reimbursement" else "Other"

    print("About to db_insert...")
    ete.db_insert()
    print(f"db_insert done — name={ete.name}")

    frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)
    ete.docstatus = 1
    print("Set docstatus=1")

    if person:
        try:
            from cannabis_management.cash_management.utils.cash_utils import (
                update_expense_balance, publish_realtime_balance
            )
            update_expense_balance(ete, None)
            publish_realtime_balance(ete, None)
            print("Balance hooks ran ok")
        except Exception:
            import traceback
            print("Balance hook error:", traceback.format_exc())

    frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", ete.name)
    frappe.db.commit()
    print(f"Done — ETE={ete.name} linked on {doc.name}")
