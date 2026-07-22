"""Backend for the Cash Tracking dashboard page.

Scoping rules (enforced server-side, never trust the client):
  * Full-view users (Administrator or any System Manager) see every person's
    entries and may switch between people via the filter.
  * Everyone else is locked to their own Cash Tracker Person — both the data
    they receive and the single option in their person filter.
"""

import frappe

from cannabis_management.cash_management.permissions import is_cash_admin

# docstatus -> label
STATUS_MAP = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def _is_full_view(user=None):
    """Only cash admins (Administrator / MBI) see every person's data."""
    return is_cash_admin(user)


def _own_person(user=None):
    """The Cash Tracker Person linked to this user, if any."""
    user = user or frappe.session.user
    return frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")


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
        return {"is_admin": True, "persons": persons, "own": _own_person()}

    own = _own_person()
    persons = []
    if own:
        persons = [
            frappe.db.get_value(
                "Cash Tracker Person", own, ["name", "full_name", "user"], as_dict=True
            )
        ]
    return {"is_admin": False, "persons": persons, "own": own}


@frappe.whitelist()
def get_entries(tracker="all", person=None, from_date=None, to_date=None):
    """Return unified cash-tracking rows + totals, scoped to the caller."""
    is_admin = _is_full_view()

    if not is_admin:
        # Force own person regardless of what the client sent.
        own = _own_person()
        if not own:
            return {"rows": [], "totals": _empty_totals(), "is_admin": False}
        person = own

    person = person or None  # empty string -> all (admin only)

    rows = []
    if tracker in ("all", "motley"):
        rows += _fetch_motley(person, from_date, to_date)
    if tracker in ("all", "personal"):
        rows += _fetch_personal(person, from_date, to_date)

    rows.sort(key=lambda r: (r.get("date") or "", r.get("name") or ""), reverse=True)
    return {"rows": rows, "totals": _compute_totals(rows), "is_admin": is_admin}


def _base_filters(person, from_date, to_date):
    # Only submitted entries are shown on the dashboard (never Draft/Cancelled).
    filters = [["docstatus", "=", 1]]
    if person:
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
            "user", "reason as category", "money_in", "money_out",
            "docstatus",
        ],
        order_by="transaction_date desc",
    )
    for r in recs:
        r["tracker"] = "Personal"
        r["business"] = ""
        r["notes"] = r.get("category")
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
