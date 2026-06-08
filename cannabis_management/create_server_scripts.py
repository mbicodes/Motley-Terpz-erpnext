"""
Create Server Scripts for Nikki web-form → Expense/Cash draft creation.
Server Scripts are stored in DB — no worker restart needed.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.create_server_scripts.run
"""
import frappe


EXPENSE_SCRIPT = '''
from frappe.utils import getdate

doc = frappe.get_doc(frappe.form_dict.doctype, frappe.form_dict.docname) if frappe.form_dict.get("docname") else doc

if doc.money_out and doc.money_out > 0:
    direction = "Expense"
    amount = doc.money_out
elif doc.money_in and doc.money_in > 0:
    direction = "Reimbursement"
    amount = doc.money_in
else:
    # nothing to do
    pass
else:
    person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")

    ete = frappe.new_doc("Expense Tracker Entry")
    ete.date = doc.transaction_date
    from frappe.utils import getdate
    ete.month = getdate(doc.transaction_date).strftime("%b %Y")
    ete.direction = direction
    ete.amount = amount
    ete.receipt = doc.receipt or None
    ete.notes = ("[Web Form] Source: Nikki Expense Entry " + doc.name + ". " + (doc.transaction_notes or "")).strip()
    ete.company = doc.business or None
    ete.cash_tracker_person = person or None
    ete.transaction_type = "Reimbursement" if direction == "Reimbursement" else "Other"
    ete.db_insert()

    frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)
    ete.docstatus = 1

    if person:
        try:
            from cannabis_management.cash_management.utils.cash_utils import update_expense_balance, publish_realtime_balance
            update_expense_balance(ete, None)
            publish_realtime_balance(ete, None)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Expense Tracker Submit Failed")

    frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", ete.name)
'''


def run():
    frappe.set_user("Administrator")

    # Build the correct expense script
    expense_script = '''
if doc.money_out and doc.money_out > 0:
    direction = "Expense"
    amount = doc.money_out
elif doc.money_in and doc.money_in > 0:
    direction = "Reimbursement"
    amount = doc.money_in
else:
    direction = None
    amount = 0

if direction and amount:
    person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")
    from frappe.utils import getdate
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
    ete.db_insert()
    frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)
    ete.docstatus = 1
    if person:
        try:
            from cannabis_management.cash_management.utils.cash_utils import update_expense_balance, publish_realtime_balance
            update_expense_balance(ete, None)
            publish_realtime_balance(ete, None)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Expense Tracker Submit Failed")
    frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", ete.name)
'''

    cash_script = '''
from frappe.utils import getdate
person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")
cle = frappe.new_doc("Cash Ledger Entry")
cle.date = doc.date
cle.month = getdate(doc.date).strftime("%b %Y")
cle.entity = doc.entity
cle.transaction_type = doc.transaction_type
cle.direction = doc.direction
cle.amount = doc.amount
cle.invoice_number = doc.invoice_number or None
cle.receipt = doc.receipt or None
cle.notes = ("[Web Form] Source: Nikki Cash Ledger Entry " + doc.name + ". " + (doc.notes or "")).strip()
cle.cash_tracker_person = person or None
cle.db_insert()
frappe.db.set_value("Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry", cle.name)
'''

    for name, doctype, event, script in [
        ("Nikki Expense → Expense Tracker Entry", "Nikki Expense Entry", "After Insert", expense_script),
        ("Nikki Cash → Cash Ledger Entry", "Nikki Cash Ledger Entry", "After Insert", cash_script),
    ]:
        existing = frappe.db.get_value("Server Script", {"name": name})
        if existing:
            ss = frappe.get_doc("Server Script", name)
            ss.script = script
            ss.save(ignore_permissions=True)
            print(f"Updated: {name}")
        else:
            ss = frappe.get_doc({
                "doctype": "Server Script",
                "name": name,
                "script_type": "DocType Event",
                "reference_doctype": doctype,
                "doctype_event": event,
                "script": script,
                "disabled": 0,
            })
            ss.insert(ignore_permissions=True)
            print(f"Created: {name}")

    frappe.db.commit()
    print("Done.")
