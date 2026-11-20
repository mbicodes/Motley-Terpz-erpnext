"""Keep referral partners on the portal and off the desk.

Frappe decides a user's type from their roles: one role with Desk Access makes
the user a System User, who lands on the desk after login. Frappe also creates
any role named in a DocType's permissions with Desk Access ON, which is how
"Referral Partner" picked it up on install. Everything here makes sure a
partner's user is a Website User whose only role is Referral Partner.
"""

import frappe
from frappe import _

PARTNER_ROLE = "Referral Partner"
PORTAL_HOME = "partner"
# Roles that mark a real staff account; such a user is never turned into a partner login.
STAFF_ROLES = {"System Manager", "Administrator"}


def ensure_partner_role():
    """Referral Partner: no Desk Access, lands on /partner."""
    if not frappe.db.exists("Role", PARTNER_ROLE):
        frappe.get_doc(
            {"doctype": "Role", "role_name": PARTNER_ROLE, "desk_access": 0, "home_page": PORTAL_HOME}
        ).insert(ignore_permissions=True)
        return
    role = frappe.get_doc("Role", PARTNER_ROLE)
    if role.desk_access or (role.home_page or "") != PORTAL_HOME:
        role.desk_access = 0
        role.home_page = PORTAL_HOME
        role.save(ignore_permissions=True)
        frappe.clear_cache()


def is_staff(user):
    """A real internal account: linked to an Employee, or a System Manager."""
    if user in ("Administrator", "Guest"):
        return True
    if frappe.db.exists("Employee", {"user_id": user}):
        return True
    roles = set(frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role"))
    return bool(roles & STAFF_ROLES)


def desk_roles_besides_partner(user):
    roles = frappe.get_all(
        "Has Role", filters={"parent": user, "parenttype": "User", "role": ["!=", PARTNER_ROLE]}, pluck="role"
    )
    if not roles:
        return []
    return frappe.get_all("Role", filters={"name": ["in", roles], "desk_access": 1}, pluck="name")


def make_partner_only(user):
    """Strip every role but Referral Partner and make the user a Website User.

    Returns the roles that were removed. Ends the user's sessions when they were a
    System User, so an open desk session cannot carry on.
    """
    ensure_partner_role()
    doc = frappe.get_doc("User", user)
    was_system_user = doc.user_type == "System User"
    removed = sorted({r.role for r in doc.roles if r.role != PARTNER_ROLE})
    has_partner = any(r.role == PARTNER_ROLE for r in doc.roles)
    if removed or not has_partner or doc.user_type != "Website User":
        doc.set("roles", [])
        doc.append("roles", {"role": PARTNER_ROLE})
        doc.user_type = "Website User"
        doc.role_profile_name = None
        doc.module_profile = None
        # stops ERPNext adding Customer / Supplier roles from a linked Contact on save
        frappe.flags.setting_role = True
        try:
            doc.save(ignore_permissions=True)
        finally:
            frappe.flags.setting_role = False
    assert_website_user(user)
    if was_system_user:
        from frappe.sessions import clear_sessions

        clear_sessions(user=user, force=True)
    return removed


def assert_website_user(user):
    user_type = frappe.db.get_value("User", user, "user_type")
    if user_type != "Website User":
        frappe.throw(
            _("Partner login {0} came out as a {1}. It must be a Website User; activation stopped.").format(
                user, user_type
            )
        )


def partner_users():
    users = set(frappe.get_all("Referral Partner", filters={"portal_user": ["is", "set"]}, pluck="portal_user"))
    users |= set(frappe.get_all("Has Role", filters={"role": PARTNER_ROLE, "parenttype": "User"}, pluck="parent"))
    return sorted(u for u in users if u and frappe.db.exists("User", u))


def repair_partner_users(verbose=True):
    """Turn every existing partner login into a Website User with only Referral Partner.

    Staff accounts (Employee-linked or System Manager) are left alone and reported.
    """
    ensure_partner_role()
    fixed, skipped = [], []
    for user in partner_users():
        if is_staff(user):
            skipped.append(user)
            continue
        before = frappe.db.get_value("User", user, "user_type")
        removed = make_partner_only(user)
        if removed or before != "Website User":
            fixed.append((user, before, removed))
    frappe.db.commit()
    if verbose:
        for user, before, removed in fixed:
            print(f"motley_referral: {user} {before} -> Website User; removed roles: {', '.join(removed) or '-'}")
        for user in skipped:
            print(f"motley_referral: SKIPPED staff account {user} (has Referral Partner role or is a portal_user)")
    return {"fixed": fixed, "skipped": skipped}
