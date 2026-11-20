"""Reimbursement Change Request 1: permissions on sites that override Personal Cash
Tracking with Custom DocPerm (Role Permissions Manager). Custom DocPerm replaces the
DocType's own permissions entirely, so the JSON rows for these roles never apply there.
"""

import frappe

DOCTYPE = "Personal Cash Tracking"

ROWS = [
    # approvers act from the Safe panel: apply_workflow needs read / write / submit
    ("Reimbursement Approver", 0, {"read": 1, "write": 1, "submit": 1, "print": 1, "email": 1, "report": 1, "export": 1}),
    # Leo sees the pending rows and can open the entry
    ("Safe Cash Tracker", 0, {"read": 1, "print": 1, "email": 1, "report": 1}),
    # Paid From Safe / Safe (and Processed) are permlevel 1: Finance only
    ("Accounts Manager", 1, {"read": 1, "write": 1}),
    ("System Manager", 1, {"read": 1, "write": 1}),
]


def execute():
    if not frappe.db.count("Custom DocPerm", {"parent": DOCTYPE}):
        return  # the DocType JSON permissions apply as they are
    for role, permlevel, rights in ROWS:
        if not frappe.db.exists("Role", role):
            continue
        name = frappe.db.get_value("Custom DocPerm", {"parent": DOCTYPE, "role": role, "permlevel": permlevel, "if_owner": 0})
        if name:
            frappe.db.set_value("Custom DocPerm", name, rights)
        else:
            doc = frappe.new_doc("Custom DocPerm")
            doc.update({"parent": DOCTYPE, "parenttype": "DocType", "parentfield": "permissions",
                        "role": role, "permlevel": permlevel, **rights})
            doc.insert(ignore_permissions=True)
    frappe.clear_cache(doctype=DOCTYPE)
