"""
Create 'Before Delete' Server Scripts for Cash Ledger Entry and Expense Tracker Entry.
When either is deleted, any linked Payment Entry or Journal Entry is also cancelled + deleted.

Run: bench --site stage.alltechvirtual.com execute cannabis_management.create_cle_ete_delete_scripts.run
"""
import frappe


def _delete_linked_script(doctype_label):
    return """\
def _cancel_and_delete(doctype, name):
    if not name:
        return
    if not frappe.db.exists(doctype, name):
        return
    status = frappe.db.get_value(doctype, name, "docstatus")
    if status == 1:
        linked = frappe.get_doc(doctype, name)
        linked.cancel()
    frappe.delete_doc(doctype, name, ignore_permissions=True, force=1)

_cancel_and_delete("Payment Entry", doc.payment_entry)
_cancel_and_delete("Journal Entry", doc.journal_entry)
"""


CLE_SCRIPT = """\
def _cancel_and_delete(doctype, name):
    if not name:
        return
    if not frappe.db.exists(doctype, name):
        return
    status = frappe.db.get_value(doctype, name, "docstatus")
    if status == 1:
        linked_doc = frappe.get_doc(doctype, name)
        linked_doc.cancel()
    frappe.delete_doc(doctype, name, ignore_permissions=True, force=1)

_cancel_and_delete("Payment Entry", doc.payment_entry)
_cancel_and_delete("Journal Entry", doc.journal_entry)
"""

ETE_SCRIPT = """\
def _cancel_and_delete(doctype, name):
    if not name:
        return
    if not frappe.db.exists(doctype, name):
        return
    status = frappe.db.get_value(doctype, name, "docstatus")
    if status == 1:
        linked_doc = frappe.get_doc(doctype, name)
        linked_doc.cancel()
    frappe.delete_doc(doctype, name, ignore_permissions=True, force=1)

_cancel_and_delete("Payment Entry", doc.payment_entry)
_cancel_and_delete("Journal Entry", doc.journal_entry)
"""

SCRIPTS = [
    {
        "name":              "Cash Ledger Entry → Delete PE/JE",
        "script_type":       "DocType Event",
        "reference_doctype": "Cash Ledger Entry",
        "doctype_event":     "Before Delete",
        "script":            CLE_SCRIPT,
    },
    {
        "name":              "Expense Tracker Entry → Delete PE/JE",
        "script_type":       "DocType Event",
        "reference_doctype": "Expense Tracker Entry",
        "doctype_event":     "Before Delete",
        "script":            ETE_SCRIPT,
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
