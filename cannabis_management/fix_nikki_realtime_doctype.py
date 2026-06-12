"""
Update the Nikki workspace Custom HTML Block so its realtime listener
watches 'Cash Ledger Entry' instead of 'Nikki Cash Ledger Entry'.

Run:
  bench --site stage.alltechvirtual.com execute cannabis_management.fix_nikki_realtime_doctype.run
"""
import frappe


def run():
    frappe.set_user("Administrator")
    block = frappe.get_doc("Custom HTML Block", "Nikki")
    script = block.script or ""

    OLD = 'data.doctype === "Nikki Cash Ledger Entry"'
    NEW = 'data.doctype === "Cash Ledger Entry"'

    if OLD in script:
        block.script = script.replace(OLD, NEW)
        block.save(ignore_permissions=True)
        frappe.db.commit()
        print("Updated: realtime listener now watches 'Cash Ledger Entry'.")
    else:
        print("No change needed — pattern not found (may already be updated).")
