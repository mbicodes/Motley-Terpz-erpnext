"""
Create two 'Before Delete' Server Scripts that cascade deletion:
  - Nikki Cash Ledger Entry deleted → cancel + delete linked Cash Ledger Entry
  - Nikki Expense Entry deleted     → cancel + delete linked Expense Tracker Entry

Run: bench --site stage.alltechvirtual.com execute cannabis_management.create_delete_cascade_scripts.run
"""
import frappe


NCLE_SCRIPT = """\
linked = doc.cash_ledger_entry
if linked and frappe.db.exists("Cash Ledger Entry", linked):
    current_status = frappe.db.get_value("Cash Ledger Entry", linked, "docstatus")
    if current_status == 1:
        cle_doc = frappe.get_doc("Cash Ledger Entry", linked)
        cle_doc.cancel()
    frappe.delete_doc("Cash Ledger Entry", linked, ignore_permissions=True, force=1)
    frappe.db.set_value("Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry", None)
"""

NEE_SCRIPT = """\
linked = doc.expense_tracker_entry
if linked and frappe.db.exists("Expense Tracker Entry", linked):
    current_status = frappe.db.get_value("Expense Tracker Entry", linked, "docstatus")
    if current_status == 1:
        ete_doc = frappe.get_doc("Expense Tracker Entry", linked)
        ete_doc.cancel()
    frappe.delete_doc("Expense Tracker Entry", linked, ignore_permissions=True, force=1)
    frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", None)
"""

SCRIPTS = [
    {
        "name":               "Nikki Cash → Delete Cash Ledger Entry",
        "script_type":        "DocType Event",
        "reference_doctype":  "Nikki Cash Ledger Entry",
        "doctype_event":      "Before Delete",
        "script":             NCLE_SCRIPT,
    },
    {
        "name":               "Nikki Expense → Delete Expense Tracker Entry",
        "script_type":        "DocType Event",
        "reference_doctype":  "Nikki Expense Entry",
        "doctype_event":      "Before Delete",
        "script":             NEE_SCRIPT,
    },
]


def run():
    frappe.set_user("Administrator")

    for s in SCRIPTS:
        if frappe.db.exists("Server Script", s["name"]):
            doc = frappe.get_doc("Server Script", s["name"])
            doc.script        = s["script"]
            doc.doctype_event = s["doctype_event"]
            doc.disabled      = 0
            doc.save(ignore_permissions=True)
            print(f"Updated: {s['name']}")
        else:
            doc = frappe.get_doc({"doctype": "Server Script", **s, "disabled": 0})
            doc.insert(ignore_permissions=True)
            print(f"Created: {s['name']}")

    frappe.db.commit()
    print("Done.")
