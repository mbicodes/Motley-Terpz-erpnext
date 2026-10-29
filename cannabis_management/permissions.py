import frappe

MANAGER_ROLES = {"System Manager", "Sales Manager", "Accounts Manager"}
SUPER_ADMIN_ROLE = "Super Admin"


def _sees_all_customers(user):
    if user == "Administrator":
        return True
    return SUPER_ADMIN_ROLE in frappe.get_roles(user)


def _is_sales_person(user):
    return bool(frappe.db.exists("Sales Person", {"custom_email": user}))


def _visible_owners(user):
    try:
        from crm.motley_terpz.access import visible_owners

        return visible_owners(user)
    except Exception:
        return {user}


def _sp_customer_subquery(user):
    owners = ", ".join(frappe.db.escape(o) for o in _visible_owners(user))
    return (
        "SELECT cl.custom_erp_customer"
        " FROM `tabCRM Lead` cl"
        f" WHERE cl.custom_account_owner IN ({owners})"
        "   AND cl.custom_erp_customer IS NOT NULL"
        "   AND cl.custom_erp_customer != ''"
    )


def _assign_conditions(alias, user):
    return " OR ".join(
        f"{alias}.`_assign` LIKE {frappe.db.escape('%' + o + '%')}"
        for o in _visible_owners(user)
    )


def _visible_customers_subquery(user):
    return (
        "SELECT c.name FROM `tabCustomer` c"
        f" WHERE ({_assign_conditions('c', user)})"
        f"    OR c.name IN ({_sp_customer_subquery(user)})"
    )


def _customer_visible(customer, user, assign=None):
    if not customer:
        return True

    owners = _visible_owners(user)
    if assign is None:
        assign = frappe.db.get_value("Customer", customer, "_assign") or ""
    if any(o in (assign or "") for o in owners):
        return True

    return bool(frappe.db.get_value(
        "CRM Lead",
        {"custom_erp_customer": customer, "custom_account_owner": ["in", list(owners)]},
        "name",
    ))


def customer_query_conditions(user):
    if not user:
        user = frappe.session.user

    if _sees_all_customers(user):
        return ""

    if not _is_sales_person(user):
        return ""

    return (
        "(" + _assign_conditions("`tabCustomer`", user)
        + f" OR `tabCustomer`.`name` IN ({_sp_customer_subquery(user)}))"
    )


def customer_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if _sees_all_customers(user):
        return True

    if ptype == "create":
        return True

    if not _is_sales_person(user):
        return True

    return _customer_visible(doc.name, user, assign=doc.get("_assign") or "")


def sales_invoice_query_conditions(user):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ""

    if _is_sales_person(user):
        return f"`tabSales Invoice`.`customer` IN ({_visible_customers_subquery(user)})"

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return ""

    return ""


def sales_invoice_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return True

    if _is_sales_person(user):
        if ptype == "create":
            return True
        return _customer_visible(doc.get("customer"), user)

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return True

    return True
