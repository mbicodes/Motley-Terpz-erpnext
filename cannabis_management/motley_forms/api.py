import frappe

@frappe.whitelist(allow_guest=False)
def get_current_employee():
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user},
        ["name", "employee_name"],
        as_dict=True
    )
    return employee