import frappe

FINANCE_ROLES = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}


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

def _sees_all_personal_cash(user):
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def personal_cash_tracking_query(user):
    """List-level filter: non-managers only see records they created."""
    user = user or frappe.session.user
    if _sees_all_personal_cash(user):
        return ""
    return f"`tabPersonal Cash Tracking`.owner = {frappe.db.escape(user)}"


def personal_cash_tracking_has_permission(doc, ptype="read", user=None):
    """Document-level gate: only the creator (or System Manager) can touch it."""
    user = user or frappe.session.user
    if _sees_all_personal_cash(user):
        return True
    if doc is None or isinstance(doc, str):
        return True  # doctype-level access is decided by role permissions
    return (doc.get("owner") or user) == user


# ── Motley Cash Tracking — strictly own records ─────────────────────────────

def motley_cash_tracking_query(user):
    """List-level filter: strictly own records. Only the Administrator
    account bypasses — System Managers do NOT see these entries."""
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    return f"`tabMotley Cash Tracking`.owner = {frappe.db.escape(user)}"


def motley_cash_tracking_has_permission(doc, ptype="read", user=None):
    """Document-level gate: only the creator (or the Administrator account)."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    if doc is None or isinstance(doc, str):
        return True  # doctype-level access is decided by role permissions
    return (doc.get("owner") or user) == user
