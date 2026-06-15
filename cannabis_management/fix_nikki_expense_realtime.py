"""
Update the Nikki workspace realtime listener to watch 'Nikki Expense Entry'
instead of 'Expense Tracker Entry'.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.fix_nikki_expense_realtime.run
"""
import frappe


def run():
    frappe.set_user("Administrator")
    block = frappe.get_doc("Custom HTML Block", "Nikki")
    script = block.script or ""

    OLD = 'data.doctype === "Nikki Expense Entry" || data.doctype === "Expense Tracker Entry"'
    NEW = 'data.doctype === "Nikki Expense Entry"'

    if OLD in script:
        block.script = script.replace(OLD, NEW)
        block.save(ignore_permissions=True)
        frappe.db.commit()
        print("Updated: realtime listener now watches 'Nikki Expense Entry' only.")
    elif 'data.doctype === "Nikki Expense Entry"' in script:
        print("Already watching 'Nikki Expense Entry' — no change needed.")
    else:
        print("WARNING: pattern not found in script.")
