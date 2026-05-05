import frappe


def create_custom_fields():
    """Create custom fields required for Sales Order approval workflow."""
    if not frappe.db.exists("Custom Field", "Sales Order-custom_approval_status"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Sales Order",
            "fieldname": "custom_approval_status",
            "label": "Approval Status",
            "fieldtype": "Select",
            "options": "\nPending Approval\nApproved\nRejected",
            "insert_after": "custom_mode_of_payment",
            "read_only": 1,
            "bold": 1,
            "in_list_view": 0,
            "no_copy": 1,
        }).insert(ignore_permissions=True)
        frappe.db.commit()
        print("✅  custom_approval_status field created on Sales Order")
    else:
        print("ℹ️   custom_approval_status field already exists")
