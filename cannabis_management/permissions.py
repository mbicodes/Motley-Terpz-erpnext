import frappe

RESTRICTED_CUSTOMERS = {
    "nikki@motleyterpz.com": ["Motley Terpz"],
    # add more users here if needed later
}

def customer_query_conditions(user):
    if not user:
        user = frappe.session.user

    if "System Manager" in frappe.get_roles(user):
        return ""

    hidden = RESTRICTED_CUSTOMERS.get(user, [])
    if not hidden:
        return ""

    excluded = ", ".join([f'"{c}"' for c in hidden])
    return f"`tabCustomer`.`name` NOT IN ({excluded})"


def customer_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if "System Manager" in frappe.get_roles(user):
        return True

    hidden = RESTRICTED_CUSTOMERS.get(user, [])
    if doc.name in hidden:
        return False

    return True