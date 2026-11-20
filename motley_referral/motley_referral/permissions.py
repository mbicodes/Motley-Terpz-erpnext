"""Scopes the portal role (Referral Partner) to its own records, and keeps every query of a partner
filtered in Python. Desk roles are unaffected."""
import frappe

DESK_ROLES = {"System Manager", "Referral Manager", "Accounts Manager"}


def is_partner_only(user):
    roles = set(frappe.get_roles(user))
    return "Referral Partner" in roles and not (roles & DESK_ROLES) and user != "Administrator"


def partner_of(user):
    return frappe.db.get_value("Referral Partner", {"portal_user": user, "status": ["in", ["Active", "Terminated"]]}, "name")


def _cond(doctype, field):
    def fn(user=None):
        user = user or frappe.session.user
        if not is_partner_only(user):
            return ""
        p = partner_of(user)
        return f"`tab{doctype}`.`{field}` = {frappe.db.escape(p)}" if p else "1=0"
    return fn


def _has(field):
    def fn(doc, user=None, permission_type=None):
        user = user or frappe.session.user
        if not is_partner_only(user):
            return None
        p = partner_of(user)
        if not p:
            return False
        if permission_type in ("write", "delete", "submit", "cancel", "amend"):
            return False
        return (doc.name if field == "name" else doc.get(field)) == p
    return fn


referral_partner_query = _cond("Referral Partner", "name")
partner_referral_query = _cond("Partner Referral", "referral_partner")
ledger_query = _cond("Referral Commission Ledger", "referral_partner")


def statement_query(user=None):
    user = user or frappe.session.user
    if not is_partner_only(user):
        return ""
    p = partner_of(user)
    if not p:
        return "1=0"
    return f"`tabReferral Commission Statement`.`referral_partner` = {frappe.db.escape(p)} and `tabReferral Commission Statement`.`docstatus` = 1 and `tabReferral Commission Statement`.`status` in ('Approved','Paid','Carried Forward')"


referral_partner_has = _has("name")
partner_referral_has = _has("referral_partner")
ledger_has = _has("referral_partner")


def statement_has(doc, user=None, permission_type=None):
    r = _has("referral_partner")(doc, user, permission_type)
    if r:
        return doc.docstatus == 1 and doc.status in ("Approved", "Paid", "Carried Forward")
    return r
