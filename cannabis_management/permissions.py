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


def _visible_owners(user):
    """The user plus anyone they share visibility with.

    Single source of truth is crm.motley_terpz.access.SHARED_VISIBILITY_GROUPS,
    so a pairing configured for CRM leads/deals automatically applies to
    Customers too - previously the two sides disagreed, and a "shared" rep
    could see their partner's deals but not the customers behind them.

    Falls back to just the user if the CRM app is not installed.
    """
    try:
        from crm.motley_terpz.access import visible_owners

        return visible_owners(user)
    except Exception:
        return {user}


def _sp_customer_subquery(user):
    """SQL subquery returning customer names owned by the user's visibility group."""
    owners = ", ".join(frappe.db.escape(o) for o in _visible_owners(user))
    return (
        "SELECT cl.custom_erp_customer"
        " FROM `tabCRM Lead` cl"
        f" WHERE cl.custom_account_owner IN ({owners})"
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

    # Assignment check widened across the visibility group, so a shared pair
    # sees customers assigned to either of them.
    conditions = [
        f"`tabCustomer`.`_assign` LIKE {frappe.db.escape('%' + o + '%')}"
        for o in _visible_owners(user)
    ]
    conditions.append(f"`tabCustomer`.`name` IN ({_sp_customer_subquery(user)})")

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

    owners = _visible_owners(user)
    assign = doc.get("_assign") or ""
    if any(o in assign for o in owners):
        return True

    return bool(frappe.db.get_value(
        "CRM Lead",
        {"custom_erp_customer": doc.name, "custom_account_owner": ["in", list(owners)]},
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
