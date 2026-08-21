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


def _assign_conditions(alias, user):
    """OR-ed `_assign LIKE` fragment covering everyone in the visibility group."""
    return " OR ".join(
        f"{alias}.`_assign` LIKE {frappe.db.escape('%' + o + '%')}"
        for o in _visible_owners(user)
    )


def _visible_customers_subquery(user):
    """SQL subquery returning every Customer the user may see - assigned to
    anyone in their visibility group, OR linked to a CRM Lead that group owns.

    This is THE definition of "my customers" and must stay the single source of
    truth for anything derived from customer ownership (e.g. Sales Invoice).
    Only the `_assign` half matches anything today: CRM Lead's
    custom_account_owner is unpopulated site-wide (the CRM app writes
    lead_owner instead), which is exactly why Sales Invoice - which used to
    filter on the CRM Lead branch alone - showed an empty list to every
    sales person.
    """
    return (
        "SELECT c.name FROM `tabCustomer` c"
        f" WHERE ({_assign_conditions('c', user)})"
        f"    OR c.name IN ({_sp_customer_subquery(user)})"
    )


def _customer_visible(customer, user, assign=None):
    """Python-side twin of _visible_customers_subquery, for one customer.
    Pass `assign` when the caller already has the Customer's _assign value."""
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


# ── Sales Invoice ─────────────────────────────────────────────────────────────

def sales_invoice_query_conditions(user):
    if not user:
        user = frappe.session.user

    if user == "Administrator":
        return ""

    if _is_sales_person(user):
        # An invoice is visible exactly when its customer is visible - see
        # _visible_customers_subquery. Filtering on _sp_customer_subquery alone
        # hid every invoice from every sales person, because no CRM Lead has
        # custom_account_owner set.
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
        # Same rule as the list view, and group-aware: the old check compared
        # custom_account_owner to `user` only, ignoring shared visibility.
        return _customer_visible(doc.get("customer"), user)

    if set(frappe.get_roles(user)) & MANAGER_ROLES:
        return True

    return True
