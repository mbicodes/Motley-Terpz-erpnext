import frappe

MANAGER_ROLES = {"System Manager", "Sales Manager", "Accounts Manager"}


def _is_sales_person(user):
    """Return True if the user's email is registered on the Sales Person list."""
    return bool(frappe.db.exists("Sales Person", {"custom_email": user}))


def _sp_customer_subquery(user):
    """SQL subquery returning customer names assigned to this Sales Person."""
    u = frappe.db.escape(user)
    return (
        "SELECT cl.custom_erp_customer"
        " FROM `tabCRM Lead` cl"
        f" WHERE cl.custom_account_owner = {u}"
        "   AND cl.custom_erp_customer IS NOT NULL"
        "   AND cl.custom_erp_customer != ''"
    )


# ── Customer ──────────────────────────────────────────────────────────────────

def customer_query_conditions(user):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ""

    # SP condition takes priority — checked before role bypass so that a
    # Sales Person with a broad role (e.g. Sales Manager) is still restricted
    # to only their assigned customers.
    if _is_sales_person(user):
        return f"`tabCustomer`.`name` IN ({_sp_customer_subquery(user)})"

    # Not a Sales Person: system managers see everything; everyone else gets
    # no extra restriction (standard role permissions apply).
    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return ""

    return ""


def customer_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return True

    if _is_sales_person(user):
        return bool(frappe.db.get_value(
            "CRM Lead",
            {"custom_erp_customer": doc.name, "custom_account_owner": user},
            "name"
        ))

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return True

    return True


# ── Sales Invoice ─────────────────────────────────────────────────────────────

def sales_invoice_query_conditions(user):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ""

    if _is_sales_person(user):
        return f"`tabSales Invoice`.`customer` IN ({_sp_customer_subquery(user)})"

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return ""

    return ""


def sales_invoice_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return True

    if _is_sales_person(user):
        return bool(frappe.db.get_value(
            "CRM Lead",
            {"custom_erp_customer": doc.customer, "custom_account_owner": user},
            "name"
        ))

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return True

    return True
