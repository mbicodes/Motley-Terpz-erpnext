import frappe

FINANCE_ROLES = {"Finance Manager", "Accounts Manager", "System Manager", "Administrator"}

CASH_ADMIN_USERS = {"Administrator", "mbi@alltechvirtual.com"}

FINANCE_TEAM_ROLES = {"Finance Manager", "Accounts Manager"}


def can_mark_processed(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(FINANCE_TEAM_ROLES.intersection(set(frappe.get_roles(user))))


def is_cash_admin(user=None):
    return (user or frappe.session.user) in CASH_ADMIN_USERS


def is_accounts_manager(user=None):
    user = user or frappe.session.user
    return "Accounts Manager" in frappe.get_roles(user)


def is_cash_full_view(user=None):
    user = user or frappe.session.user
    return is_cash_admin(user) or is_accounts_manager(user)


def _my_persons(user=None):
    user = user or frappe.session.user
    return frappe.get_all("Cash Tracker Person", filters={"user": user}, pluck="name")


def _get_person_for_user(user=None):
    user = user or frappe.session.user
    return frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")


def _is_finance_or_above(user=None):
    user = user or frappe.session.user
    return bool(FINANCE_ROLES.intersection(set(frappe.get_roles(user))))


def can_use_motley(user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    return bool(frappe.db.get_value(
        "Cash Tracker Person",
        {"user": user, "is_active": 1, "allow_for_motley": 1},
        "name",
    ))


def person_allows_motley(person):
    if not person:
        return False
    return bool(frappe.db.get_value("Cash Tracker Person", person, "allow_for_motley"))


def can_use_tsbc(user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    return bool(frappe.db.get_value(
        "Cash Tracker Person",
        {"user": user, "is_active": 1, "allow_for_tsbc": 1},
        "name",
    ))


def person_allows_tsbc(person):
    if not person:
        return False
    return bool(frappe.db.get_value("Cash Tracker Person", person, "allow_for_tsbc"))


def can_use_safe(user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    return bool(frappe.db.get_value(
        "Cash Tracker Person",
        {"user": user, "is_active": 1, "allow_for_safe": 1},
        "name",
    ))


def person_allows_safe(person):
    if not person:
        return False
    return bool(frappe.db.get_value("Cash Tracker Person", person, "allow_for_safe"))


def cash_ledger_entry_query(user):
    if _is_finance_or_above(user):
        return ""
    person = _get_person_for_user(user)
    if not person:
        return "1=0"
    return f"`tabCash Ledger Entry`.`cash_tracker_person` = {frappe.db.escape(person)}"


def expense_tracker_entry_query(user):
    if _is_finance_or_above(user):
        return ""
    person = _get_person_for_user(user)
    if not person:
        return "1=0"
    return f"`tabExpense Tracker Entry`.`cash_tracker_person` = {frappe.db.escape(person)}"


def cash_ledger_entry_has_permission(doc, ptype="read", user=None):
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


def expense_tracker_entry_has_permission(doc, ptype="read", user=None):
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


def personal_cash_tracking_query(user):
    user = user or frappe.session.user
    if is_cash_full_view(user):
        return ""
    conds = [f"`tabPersonal Cash Tracking`.owner = {frappe.db.escape(user)}"]
    persons = _my_persons(user)
    if persons:
        plist = ", ".join(frappe.db.escape(p) for p in persons)
        conds.append(f"`tabPersonal Cash Tracking`.cash_tracker_person IN ({plist})")
    return "(" + " OR ".join(conds) + ")"


def personal_cash_tracking_has_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    if ptype == "read" and is_accounts_manager(user):
        return True
    if ptype == "cancel":
        return False
    if doc is None or isinstance(doc, str):
        return True
    if (doc.get("owner") or user) == user:
        return True
    if ptype == "read" and doc.get("cash_tracker_person") in _my_persons(user):
        return True
    return False


def motley_cash_tracking_query(user):
    user = user or frappe.session.user
    if is_cash_full_view(user):
        return ""
    conds = [f"`tabMotley Cash Tracking`.owner = {frappe.db.escape(user)}"]
    persons = _my_persons(user)
    if persons:
        plist = ", ".join(frappe.db.escape(p) for p in persons)
        conds.append(f"`tabMotley Cash Tracking`.cash_tracker_person IN ({plist})")
    return "(" + " OR ".join(conds) + ")"


def motley_cash_tracking_has_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    if ptype == "read" and is_accounts_manager(user):
        return True
    if ptype == "cancel":
        return False
    if ptype in ("create", "write", "submit", "amend") and not can_use_motley(user):
        return False
    if doc is None or isinstance(doc, str):
        return True
    if (doc.get("owner") or user) == user:
        return True
    if ptype == "read" and doc.get("cash_tracker_person") in _my_persons(user):
        return True
    return False


def tsbc_cash_tracking_query(user):
    user = user or frappe.session.user
    if is_cash_full_view(user):
        return ""
    conds = [f"`tabTSBC Cash Tracking`.owner = {frappe.db.escape(user)}"]
    persons = _my_persons(user)
    if persons:
        plist = ", ".join(frappe.db.escape(p) for p in persons)
        conds.append(f"`tabTSBC Cash Tracking`.cash_tracker_person IN ({plist})")
    return "(" + " OR ".join(conds) + ")"


def tsbc_cash_tracking_has_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    if ptype == "read" and is_accounts_manager(user):
        return True
    if ptype == "cancel":
        return False
    if ptype in ("create", "write", "submit", "amend") and not can_use_tsbc(user):
        return False
    if doc is None or isinstance(doc, str):
        return True
    if (doc.get("owner") or user) == user:
        return True
    if ptype == "read" and doc.get("cash_tracker_person") in _my_persons(user):
        return True
    return False


def safe_cash_tracking_query(user):
    user = user or frappe.session.user
    if is_cash_full_view(user):
        return ""
    conds = [f"`tabSafe Cash Tracking`.owner = {frappe.db.escape(user)}"]
    persons = _my_persons(user)
    if persons:
        plist = ", ".join(frappe.db.escape(p) for p in persons)
        conds.append(f"`tabSafe Cash Tracking`.cash_tracker_person IN ({plist})")
    return "(" + " OR ".join(conds) + ")"


def safe_cash_tracking_has_permission(doc, ptype="read", user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    if ptype == "read" and is_accounts_manager(user):
        return True
    if ptype == "cancel":
        return False
    if ptype in ("create", "write", "submit", "amend") and not can_use_safe(user):
        return False
    if doc is None or isinstance(doc, str):
        return True
    if (doc.get("owner") or user) == user:
        return True
    if ptype == "read" and doc.get("cash_tracker_person") in _my_persons(user):
        return True
    return False


def cash_tracker_person_has_permission(doc, ptype="read", user=None):
    if ptype != "share":
        return True
    return (user or frappe.session.user) == "Administrator"


def docshare_validate(doc, method=None):
    if doc.share_doctype != "Cash Tracker Person":
        return

    if frappe.session.user != "Administrator":
        frappe.throw(
            frappe._("Only the Administrator can share a Cash Tracker Person."),
            frappe.PermissionError,
            title=frappe._("Sharing Restricted"),
        )

    if doc.share:
        doc.share = 0
        frappe.msgprint(
            frappe._(
                "\"Can Share\" was not granted: the right to share a Cash Tracker "
                "Person stays with the Administrator."
            ),
            indicator="orange",
            alert=True,
        )
