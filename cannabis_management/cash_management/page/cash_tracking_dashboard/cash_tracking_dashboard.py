"""Backend for the Cash Tracking dashboard page.

Scoping rules (enforced server-side, never trust the client):
  * Full-view users (Administrator or any System Manager) see every person's
    entries and may switch between people via the filter.
  * Everyone else sees their own Cash Tracker Person, plus any Cash Tracker
    Person **shared** with them through Frappe's standard Share panel on that
    record. Sharing is the one lever a manager has here that needs no code and
    no role change: share the person, and its entries appear in the filter.
  * The person filter never offers, and get_entries never returns, anybody
    outside that set — whatever the client asks for is re-derived here.

A share grants *visibility*, never rights: it can let you read someone's Motley
entries, but never file one. Creating stays with permissions.can_use_motley and
the "Allow For Motley" tick on your own record.
"""

import frappe

from cannabis_management.cash_management.permissions import can_use_motley, is_cash_admin

# docstatus -> label
STATUS_MAP = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def _is_full_view(user=None):
    """Only cash admins (Administrator / MBI) see every person's data."""
    return is_cash_admin(user)


def _own_person(user=None):
    """The Cash Tracker Person linked to this user, if any."""
    user = user or frappe.session.user
    return frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")


def _shared_persons(user=None):
    """Cash Tracker Person records shared with this user via the Share panel."""
    user = user or frappe.session.user
    return frappe.share.get_shared("Cash Tracker Person", user=user, rights=["read"]) or []


def _visible_persons(user=None):
    """Every person this user may look at: their own first, then anything shared.

    Own first so that a user who suddenly has records shared with them still
    lands on their own entries by default.
    """
    user = user or frappe.session.user
    visible = []
    own = _own_person(user)
    if own:
        visible.append(own)
    for name in _shared_persons(user):
        if name not in visible:
            visible.append(name)
    return visible


def _can_view_motley(persons):
    """Motley rows are viewable when any person in view is flagged for Motley.

    A share hands over that person's view, Motley included — but only to look
    at. Filing a Motley entry still needs the viewer's own record ticked.
    """
    if not persons:
        return False
    return bool(
        frappe.db.exists("Cash Tracker Person", {"name": ["in", persons], "allow_for_motley": 1})
    )


@frappe.whitelist()
def get_persons():
    """Options for the person filter.

    Admins get all active people; regular users get only themselves.
    """
    if _is_full_view():
        persons = frappe.get_all(
            "Cash Tracker Person",
            filters={"is_active": 1},
            fields=["name", "full_name", "user"],
            order_by="full_name asc",
        )
        return {
            "is_admin": True,
            "persons": persons,
            "own": _own_person(),
            "allow_motley": True,
        }

    own = _own_person()
    visible = _visible_persons()
    persons = [
        frappe.db.get_value(
            "Cash Tracker Person", name, ["name", "full_name", "user"], as_dict=True
        )
        for name in visible
    ]
    return {
        "is_admin": False,
        "persons": [p for p in persons if p],
        "own": own,
        # Anything past the first entry arrived through the Share panel; the page
        # uses this to unlock the filter and label the shared options.
        "shared": [p for p in visible if p != own],
        # Drives the Motley toggle + "New Motley Cash" button in the page.
        # Viewing follows the people in view; creating follows can_use_motley.
        "allow_motley": _can_view_motley(visible),
        "can_create_motley": can_use_motley(),
    }


@frappe.whitelist()
def get_entries(tracker="personal", person=None, from_date=None, to_date=None):
    """Return cash-tracking rows + totals, scoped to the caller.

    tracker is "motley" or "personal" — the old "all" mode is gone, because
    Motley visibility is now a per-person right ("Allow For Motley") rather than
    something everyone shares. A user without that right asking for Motley data
    is served their Personal entries instead, never an error and never Motley.
    """
    is_admin = _is_full_view()

    if not is_admin:
        # Re-derive what this user may see; never trust the person the client
        # sent. An unknown or unshared person silently collapses to their own.
        visible = _visible_persons()
        if not visible:
            return {
                "rows": [], "totals": _empty_totals(),
                "is_admin": False, "tracker": "personal",
            }
        if tracker == "motley" and not _can_view_motley(visible):
            tracker = "personal"
        person = person if person in visible else (visible if not person else visible[0])
    else:
        if tracker == "motley" and not can_use_motley():
            tracker = "personal"
        person = person or None  # empty string -> all (admin only)

    rows = []
    if tracker == "motley":
        rows += _fetch_motley(person, from_date, to_date)
    else:
        rows += _fetch_personal(person, from_date, to_date)

    rows.sort(key=lambda r: (r.get("date") or "", r.get("name") or ""), reverse=True)
    return {
        "rows": rows,
        "totals": _compute_totals(rows),
        "is_admin": is_admin,
        # Echo back what was actually served, so the page can correct its toggle
        # if it asked for Motley without the right.
        "tracker": tracker,
    }


def _base_filters(person, from_date, to_date):
    # Only submitted entries are shown on the dashboard (never Draft/Cancelled).
    filters = [["docstatus", "=", 1]]
    if person:
        # A list arrives when a user with shared records views "All" — their own
        # person plus everything shared with them, and nothing else.
        if isinstance(person, (list, tuple, set)):
            filters.append(["cash_tracker_person", "in", list(person)])
        else:
            filters.append(["cash_tracker_person", "=", person])
    if from_date:
        filters.append(["transaction_date", ">=", from_date])
    if to_date:
        filters.append(["transaction_date", "<=", to_date])
    return filters


def _fetch_motley(person, from_date, to_date):
    recs = frappe.get_all(
        "Motley Cash Tracking",
        filters=_base_filters(person, from_date, to_date),
        fields=[
            "name", "transaction_date as date", "cash_tracker_person as person",
            "user", "transaction_type as category", "business",
            "money_in", "money_out", "docstatus", "transaction_notes as notes",
        ],
        order_by="transaction_date desc",
    )
    for r in recs:
        r["tracker"] = "Motley"
        r["status"] = STATUS_MAP.get(r.pop("docstatus"), "")
    return recs


def _fetch_personal(person, from_date, to_date):
    recs = frappe.get_all(
        "Personal Cash Tracking",
        filters=_base_filters(person, from_date, to_date),
        fields=[
            "name", "transaction_date as date", "cash_tracker_person as person",
            "user", "transaction_type as category", "reason as notes",
            "money_in", "money_out", "docstatus",
        ],
        order_by="transaction_date desc",
    )
    for r in recs:
        r["tracker"] = "Personal"
        r["business"] = ""
        r["status"] = STATUS_MAP.get(r.pop("docstatus"), "")
    return recs


def _empty_totals():
    return {"money_in": 0, "money_out": 0, "net": 0, "count": 0}


def _compute_totals(rows):
    money_in = sum((r.get("money_in") or 0) for r in rows)
    money_out = sum((r.get("money_out") or 0) for r in rows)
    return {
        "money_in": money_in,
        "money_out": money_out,
        "net": money_in - money_out,
        "count": len(rows),
    }
