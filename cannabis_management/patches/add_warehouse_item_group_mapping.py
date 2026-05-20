def execute():
    import frappe
    frappe.reload_doc(
        "cannabis_management",
        "doctype",
        "warehouse_item_group_account_mapping",
    )
