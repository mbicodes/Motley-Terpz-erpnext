"""
Revert the Nikki workspace realtime listener back to 'Nikki Cash Ledger Entry'.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.revert_nikki_realtime.run
"""
import frappe


def run():
    frappe.set_user("Administrator")
    block = frappe.get_doc("Custom HTML Block", "Nikki")
    script = block.script or ""

    OLD = 'data.doctype === "Cash Ledger Entry"'
    NEW = 'data.doctype === "Nikki Cash Ledger Entry"'

    if OLD in script:
        block.script = script.replace(OLD, NEW)
        block.save(ignore_permissions=True)
        frappe.db.commit()
        print("Reverted: realtime listener now watches 'Nikki Cash Ledger Entry'.")
    else:
        print("Pattern not found — may already be reverted.")
