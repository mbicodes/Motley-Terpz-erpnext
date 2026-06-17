"""
Create the "AR Recon Snapshot" doctype used to track the unreconciled-customer
count day over day (one row per company-scope per day).

Run: bench --site stage.alltechvirtual.com execute cannabis_management.setup_ar_recon_snapshot.run
"""
import frappe

DOCTYPE = "AR Recon Snapshot"


def run():
    frappe.set_user("Administrator")
    if frappe.db.exists("DocType", DOCTYPE):
        print(f"DocType '{DOCTYPE}' already exists.")
        return

    doc = frappe.get_doc({
        "doctype": "DocType",
        "name": DOCTYPE,
        "module": "Cannabis Management",
        "custom": 1,
        "autoname": "prompt",
        "track_changes": 0,
        "fields": [
            {"fieldname": "snapshot_date", "label": "Snapshot Date", "fieldtype": "Date", "in_list_view": 1, "reqd": 1},
            {"fieldname": "company", "label": "Company Scope", "fieldtype": "Data", "in_list_view": 1, "reqd": 1},
            {"fieldname": "unreconciled_count", "label": "Unreconciled Count", "fieldtype": "Int", "in_list_view": 1},
            {"fieldname": "outstanding_total", "label": "Outstanding Total", "fieldtype": "Currency", "in_list_view": 1},
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
        ],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"Created DocType '{DOCTYPE}'")
