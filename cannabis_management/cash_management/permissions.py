import frappe

FINANCE_ROLES = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}

# Users with full cross-person access to the cash tracking capture forms
# (Motley / Personal Cash Tracking): they read every person's records and are
# the only ones who may cancel a submitted entry. Everyone else — even holders
# of System Manager on this staging site — is restricted to their own records.
CASH_ADMIN_USERS = {"Administrator", "mbi@alltechvirtual.com"}


def is_cash_admin(user=None):
    return (user or frappe.session.user) in CASH_ADMIN_USERS


def _get_person_for_user(user=None):
    """Return the Cash Tracker Person name linked to this ERPNext user, or None."""
    user = user or frappe.session.user
    return frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")


def _is_finance_or_above(user=None):
    user = user or frappe.session.user
    return bool(FINANCE_ROLES.intersection(set(frappe.get_roles(user))))


# ── List-view filtering ────────────────────────────────────────────────────────

def cash_ledger_entry_query(user):
    """Cash Tracker Users see only their own entries in list views; Finance sees all."""
    if _is_finance_or_above(user):
        return ""
    person = _get_person_for_user(user)
    if not person:
        return "1=0"
    return f"`tabCash Ledger Entry`.`cash_tracker_person` = {frappe.db.escape(person)}"


def expense_tracker_entry_query(user):
    """Cash Tracker Users see only their own expense entries in list views; Finance sees all."""
    if _is_finance_or_above(user):
        return ""
    person = _get_person_for_user(user)
    if not person:
        return "1=0"
    return f"`tabExpense Tracker Entry`.`cash_tracker_person` = {frappe.db.escape(person)}"


# ── Document-level permission checks ──────────────────────────────────────────

def cash_ledger_entry_has_permission(doc, ptype="read", user=None):
    """
    Document-level gate for Cash Ledger Entry.
    - Finance roles: full access.
    - Everyone else: read only their own; cancel always denied.
    doc is None when Frappe checks list-level access — allow if user has a CTP.
    """
    user = user or frappe.session.user
    if _is_finance_or_above(user):
        return True

    if ptype == "cancel":
        return False

    # None or string = list/create level check (no specific document)
    if doc is None or isinstance(doc, str):
        return bool(_get_person_for_user(user))

    person = _get_person_for_user(user)
    if not person:
        return False
    return doc.get("cash_tracker_person") == person


def expense_tracker_entry_has_permission(doc, ptype="read", user=None):
    """
    Document-level gate for Expense Tracker Entry.
    - Finance roles: full access.
    - Everyone else: read/write/submit only their own; cancel always denied.
    doc is None when Frappe checks list-level access — allow if user has a CTP.
    """
    user = user or frappe.session.user
    if _is_finance_or_above(user):
        return True

    if ptype == "cancel":
        return False

    if doc is None or isinstance(doc, str):
        return bool(_get_person_for_user(user))

    person = _get_person_for_user(user)
    if not person:
        return False
    return doc.get("cash_tracker_person") == person


# ── Personal Cash Tracking — strictly own records ──────────────────────────

def personal_cash_tracking_query(user):
    """List-level filter: cash admins see all; everyone else only their own."""
    user = user or frappe.session.user
    if is_cash_admin(user):
        return ""
    return f"`tabPersonal Cash Tracking`.owner = {frappe.db.escape(user)}"


def personal_cash_tracking_has_permission(doc, ptype="read", user=None):
    """Document-level gate: cash admins have full access; everyone else may only
    touch their own records and can never cancel."""
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    if ptype == "cancel":
        return False
    if doc is None or isinstance(doc, str):
        return True  # doctype-level access is decided by role permissions
    return (doc.get("owner") or user) == user


# ── Motley Cash Tracking — strictly own records ─────────────────────────────

def motley_cash_tracking_query(user):
    """List-level filter: cash admins see all; everyone else only their own."""
    user = user or frappe.session.user
    if is_cash_admin(user):
        return ""
    return f"`tabMotley Cash Tracking`.owner = {frappe.db.escape(user)}"


def motley_cash_tracking_has_permission(doc, ptype="read", user=None):
    """Document-level gate: cash admins have full access; everyone else may only
    touch their own records and can never cancel."""
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    if ptype == "cancel":
        return False
    if doc is None or isinstance(doc, str):
        return True  # doctype-level access is decided by role permissions
    return (doc.get("owner") or user) == user
