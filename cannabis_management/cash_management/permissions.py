import frappe


def _get_person_for_user(user=None):
    """Return the Cash Tracker Person name linked to this ERPNext user, or None."""
    user = user or frappe.session.user
    return frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")


def _is_finance_or_above(user=None):
    user = user or frappe.session.user
    elevated = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}
    return bool(elevated.intersection(set(frappe.get_roles(user))))


def cash_ledger_entry_query(user):
    """Cash Tracker Users see only their own entries; Finance sees all."""
    if _is_finance_or_above(user):
        return ""
    person = _get_person_for_user(user)
    if not person:
        return "1=0"  # user has no Cash Tracker Person — see nothing
    return f"`tabCash Ledger Entry`.`cash_tracker_person` = {frappe.db.escape(person)}"


def expense_tracker_entry_query(user):
    """Cash Tracker Users see only their own expense entries; Finance sees all."""
    if _is_finance_or_above(user):
        return ""
    person = _get_person_for_user(user)
    if not person:
        return "1=0"
    return f"`tabExpense Tracker Entry`.`cash_tracker_person` = {frappe.db.escape(person)}"
