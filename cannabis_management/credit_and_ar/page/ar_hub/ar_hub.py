# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""AR Hub — one receivables grid doing the work of AR Dashboard, Categorized AR
and AR Accountability.

One row per customer. The money comes straight from Sales Invoice
(outstanding_amount and due_date), which is where all three pages end up: AR
Dashboard replaces the ERPNext report's figures with exactly these
(_apply_si_outstanding), Categorized AR sums them and AR Accountability buckets
them. Intercompany customers and company scope follow AR Dashboard and
Categorized AR; aging buckets and debt levels are AR Accountability's own.

Nothing here writes. Recon status, the two Yes/No flags, the notebox, New AR,
the segment and the weekly entries are saved through those pages' own
endpoints, with their own permission checks, so all four pages always show the
same values.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from cannabis_management.api.sheet_export import send_csv, send_xlsx
from cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard import (
	LEGACY_CUTOFF,
	NEW_AR_START,
	TMM_GROUP_COMPANIES,
	_internal_customer_names,
	_permitted_companies,
	_scope_companies,
)
from cannabis_management.credit_and_ar.doctype.ar_weekly_entry.ar_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)
from cannabis_management.credit_and_ar.page.ar_weekly_review.ar_weekly_review import (
	BUCKETS,
	LEDGER_LEGACY,
	LEDGER_NEW,
	TIER_LABELS,
	TIER_RANK,
	_attach_customer_info,
	_bucket_for,
	_latest_entries,
	_ledger_for,
)
from cannabis_management.credit_and_ar.page.ar_weekly_review.ar_weekly_review import (
	PAGE_ROLE as WEEKLY_ROLE,
)

PAGE = "ar-hub"
ALL_COMPANIES = "__ALL__"
AR_MODES = ("legacy", "new", "all")

OVERDUE_LABELS = [b[1] for b in BUCKETS]

# Days left before the due date, for invoices still on terms: AR Dashboard's
# "New AR on Terms" columns. (key, label, upper bound; None = no bound)
TERMS = (
	("t1", "0-10", 10),
	("t2", "10-20", 20),
	("t3", "20+", None),
)


def _require_access():
	"""Whitelisted methods are reachable by anyone logged in, so re-check the
	page's own roles. The weekly log has a stricter role, checked separately."""
	if not frappe.get_doc("Page", PAGE).is_permitted():
		frappe.throw(_("You are not permitted to view AR Hub."), frappe.PermissionError)


def _can_weekly():
	"""AR Accountability's role: who may see and file weekly entries."""
	return WEEKLY_ROLE in frappe.get_roles()


def _mode(ar_mode):
	return ar_mode if ar_mode in AR_MODES else "all"


def _company_scope(company, permitted):
	"""Companies to count, already narrowed to `permitted`. None = every company."""
	if not company or company == ALL_COMPANIES:
		return permitted
	if company == "TMM Group":
		return _scope_companies(TMM_GROUP_COMPANIES, permitted)
	return _scope_companies([company], permitted)


def _in_mode(posting_date, ar_mode):
	posted = str(posting_date or "")
	if ar_mode == "legacy":
		return posted <= LEGACY_CUTOFF
	if ar_mode == "new":
		return posted >= NEW_AR_START
	return posted <= LEGACY_CUTOFF or posted >= NEW_AR_START


def _terms_key(days_left):
	for key, _label, upper in TERMS:
		if upper is None or days_left <= upper:
			return key


def _company_options(permitted):
	companies = _scope_companies(frappe.get_all("Company", pluck="name", order_by="name"), permitted)
	# TMM Group is a roll-up of TMM_GROUP_COMPANIES, as on AR Dashboard.
	if "TMM Group" not in companies and _scope_companies(TMM_GROUP_COMPANIES, permitted):
		companies.append("TMM Group")
	return sorted(companies)


def _new_row(inv):
	return {
		"customer": inv.customer,
		"customer_name": inv.customer_name or inv.customer,
		"companies": set(),
		"invoice_count": 0,
		"invoiced": 0.0,
		"paid": 0.0,
		"outstanding": 0.0,
		"ledger_amounts": {},
		"on_terms": 0.0,
		"terms": {key: 0.0 for key, _label, _upper in TERMS},
		"overdue": 0.0,
		"buckets": {label: 0.0 for label in OVERDUE_LABELS},
		"tier": "upcoming",
		"worst": "",
		"oldest": None,
		"invoices": [],
	}


def _build(ar_mode, company):
	"""Every customer with an open balance in the chosen book and companies."""
	ar_mode = _mode(ar_mode)
	permitted = _permitted_companies()
	scope = _company_scope(company, permitted)
	internal = _internal_customer_names()
	today = getdate(nowdate())

	invoices = frappe.db.sql(
		"""
		select si.name, si.customer, c.customer_name, si.company, si.posting_date, si.due_date,
		       si.outstanding_amount * ifnull(si.conversion_rate, 1) as outstanding,
		       if(ifnull(si.base_rounded_total, 0) != 0, si.base_rounded_total, si.base_grand_total) as invoiced
		from `tabSales Invoice` si
		left join `tabCustomer` c on c.name = si.customer
		where si.docstatus = 1 and si.outstanding_amount > 0
		order by si.due_date, si.name
		""",
		as_dict=True,
	)

	rows = {}
	# A weekly entry is filed per customer + ledger across every company, and
	# its status is validated against that tier (_snapshot_for). The status
	# choices use the same scope, whatever the filters say.
	weekly_tier = {}

	for inv in invoices:
		if inv.customer in internal:
			continue
		ledger = _ledger_for(inv.posting_date)
		due = getdate(inv.due_date) if inv.due_date else today
		days_overdue = (today - due).days
		label, tier = _bucket_for(days_overdue)

		key = (inv.customer, ledger)
		if TIER_RANK[tier] > TIER_RANK[weekly_tier.get(key, "upcoming")]:
			weekly_tier[key] = tier
		weekly_tier.setdefault(key, tier)

		if scope is not None and inv.company not in scope:
			continue
		if not _in_mode(inv.posting_date, ar_mode):
			continue

		r = rows.get(inv.customer)
		if r is None:
			r = rows[inv.customer] = _new_row(inv)

		outstanding = flt(inv.outstanding, 2)
		invoiced = flt(inv.invoiced, 2)
		r["companies"].add(inv.company)
		r["invoice_count"] += 1
		r["invoiced"] += invoiced
		r["paid"] += invoiced - outstanding
		r["outstanding"] += outstanding
		r["ledger_amounts"][ledger] = r["ledger_amounts"].get(ledger, 0.0) + outstanding

		if tier == "upcoming":
			days_left = max((due - today).days, 0)
			r["terms"][_terms_key(days_left)] += outstanding
			r["on_terms"] += outstanding
			aging = _("{0}d left").format(days_left)
		else:
			r["buckets"][label] += outstanding
			r["overdue"] += outstanding
			aging = label

		if TIER_RANK[tier] >= TIER_RANK[r["tier"]]:
			r["tier"] = tier
		if tier != "upcoming" and OVERDUE_LABELS.index(label) >= (
			OVERDUE_LABELS.index(r["worst"]) if r["worst"] else -1
		):
			r["worst"] = label
		posted = getdate(inv.posting_date)
		if r["oldest"] is None or posted < r["oldest"]:
			r["oldest"] = posted

		r["invoices"].append({
			"name": inv.name,
			"company": inv.company,
			"ledger": ledger,
			"posting_date": str(inv.posting_date or ""),
			"due_date": str(inv.due_date or ""),
			"aging": aging,
			"tier": tier,
			"invoiced": invoiced,
			"paid": flt(invoiced - outstanding, 2),
			"outstanding": outstanding,
		})

	out_rows = sorted(rows.values(), key=lambda r: -r["outstanding"])
	for r in out_rows:
		r["companies"] = sorted(r["companies"])
		r["age_days"] = date_diff(today, r["oldest"])
		r["oldest"] = str(r["oldest"])
		r["ledgers"] = [lg for lg in (LEDGER_NEW, LEDGER_LEGACY) if r["ledger_amounts"].get(lg)]
		r["legacy_ar"] = r["ledger_amounts"].get(LEDGER_LEGACY, 0.0)
		r["new_ar"] = r["ledger_amounts"].get(LEDGER_NEW, 0.0)
		del r["ledger_amounts"]

	meta = _attach_customer_info(out_rows)
	_attach_account_fields(out_rows)

	can_weekly = _can_weekly()
	if can_weekly:
		latest = _latest_entries()
		for r in out_rows:
			r["weekly"] = {}
			for lg in r["ledgers"]:
				tier = weekly_tier.get((r["customer"], lg), "upcoming")
				info = latest.get((r["customer"], lg)) or {}
				r["weekly"][lg] = {
					"tier": tier,
					"statuses": STATUSES_BY_TIER.get(tier, []),
					"status": info.get("current_status") or "",
					"note": info.get("latest_note") or "",
					"week": info.get("latest_week") or "",
					"count": info.get("log_count") or 0,
				}

	statuses = []
	for tier in ("upcoming", "level1", "level2", "level3"):
		for s in STATUSES_BY_TIER.get(tier, []):
			if s not in statuses:
				statuses.append(s)

	meta.update({
		"rows": out_rows,
		"ar_mode": ar_mode,
		"company": company or ALL_COMPANIES,
		"companies": _company_options(permitted),
		"as_of": str(today),
		"legacy_cutoff": LEGACY_CUTOFF,
		"new_ar_start": NEW_AR_START,
		"overdue_labels": OVERDUE_LABELS,
		"overdue": [{"label": label, "tier": tier} for _upper, label, tier in BUCKETS],
		"terms": [{"key": k, "label": lbl} for k, lbl, _upper in TERMS],
		"can_weekly": can_weekly,
		"week_of": str(week_start()) if can_weekly else "",
		"statuses": statuses if can_weekly else [],
	})
	return meta


def _attach_account_fields(rows):
	"""Notebox and New AR, the two AR Dashboard fields _attach_customer_info
	does not carry. Either can be missing on a site that never ran
	setup_ar_custom_fields."""
	fields = {
		"notebox": "custom_notebox",
		"new_ar_available": "custom_new_ar_available",
	}
	present = {k: f for k, f in fields.items() if frappe.db.has_column("Customer", f)}
	info = {}
	customers = [r["customer"] for r in rows]
	if customers and present:
		for c in frappe.get_all("Customer", filters={"name": ["in", customers]},
		                        fields=["name"] + list(present.values())):
			info[c.name] = c
	for r in rows:
		c = info.get(r["customer"]) or {}
		r["notebox"] = c.get("custom_notebox") or ""
		r["new_ar_available"] = 1 if c.get("custom_new_ar_available") else 0


@frappe.whitelist()
def get_data(ar_mode="all", company=None):
	"""The whole grid in one call."""
	_require_access()
	return _build(ar_mode, company)


@frappe.whitelist()
def get_customer_detail(customer, ar_mode="all", company=None):
	"""What an expanded row needs beyond the grid: the customer's fully paid
	invoices (display only, as in AR Dashboard's dropdown) and, for AR
	Accountability's role, the weekly entry history of the books in view."""
	_require_access()
	ar_mode = _mode(ar_mode)
	scope = _company_scope(company, _permitted_companies())

	conditions = ["docstatus = 1", "is_return = 0", "outstanding_amount <= 0", "customer = %(customer)s"]
	params = {"customer": customer, "cutoff": LEGACY_CUTOFF, "start": NEW_AR_START}
	if scope is not None:
		conditions.append("company in %(companies)s")
		params["companies"] = tuple(scope) or ("__none__",)
	if ar_mode == "legacy":
		conditions.append("posting_date <= %(cutoff)s")
	elif ar_mode == "new":
		conditions.append("posting_date >= %(start)s")

	paid = []
	for inv in frappe.db.sql(
		f"""
		select name, company, posting_date, due_date,
		       if(ifnull(base_rounded_total, 0) != 0, base_rounded_total, base_grand_total) as invoiced
		from `tabSales Invoice`
		where {" and ".join(conditions)}
		order by posting_date desc, name desc
		""",
		params,
		as_dict=True,
	):
		if abs(flt(inv.invoiced)) < 0.005:
			continue  # $0 invoices (samples etc.) would read as "Paid" for nothing
		paid.append({
			"name": inv.name,
			"company": inv.company,
			"ledger": _ledger_for(inv.posting_date),
			"posting_date": str(inv.posting_date or ""),
			"due_date": str(inv.due_date or ""),
			"invoiced": flt(inv.invoiced, 2),
		})

	out = {"paid_invoices": paid, "log": []}
	if _can_weekly():
		ledgers = {"legacy": [LEDGER_LEGACY], "new": [LEDGER_NEW]}.get(ar_mode, [LEDGER_NEW, LEDGER_LEGACY])
		out["log"] = frappe.get_all(
			"AR Weekly Entry",
			filters={"customer": customer, "ledger": ["in", ledgers]},
			fields=["name", "ledger", "week_of", "status", "qa", "plan", "notes",
			        "contact", "email", "need_three_way_call", "tier_snapshot",
			        "amount_snapshot", "owner"],
			order_by="week_of desc, creation desc",
		)
	return out


def _export_tables(data, customers):
	"""Rows in the order the page shows them, limited to the customers it shows."""
	by_name = {r["customer"]: r for r in data["rows"]}
	if customers is None:
		rows = data["rows"]
	else:
		rows = [by_name[c] for c in customers if c in by_name]

	books = {"legacy": [LEDGER_LEGACY], "new": [LEDGER_NEW]}.get(data["ar_mode"], [LEDGER_NEW, LEDGER_LEGACY])
	weekly = data["can_weekly"]
	split = data["ar_mode"] == "all"

	head = ["Customer", "Customer Name", "Companies", "Segment", "Recon Status",
	        "Onboarding", "Company Made Contact"]
	if weekly:
		for book in books:
			head += [f"{book} Weekly Status", f"{book} Latest Note"]
	head += ["Level", "Worst Aging", "Oldest Invoice", "Age (days)", "Invoices",
	         "Invoiced", "Paid", "Outstanding"]
	if split:
		head += ["Legacy AR", "New AR"]
	head += [f"On Terms {t['label']} Days Left" for t in data["terms"]]
	head += [f"Overdue {lbl}" for lbl in data["overdue_labels"]]
	head += ["Notebox", "New AR Available"]

	grid = [head]
	inv_sheet = [["Customer", "Invoice", "Company", "Book", "Posted", "Due", "Aging",
	              "Invoiced", "Paid", "Outstanding"]]
	for r in rows:
		line = [r["customer"], r["customer_name"], ", ".join(r["companies"]),
		        r.get("segment") or data["unassigned_label"], r.get("recon_status") or "",
		        r.get("onboarding") or "", r.get("company_made_contact") or ""]
		if weekly:
			for book in books:
				w = (r.get("weekly") or {}).get(book) or {}
				line += [w.get("status") or "", w.get("note") or ""]
		line += [TIER_LABELS.get(r["tier"], r["tier"]), r["worst"] or "On terms",
		         getdate(r["oldest"]), r["age_days"], r["invoice_count"],
		         flt(r["invoiced"], 2), flt(r["paid"], 2), flt(r["outstanding"], 2)]
		if split:
			line += [flt(r["legacy_ar"], 2), flt(r["new_ar"], 2)]
		line += [flt(r["terms"][t["key"]], 2) for t in data["terms"]]
		line += [flt(r["buckets"][lbl], 2) for lbl in data["overdue_labels"]]
		line += [r.get("notebox") or "", "Yes" if r.get("new_ar_available") else "No"]
		grid.append(line)

		for i in r["invoices"]:
			inv_sheet.append([r["customer"], i["name"], i["company"], i["ledger"],
			                  getdate(i["posting_date"]) if i["posting_date"] else None,
			                  getdate(i["due_date"]) if i["due_date"] else None,
			                  i["aging"], i["invoiced"], i["paid"], i["outstanding"]])

	log = [["Customer", "Book", "Week Of", "Status", "Level At Entry", "Outstanding At Entry",
	        "What is going on?", "What is the plan?", "Notes", "Contact", "Email",
	        "Need Three-Way Call", "Filed By"]]
	if weekly and rows:
		for e in frappe.get_all(
			"AR Weekly Entry",
			filters={"customer": ["in", [r["customer"] for r in rows]], "ledger": ["in", books]},
			fields=["customer", "ledger", "week_of", "status", "tier_snapshot", "amount_snapshot",
			        "qa", "plan", "notes", "contact", "email", "need_three_way_call", "owner"],
			order_by="customer asc, week_of desc, creation desc",
		):
			log.append([e.customer, e.ledger, getdate(e.week_of) if e.week_of else None, e.status,
			            TIER_LABELS.get(e.tier_snapshot, e.tier_snapshot or ""), flt(e.amount_snapshot, 2),
			            e.qa, e.plan, e.notes, e.contact, e.email,
			            "Yes" if e.need_three_way_call else "No", e.owner])
	return grid, inv_sheet, log


@frappe.whitelist()
def export_view(ar_mode="all", company=None, customers=None, file_format="xlsx"):
	"""The grid as the page shows it. The page sends the customers in view and
	their order; every figure is recomputed here, so an export can never show
	a balance the page would not."""
	_require_access()
	data = _build(ar_mode, company)
	wanted = frappe.parse_json(customers) if customers else None
	grid, inv_sheet, log = _export_tables(data, wanted)

	title = _("AR Hub {0}").format(nowdate())
	if file_format == "csv":
		send_csv(title, grid)
		return
	send_xlsx(title, [
		("Receivables", grid, None),
		("Open Invoices", inv_sheet, [34, 22, 26, 12, 12, 12, 14, 14, 14, 14]),
		("Weekly Entries", log, [34, 12, 12, 24, 24, 18, 44, 44, 44, 20, 24, 18, 24]),
	])
