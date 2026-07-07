import frappe


def run():
    if frappe.db.exists("Custom Field", "Batch-custom_procurement_status"):
        print("custom_procurement_status already exists on Batch")
        return

    doc = frappe.get_doc({
        "doctype": "Custom Field",
        "dt": "Batch",
        "fieldname": "custom_procurement_status",
        "label": "Procurement Status",
        "fieldtype": "Select",
        "options": "Active\nArchived",
        "default": "Active",
        "insert_after": "custom_metrc_last_synced",
        "description": "Drives the Active/Archived toggle for procurement cards on the CEO Dashboard — Farm page.",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("Created custom_procurement_status on Batch")
