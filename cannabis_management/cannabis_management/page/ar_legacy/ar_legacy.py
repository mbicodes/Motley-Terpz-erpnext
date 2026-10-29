import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate, nowdate

from cannabis_management.api.sheet_export import send_csv, send_xlsx

from cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard import (
	LEGACY_CUTOFF,
	NEW_AR_START,
	ORG_WIDE_VIEW_ROLES,
	_internal_customer_names,
	_permitted_companies,
)

SEGMENTS = [
	"Matt's Accounts",
	"Matt has Relationships",
	"Nikki's Accounts - Matt knows them",
	"Nikki's Accounts - Legit companies",
	"Nikki's Accounts - Unknown companies",
]

REACH_OUT_FIELD = "custom_reach_out_status"
NOT_REACHED_OUT = "Haven't Reached Out"
REACHED_OUT = "Reached Out"
REACH_OUT_STATUSES = [
	REACHED_OUT,
	"Ready to reach out",
	"Ready to reach out - Sales Rep",
	"Find Info",
	NOT_REACHED_OUT,
]

AR_SEGMENT_DOCTYPE = "AR Segment"

AR_MODES = ("legacy", "new", "all")


def get_segments():
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
		return fallback

	return [{"value": r["name"], "color": r.get("color") or None} for r in rows]


def sync_segment_field_options(exclude=None):
	values = [s["value"] for s in get_segments() if s["value"] != exclude]

	name = frappe.db.get_value(
		"Custom Field", {"dt": "Customer", "fieldname": SEGMENT_FIELD}, "name"
	)
	if name:
		frappe.db.set_value("Custom Field", name, "options", "\n" + "\n".join(values))
		frappe.clear_cache(doctype="Customer")


def seed_segments():
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

EDIT_ROLES = ORG_WIDE_VIEW_ROLES + ("Account Manager",)


def _can_edit(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)).intersection(EDIT_ROLES))


@frappe.whitelist()
def get_data(ar_mode="legacy"):
	permitted = _permitted_companies()
	internal = _internal_customer_names()

	has_field = frappe.db.has_column("Customer", SEGMENT_FIELD)
	segment_select = f"MAX(c.{SEGMENT_FIELD})" if has_field else "NULL"

	ar_mode = ar_mode if ar_mode in AR_MODES else "legacy"

	conditions = ["si.docstatus = 1", "si.outstanding_amount > 0"]
	if ar_mode == "new":
		conditions.append("si.posting_date >= %(start)s")
		params = {"start": NEW_AR_START}
	elif ar_mode == "all":
		conditions.append("(si.posting_date <= %(cutoff)s OR si.posting_date >= %(start)s)")
		params = {"cutoff": LEGACY_CUTOFF, "start": NEW_AR_START}
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
	if not _can_edit():
		frappe.throw(
			"You do not have permission to move accounts between segments.",
			frappe.PermissionError,
		)

	segment = (segment or "").strip()
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


@frappe.whitelist()
def set_reach_out_status(customer, status):
	if not _can_edit():
		frappe.throw(
			"You do not have permission to change the reach out status.",
			frappe.PermissionError,
		)

	status = (status or "").strip() or NOT_REACHED_OUT
	if status not in REACH_OUT_STATUSES:
		frappe.throw(f"Unknown reach out status: {status}")

	if not frappe.db.has_column("Customer", REACH_OUT_FIELD):
		frappe.throw(
			"The Reach Out Status field is not installed on this site yet. Run: "
			"bench --site &lt;site&gt; execute cannabis_management.cannabis_management."
			"page.ar_legacy.ar_legacy.install_reach_out_field"
		)

	if not frappe.db.exists("Customer", customer):
		frappe.throw(f"Customer {customer} not found")

	frappe.db.set_value("Customer", customer, REACH_OUT_FIELD, status)
	return {"customer": customer, "status": status}


def install_reach_out_field():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Customer": [
				{
					"fieldname": REACH_OUT_FIELD,
					"fieldtype": "Select",
					"label": "Reach Out Status",
					"options": "\n".join(REACH_OUT_STATUSES),
					"default": NOT_REACHED_OUT,
					"insert_after": SEGMENT_FIELD,
					"in_standard_filter": 1,
					"description": "Set from AR Accountability — whether anyone has reached out to this account yet.",
				}
			]
		},
		update=True,
	)
	frappe.db.sql(
		f"""UPDATE `tabCustomer` SET `{REACH_OUT_FIELD}` = %s
		WHERE IFNULL(`{REACH_OUT_FIELD}`, '') = ''""",
		NOT_REACHED_OUT,
	)

	if frappe.db.exists("DocType", AR_SEGMENT_DOCTYPE):
		for old in ("Ready to reach out", "Ready to reach out - Sales Rep"):
			if frappe.db.get_value(AR_SEGMENT_DOCTYPE, old, "disabled") == 0:
				seg = frappe.get_doc(AR_SEGMENT_DOCTYPE, old)
				seg.disabled = 1
				seg.save(ignore_permissions=True)

	frappe.db.commit()
	return {"status": "ok", "field": REACH_OUT_FIELD}


def install_segment_field():
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


def _export_tables(ar_mode="legacy", filters=None):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	data = get_data(ar_mode)
	rows = data["rows"]

	search = (filters.get("search") or "").strip().lower()
	company = filters.get("company") or ""
	segment = filters.get("segment") or ""
	min_amount = flt(filters.get("min_amount"))
	age = cint(filters.get("age"))

	def keep(r):
		if search and search not in (r.get("customer") or "").lower() \
				and search not in (r.get("customer_name") or "").lower():
			return False
		if company and company not in (r.get("companies") or ""):
			return False
		if min_amount and flt(r.get("outstanding")) < min_amount:
			return False
		if age and cint(r.get("age_days")) < age:
			return False
		if segment == "__unassigned__" and r.get("segment"):
			return False
		if segment and segment != "__unassigned__" and r.get("segment") != segment:
			return False
		return True

	rows = [r for r in rows if keep(r)]

	sort = filters.get("sort") or "outstanding"
	if sort == "age":
		rows.sort(key=lambda r: -cint(r.get("age_days")))
	elif sort == "invoices":
		rows.sort(key=lambda r: -cint(r.get("invoices")))
	elif sort == "name":
		rows.sort(key=lambda r: (r.get("customer_name") or r.get("customer") or "").lower())
	else:
		rows.sort(key=lambda r: -flt(r.get("outstanding")))

	book = {"new": "New AR", "all": "Legacy + New AR"}.get(data["ar_mode"], "Legacy AR")

	grid = [["Customer", "Customer Name", "Segment", "Companies",
	         "Invoices", "Outstanding", "Oldest Invoice", "Age (days)"]]
	for r in rows:
		grid.append([
			r.get("customer"), r.get("customer_name"),
			r.get("segment") or data["unassigned_label"],
			r.get("companies"), cint(r.get("invoices")),
			flt(r.get("outstanding"), 2),
			getdate(r["oldest"]) if r.get("oldest") else None,
			cint(r.get("age_days")),
		])

	totals = {}
	for r in rows:
		key = r.get("segment") or data["unassigned_label"]
		t = totals.setdefault(key, {"accounts": 0, "invoices": 0, "outstanding": 0.0})
		t["accounts"] += 1
		t["invoices"] += cint(r.get("invoices"))
		t["outstanding"] += flt(r.get("outstanding"))

	summary = [["Segment", "Accounts", "Invoices", "Outstanding"]]
	for key in sorted(totals, key=lambda k: -totals[k]["outstanding"]):
		t = totals[key]
		summary.append([key, t["accounts"], t["invoices"], flt(t["outstanding"], 2)])
	if len(summary) > 1:
		summary.append([
			"Total", sum(t["accounts"] for t in totals.values()),
			sum(t["invoices"] for t in totals.values()),
			flt(sum(t["outstanding"] for t in totals.values()), 2),
		])

	return book, grid, summary


@frappe.whitelist()
def export_xlsx(ar_mode="legacy", filters=None):
	book, grid, summary = _export_tables(ar_mode, filters)
	send_xlsx(
		_("{0} - AR by Segment {1}").format(book, nowdate()),
		[
			("Accounts", grid, [26, 36, 22, 30, 10, 16, 15, 12]),
			("By Segment", summary, [24, 11, 11, 16]),
		],
	)


@frappe.whitelist()
def export_csv(ar_mode="legacy", filters=None):
	book, grid, _summary = _export_tables(ar_mode, filters)
	send_csv(_("{0} - AR by Segment {1}").format(book, nowdate()), grid)
