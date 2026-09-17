"""AR Legacy — legacy receivables grouped by who owns the relationship.

The legacy book (invoices posted on or before the AR cut-over) is being worked
through account by account, and the first question on every one of them is whose
relationship it is. This page answers that: every legacy customer with money
still outstanding, filed under one of the segments below, with the balance and
invoice count so the size of each pile is obvious.

The segment is stored on the Customer itself (custom_ar_legacy_segment), so it
survives, reports and filters like any other field rather than living only in
this page.

Numbers come from the same source as the AR dashboard — Sales Invoice
outstanding for invoices up to LEGACY_CUTOFF, intercompany customers excluded —
so the two pages can never disagree about what legacy AR is.
"""

import frappe
from frappe.utils import date_diff, flt, getdate, nowdate

from cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard import (
	LEGACY_CUTOFF,
	NEW_AR_START,
	ORG_WIDE_VIEW_ROLES,
	_internal_customer_names,
	_permitted_companies,
)

# The original five. No longer the source of truth - that is the "AR Segment"
# doctype, one record per segment - but kept as the seed for a fresh site and as
# the fallback when the doctype is not installed, so the page cannot break
# between deploying code and migrating.
SEGMENTS = [
	"Matt's Accounts",
	"Matt has Relationships",
	"Nikki's Accounts - Matt knows them",
	"Nikki's Accounts - Legit companies",
	"Nikki's Accounts - Unknown companies",
]

AR_SEGMENT_DOCTYPE = "AR Segment"

# Which invoices each mode counts. The segment itself is a Customer attribute and
# is NOT per-mode: switching modes changes the money on the page, not who owns
# the relationship.
AR_MODES = ("legacy", "new")


def get_segments():
	"""Segments offered on the page, in display order.

	``[{"value": <segment>, "color": <hex or None>}]``. The blank "Unassigned"
	entry is added by the front end; it is not a record.
	"""
	fallback = [{"value": s, "color": None} for s in SEGMENTS]

	if not frappe.db.exists("DocType", AR_SEGMENT_DOCTYPE):
		return fallback

	rows = frappe.get_all(
		AR_SEGMENT_DOCTYPE,
		filters={"disabled": 0},
		fields=["name", "color"],
		order_by="display_order asc, creation asc",
	)
	if not rows:
		# No segments at all is never what anyone wants - treat it as
		# "not configured yet" and offer the originals.
		return fallback

	return [{"value": r["name"], "color": r.get("color") or None} for r in rows]


def sync_segment_field_options(exclude=None):
	"""Point the Customer form's own Select at the current segment list.

	Called from the AR Segment controller so the Customer field and this page can
	never disagree. ``exclude`` drops a record that is mid-delete and therefore
	still readable.
	"""
	values = [s["value"] for s in get_segments() if s["value"] != exclude]

	name = frappe.db.get_value(
		"Custom Field", {"dt": "Customer", "fieldname": SEGMENT_FIELD}, "name"
	)
	if name:
		frappe.db.set_value("Custom Field", name, "options", "\n" + "\n".join(values))
		frappe.clear_cache(doctype="Customer")


def seed_segments():
	"""Create a record per original segment. Idempotent; safe to re-run.

	Colours match what ar_legacy.css already hard-codes for these five, so the
	page looks exactly as it did before they became records.
	"""
	if not frappe.db.exists("DocType", AR_SEGMENT_DOCTYPE):
		return

	colors = {
		"Matt's Accounts": "#7c3aed",
		"Matt has Relationships": "#2563eb",
		"Nikki's Accounts - Matt knows them": "#0d9488",
		"Nikki's Accounts - Legit companies": "#16a34a",
		"Nikki's Accounts - Unknown companies": "#d97706",
	}

	for i, segment in enumerate(SEGMENTS):
		if frappe.db.exists(AR_SEGMENT_DOCTYPE, segment):
			continue
		frappe.get_doc({
			"doctype": AR_SEGMENT_DOCTYPE,
			"segment_name": segment,
			"color": colors.get(segment),
			"display_order": (i + 1) * 10,
		}).insert(ignore_permissions=True)

UNASSIGNED = "Unassigned"

SEGMENT_FIELD = "custom_ar_legacy_segment"

# Who may move an account between segments. Viewing follows the page's own role
# gate; filing an account under someone's name is an ownership call, so it is
# kept to the people who own the AR process.
EDIT_ROLES = ORG_WIDE_VIEW_ROLES + ("Account Manager",)


def _can_edit(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)).intersection(EDIT_ROLES))


@frappe.whitelist()
def get_data(ar_mode="legacy"):
	"""Every customer still owing money in the chosen book, with segment and totals.

	Read with raw SQL rather than get_list: the figures are the same for everyone
	who can open the page, and the page is role-gated already. Company scoping is
	applied explicitly from the caller's own User Permissions so a rep restricted
	to two entities does not see the rest.
	"""
	permitted = _permitted_companies()
	internal = _internal_customer_names()

	# The segment column is created by install_segment_field, not by migrate. On a
	# site where that has not been run yet, selecting it would fail with "Unknown
	# column" and the page would show nothing at all — so fall back to reading no
	# segment and let the page say what to run.
	has_field = frappe.db.has_column("Customer", SEGMENT_FIELD)
	segment_select = f"MAX(c.{SEGMENT_FIELD})" if has_field else "NULL"

	# Legacy is everything up to the cut-over, New AR everything from the day
	# after it - the same two windows the AR dashboard uses, so the pages agree.
	# Anything unrecognised falls back to legacy: that was the only behaviour
	# before the toggle existed and it must stay the default.
	ar_mode = ar_mode if ar_mode in AR_MODES else "legacy"

	conditions = ["si.docstatus = 1", "si.outstanding_amount > 0"]
	if ar_mode == "new":
		conditions.append("si.posting_date >= %(start)s")
		params = {"start": NEW_AR_START}
	else:
		conditions.append("si.posting_date <= %(cutoff)s")
		params = {"cutoff": LEGACY_CUTOFF}

	if internal:
		conditions.append("si.customer NOT IN %(internal)s")
		params["internal"] = tuple(internal)

	if permitted is not None:
		conditions.append("si.company IN %(companies)s")
		params["companies"] = tuple(permitted) or ("__none__",)

	rows = frappe.db.sql(
		f"""
		SELECT
			si.customer                                    AS customer,
			MAX(c.customer_name)                           AS customer_name,
			COUNT(*)                                       AS invoices,
			SUM(si.outstanding_amount * IFNULL(si.conversion_rate, 1)) AS outstanding,
			MIN(si.posting_date)                           AS oldest,
			{segment_select}                               AS segment,
			GROUP_CONCAT(DISTINCT si.company ORDER BY si.company SEPARATOR ', ') AS companies
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE {" AND ".join(conditions)}
		GROUP BY si.customer
		ORDER BY outstanding DESC
		""",
		params,
		as_dict=True,
	)

	today = getdate(nowdate())
	companies = set()
	for row in rows:
		row["outstanding"] = flt(row["outstanding"])
		row["segment"] = row.get("segment") or ""
		row["companies"] = row.get("companies") or ""
		oldest = row.get("oldest")
		row["oldest"] = str(oldest or "")
		# Age of the oldest unpaid invoice, in days — the useful sort for a
		# legacy book, where "how long has this been sitting" beats size.
		row["age_days"] = date_diff(today, getdate(oldest)) if oldest else 0
		for company in (row["companies"] or "").split(", "):
			if company:
				companies.add(company)

	segments = get_segments()

	return {
		"rows": rows,
		"companies": sorted(companies),
		"segments": [s["value"] for s in segments],
		"segment_colors": {s["value"]: s["color"] for s in segments if s["color"]},
		"unassigned_label": UNASSIGNED,
		"can_edit": _can_edit() and has_field,
		"cutoff": LEGACY_CUTOFF,
		"ar_mode": ar_mode,
		"field_missing": not has_field,
	}


@frappe.whitelist()
def set_segment(customer, segment):
	"""File one customer under a segment. Blank moves it back to Unassigned."""
	if not _can_edit():
		frappe.throw(
			"You do not have permission to move accounts between segments.",
			frappe.PermissionError,
		)

	segment = (segment or "").strip()
	# Checked against the live list, so a segment added today is accepted today.
	if segment and segment not in [s["value"] for s in get_segments()]:
		frappe.throw(f"Unknown segment: {segment}")

	if not frappe.db.has_column("Customer", SEGMENT_FIELD):
		frappe.throw(
			"The AR Legacy segment field is not installed on this site yet. Run: "
			"bench --site &lt;site&gt; execute cannabis_management.cannabis_management."
			"page.ar_legacy.ar_legacy.install_segment_field"
		)

	if not frappe.db.exists("Customer", customer):
		frappe.throw(f"Customer {customer} not found")

	frappe.db.set_value("Customer", customer, SEGMENT_FIELD, segment)
	return {"customer": customer, "segment": segment}


def install_segment_field():
	"""Create the Customer field this page writes to. Idempotent — safe to re-run.

	Deliberately NOT added to the app's Custom Field fixture: that fixture is
	re-imported by every bench migrate and would fight any later change to this
	field. Adding a new field is safe from it — the fixture only overwrites what
	it already contains — so this installer is the only thing that owns it.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Customer": [
				{
					"fieldname": SEGMENT_FIELD,
					"fieldtype": "Select",
					"label": "AR Legacy Segment",
					"options": "\n" + "\n".join([s["value"] for s in get_segments()]),
					"insert_after": "custom_reconciliation_status",
					"in_standard_filter": 1,
					"description": "Set from the AR Legacy page — whose relationship this legacy account is.",
				}
			]
		},
		update=True,
	)
	frappe.db.commit()
	return {"status": "ok", "field": SEGMENT_FIELD, "segments": SEGMENTS}
