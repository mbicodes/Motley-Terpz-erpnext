import frappe

def run():
    d = {
        "doctype": "Custom Field",
        "dt": "Item Default",
        "fieldname": "custom_asset_account",
        "label": "Asset Account",
        "fieldtype": "Link",
        "options": "Account",
        "insert_after": "income_account",
        "module": "Cannabis Management"
    }
    if not frappe.db.exists("Custom Field", "Item Default-custom_asset_account"):
        frappe.get_doc(d).insert()
        frappe.db.commit()
        print("Field Created")
    else:
        print("Field Exists")
