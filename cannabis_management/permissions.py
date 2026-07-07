import frappe

MANAGER_ROLES = {"System Manager", "Sales Manager", "Accounts Manager"}
SUPER_ADMIN_ROLE = "Super Admin"


def _sees_all_customers(user):
    """Administrator and 'Super Admin' are the only identities that see every
    customer regardless of assignment — same bypass used for CRM Lead/Deal."""
    if user == "Administrator":
        return True
    return SUPER_ADMIN_ROLE in frappe.get_roles(user)


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
# Visibility: the assign/CRM-Lead restriction only applies to users who are
# registered on the Sales Person list — for them, a Customer is visible only
# via Frappe's standard "Assign To" (`_assign`) or the CRM Lead they own.
# Users who are NOT on the Sales Person list see every Customer. Administrator
# and the "Super Admin" role bypass this regardless of Sales Person status.

def customer_query_conditions(user):
    if not user:
        user = frappe.session.user

    if _sees_all_customers(user):
        return ""

    if not _is_sales_person(user):
        return ""

    like = frappe.db.escape(f"%{user}%")
    conditions = [
        f"`tabCustomer`.`_assign` LIKE {like}",
        f"`tabCustomer`.`name` IN ({_sp_customer_subquery(user)})",
    ]

    return "(" + " OR ".join(conditions) + ")"


def customer_has_permission(doc, user=None, ptype="read"):
    if not user:
        user = frappe.session.user

    if _sees_all_customers(user):
        return True

    if ptype == "create":
        return True

    if not _is_sales_person(user):
        return True

    if user in (doc.get("_assign") or ""):
        return True

    return bool(frappe.db.get_value(
        "CRM Lead",
        {"custom_erp_customer": doc.name, "custom_account_owner": user},
        "name"
    ))


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
