import frappe

from cannabis_management.cash_management.permissions import (
    can_mark_processed,
    can_use_motley,
    can_use_safe,
    can_use_tsbc,
    is_cash_admin,
)

STATUS_MAP = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def _is_full_view(user=None):
    user = user or frappe.session.user
    if is_cash_admin(user):
        return True
    return "Accounts Manager" in frappe.get_roles(user)


def _own_person(user=None):
    user = user or frappe.session.user
    return frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")


def _shared_persons(user=None):
    user = user or frappe.session.user
    return frappe.share.get_shared("Cash Tracker Person", user=user, rights=["read"]) or []


def _visible_persons(user=None):
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
    if not persons:
        return False
    return bool(
        frappe.db.exists("Cash Tracker Person", {"name": ["in", persons], "allow_for_motley": 1})
    )


def _can_view_tsbc(persons):
    if not persons:
        return False
    return bool(
        frappe.db.exists("Cash Tracker Person", {"name": ["in", persons], "allow_for_tsbc": 1})
    )


def _can_view_safe(persons):
    if not persons:
        return False
    return bool(
        frappe.db.exists("Cash Tracker Person", {"name": ["in", persons], "allow_for_safe": 1})
    )


@frappe.whitelist()
def get_persons():
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
            "allow_tsbc": True,
            "allow_safe": True,
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
        "shared": [p for p in visible if p != own],
        "allow_motley": _can_view_motley(visible),
        "can_create_motley": can_use_motley(),
        "allow_tsbc": _can_view_tsbc(visible),
        "can_create_tsbc": can_use_tsbc(),
        "allow_safe": _can_view_safe(visible),
        "can_create_safe": can_use_safe(),
    }


@frappe.whitelist()
def get_entries(tracker="personal", person=None, from_date=None, to_date=None):
    is_admin = _is_full_view()

    if not is_admin:
        visible = _visible_persons()
        if not visible:
            return {
                "rows": [], "totals": _empty_totals(),
                "is_admin": False, "tracker": "personal",
                "can_mark_processed": can_mark_processed(),
            }
        if tracker == "motley" and not _can_view_motley(visible):
            tracker = "personal"
        if tracker == "tsbc" and not _can_view_tsbc(visible):
            tracker = "personal"
        if tracker == "safe" and not _can_view_safe(visible):
            tracker = "personal"
        person = person if person in visible else (visible if not person else visible[0])
    else:
        person = person or None

    rows = []
    if tracker == "motley":
        rows += _fetch_motley(person, from_date, to_date)
    elif tracker == "tsbc":
        rows += _fetch_tsbc(person, from_date, to_date)
    elif tracker == "safe":
        rows += _fetch_safe(person, from_date, to_date)
    else:
        rows += _fetch_personal(person, from_date, to_date)

    rows.sort(key=lambda r: (r.get("date") or "", r.get("name") or ""), reverse=True)
    return {
        "rows": rows,
        "totals": _compute_totals(rows),
        "is_admin": is_admin,
        "tracker": tracker,
        "can_mark_processed": can_mark_processed(),
    }


def _base_filters(person, from_date, to_date):
    filters = [["docstatus", "=", 1]]
    if person:
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
            "invoice_number as sales_order", "employee",
            "processed", "processed_by", "processed_on",
        ],
        order_by="transaction_date desc",
    )
    for r in recs:
        r["tracker"] = "Motley"
        r["status"] = STATUS_MAP.get(r.pop("docstatus"), "")
    return recs


def _fetch_tsbc(person, from_date, to_date):
    recs = frappe.get_all(
        "TSBC Cash Tracking",
        filters=_base_filters(person, from_date, to_date),
        fields=[
            "name", "transaction_date as date", "cash_tracker_person as person",
            "user", "transaction_type as category", "business",
            "money_in", "money_out", "docstatus", "transaction_notes as notes",
            "invoice_number as sales_order", "employee",
            "processed", "processed_by", "processed_on",
        ],
        order_by="transaction_date desc",
    )
    for r in recs:
        r["tracker"] = "TSBC"
        r["status"] = STATUS_MAP.get(r.pop("docstatus"), "")
    return recs


def _fetch_safe(person, from_date, to_date):
    recs = frappe.get_all(
        "Safe Cash Tracking",
        filters=_base_filters(person, from_date, to_date),
        fields=[
            "name", "transaction_date as date", "cash_tracker_person as person",
            "user", "transaction_type as category", "business",
            "money_in", "money_out", "docstatus", "transaction_notes as notes",
            "invoice_number as sales_order", "employee",
            "processed", "processed_by", "processed_on",
        ],
        order_by="transaction_date desc",
    )
    for r in recs:
        r["tracker"] = "Safe"
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
            "invoice_number as sales_order", "employee",
            "processed", "processed_by", "processed_on",
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


@frappe.whitelist()
def set_processed(tracker, name, processed):
    if not can_mark_processed():
        frappe.throw(
            "Only the finance team can mark an entry as processed.",
            frappe.PermissionError,
        )

    doctype = {
        "motley": "Motley Cash Tracking",
        "tsbc": "TSBC Cash Tracking",
        "safe": "Safe Cash Tracking",
    }.get(tracker, "Personal Cash Tracking")
    if not frappe.db.exists(doctype, name):
        frappe.throw(f"{doctype} {name} not found")

    processed = int(frappe.parse_json(processed) if isinstance(processed, str) else processed)
    frappe.db.set_value(
        doctype,
        name,
        {
            "processed": processed,
            "processed_by": frappe.session.user if processed else None,
            "processed_on": frappe.utils.now_datetime() if processed else None,
        },
        update_modified=False,
    )
    return {
        "name": name,
        "processed": processed,
        "processed_by": frappe.session.user if processed else None,
    }
