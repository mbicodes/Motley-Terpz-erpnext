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


# ── Motley eligibility ────────────────────────────────────────────────────────
# "Allow For Motley" on Cash Tracker Person is the single switch deciding who may
# file Motley entries at all. It gates three things, all from this one helper:
#   1. creating / saving a Motley Cash Tracking document (motley_cash_tracking.py)
#   2. the doc-level permission check below
#   3. the Motley filter + "New Motley Cash" button on the Cash Tracking page
# Personal Cash Tracking is deliberately untouched by it.

def can_use_motley(user=None):
    """True if this user may file Motley entries. Cash admins always may."""
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    return bool(frappe.db.get_value(
        "Cash Tracker Person",
        {"user": user, "is_active": 1, "allow_for_motley": 1},
        "name",
    ))


def person_allows_motley(person):
    """True if a given Cash Tracker Person is flagged for Motley entries."""
    if not person:
        return False
    return bool(frappe.db.get_value("Cash Tracker Person", person, "allow_for_motley"))


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
    touch their own records and can never cancel.

    Writing also requires "Allow For Motley" on the user's Cash Tracker Person.
    Reading is left open to the owner so someone whose flag is later revoked can
    still see the entries they already filed.
    """
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    if ptype == "cancel":
        return False
    if ptype in ("create", "write", "submit", "amend") and not can_use_motley(user):
        return False
    if doc is None or isinstance(doc, str):
        return True  # doctype-level access is decided by role permissions
    return (doc.get("owner") or user) == user
