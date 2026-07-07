import frappe


def run():
    if frappe.db.exists("Role", "Farm Manager"):
        print("Farm Manager role already exists")
        return

    frappe.get_doc({
        "doctype": "Role",
        "role_name": "Farm Manager",
        "desk_access": 1,
        "is_custom": 1,
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("Created Farm Manager role")
