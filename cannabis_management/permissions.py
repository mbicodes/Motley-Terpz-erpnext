import json

import frappe

RESTRICTED_CUSTOMERS = {
    "nikki@motleyterpz.com": ["Motley Terpz"],
    # add more users here if needed later
}

MANAGER_ROLES = {"System Manager", "Sales Manager", "Accounts Manager"}


def customer_query_conditions(user):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ""

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return ""

    user_escaped = frappe.db.escape(user)
    assign_like = frappe.db.escape(f"%{user}%")

    conditions = [
        f"(`tabCustomer`.`_assign` LIKE {assign_like}"
        f" OR `tabCustomer`.`account_manager` = {user_escaped})"
    ]

    hidden = RESTRICTED_CUSTOMERS.get(user, [])
    if hidden:
        excluded = ", ".join([frappe.db.escape(c) for c in hidden])
        conditions.append(f"`tabCustomer`.`name` NOT IN ({excluded})")

    return " AND ".join(conditions)


def customer_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return True

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return True

    assigned = []
    if doc._assign:
        try:
            assigned = json.loads(doc._assign)
        except Exception:
            pass

    if user not in assigned and doc.account_manager != user:
        return False

    hidden = RESTRICTED_CUSTOMERS.get(user, [])
    return doc.name not in hidden
