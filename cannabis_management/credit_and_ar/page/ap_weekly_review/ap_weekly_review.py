# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""AP Accountability — the payables counterpart of AR Accountability.

Built from the same shape as ar_weekly_review.py, with the differences that
actually matter on the payables side:

* The subject is the Supplier and the source is Purchase Invoice, so the
  question a row asks is "what are we doing about this bill", not "when will
  they pay us".

* There is no New/Legacy split. That exists on AR because of a policy cut-over
  date; payables have no such thing. The second axis here is Company, because
  each entity pays its own bills and a supplier can be owed money by more than
  one of them -- so a row is one supplier per company.

* Internal suppliers are excluded. Inter-company Purchase Invoices are created
  automatically from the matching Sales Invoice (see cannabis_management.inter_company),
  so leaving them in would fill the page with money the group owes itself. On
  this site that is 45 of 155 open bills.

* Invoices on hold are counted separately. An unpaid bill someone deliberately
  held is not the same problem as one that was simply missed, and only the
  second deserves to be chased.

Tier and outstanding amount are never stored per supplier: they are recomputed
from Purchase Invoice on every load, which is what makes an account slide from
Upcoming into Level 1 the day it passes its due date with no batch job.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.credit_and_ar.doctype.ap_weekly_entry.ap_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)

# Only holders of this role may see the page or call its methods.
PAGE_ROLE = "AP Weekly Review"


def _require_access():
	"""Re-state the page's role restriction for the whitelisted methods.

	The Page doc's `roles` only gate the route: every method below is reachable
	over /api/method by ANY logged-in user regardless of who can open the page,
	so without this the restriction would be cosmetic. Administrator holds every
	role and so needs no special case.
	"""
	if PAGE_ROLE not in frappe.get_roles():
		frappe.throw(
			_("You are not permitted to view AP Accountability."),
			frappe.PermissionError,
		)


# (upper bound in days overdue, label, tier). None = no upper bound.
BUCKETS = (
	(7, "0-7 days", "level1"),
	(15, "7-15 days", "level1"),
	(21, "15-21 days", "level1"),
	(30, "21-30 days", "level1"),
	(60, "30-60 days", "level2"),
	(90, "60-90 days", "level3"),
	(120, "90-120 days", "level3"),
	(None, "120+ days", "level3"),
)
ON_TERMS = ("On terms", "upcoming")

# Worst-first, so "which tier does this row get" is just a max().
TIER_RANK = {"upcoming": 0, "level1": 1, "level2": 2, "level3": 3}


def _bucket_for(days_overdue):
	"""Return (label, tier) for a number of days past due. <= 0 is not yet due."""
	if days_overdue <= 0:
		return ON_TERMS
	for upper, label, tier in BUCKETS:
		if upper is None or days_overdue <= upper:
			return label, tier
	return BUCKETS[-1][1], BUCKETS[-1][2]


def _bucket_rank(label):
	if label == ON_TERMS[0]:
		return -1
	for i, (_upper, lbl, _tier) in enumerate(BUCKETS):
		if lbl == label:
			return i
	return -1


def _internal_suppliers():
	return {
		s.name
		for s in frappe.get_all("Supplier", filters={"is_internal_supplier": 1}, fields=["name"])
	}


def _open_bills():
	"""Every submitted, still-outstanding, non-intercompany Purchase Invoice."""
	internal = _internal_suppliers()
	rows = frappe.db.sql(
		"""
		select pi.name, pi.supplier, pi.supplier_name, pi.posting_date, pi.due_date,
		       pi.outstanding_amount, pi.company, pi.on_hold, pi.release_date, pi.bill_no
		from `tabPurchase Invoice` pi
		where pi.docstatus = 1 and pi.outstanding_amount > 0
		""",
		as_dict=True,
	)
	return [r for r in rows if r.supplier not in internal]


def _build_rows(company=None):
	"""One row per supplier + company + portion.

	Portion is "upcoming" (nothing yet due) or "overdue", kept apart for the
	same reason as on AR: a bill that is merely scheduled and a bill that is
	already late call for different actions, and only one of them is moving.
	"""
	today = getdate(nowdate())
	groups = {}

	for inv in _open_bills():
		if company and company != "all" and inv.company != company:
			continue

		days_overdue = (today - getdate(inv.due_date)).days if inv.due_date else 0
		label, tier = _bucket_for(days_overdue)
		portion = "upcoming" if tier == "upcoming" else "overdue"

		key = (inv.supplier, inv.company, portion)
		g = groups.setdefault(
			key,
			{
				"id": "{0}|{1}|{2}".format(inv.supplier, inv.company, portion),
				"supplier": inv.supplier,
				"supplier_name": inv.supplier_name or inv.supplier,
				"company": inv.company,
				"portion": portion,
				"amount": 0.0,
				"tier": "upcoming",
				"days": label,
				"_buckets": {},
				"invoice_count": 0,
				"held_amount": 0.0,
				"held_count": 0,
				"oldest_due": None,
			},
		)

		amount = flt(inv.outstanding_amount)
		g["amount"] += amount
		g["invoice_count"] += 1
		if inv.on_hold:
			g["held_amount"] += amount
			g["held_count"] += 1
		if inv.due_date and (g["oldest_due"] is None or str(inv.due_date) < g["oldest_due"]):
			g["oldest_due"] = str(inv.due_date)

		b = g["_buckets"].setdefault(label, {"label": label, "amount": 0.0, "tier": tier})
		b["amount"] += amount

		# Row tier / days badge always describe the worst bucket present.
		if TIER_RANK[tier] >= TIER_RANK[g["tier"]]:
			g["tier"] = tier
		if _bucket_rank(label) >= _bucket_rank(g["days"]):
			g["days"] = label

	rows = []
	for g in groups.values():
		g["breakdown"] = sorted(g.pop("_buckets").values(), key=lambda b: _bucket_rank(b["label"]))
		rows.append(g)

	rows.sort(key=lambda r: -r["amount"])
	return rows


def _latest_entries():
	"""Most recent AP Weekly Entry per supplier+company, plus how many exist.

	Status is keyed on supplier + company, not per portion -- so an account's
	upcoming and overdue rows share one weekly log.
	"""
	rows = frappe.db.sql(
		"""
		select e.supplier, e.company, e.status, e.week_of, e.qa, e.plan, e.notes
		from `tabAP Weekly Entry` e
		inner join (
			select supplier, company, max(week_of) as week_of
			from `tabAP Weekly Entry` group by supplier, company
		) latest
		on latest.supplier = e.supplier and latest.company = e.company
		and latest.week_of = e.week_of
		""",
		as_dict=True,
	)
	counts = frappe.db.sql(
		"""select supplier, company, count(*) n from `tabAP Weekly Entry`
		   group by supplier, company""",
		as_dict=True,
	)
	count_map = {(c.supplier, c.company): c.n for c in counts}

	out = {}
	for r in rows:
		# max(week_of) can tie if two entries were filed the same week; last wins.
		out[(r.supplier, r.company)] = {
			"current_status": r.status or "",
			"latest_note": r.qa or r.plan or r.notes or "",
			"latest_week": str(r.week_of or ""),
			"log_count": count_map.get((r.supplier, r.company), 0),
		}
	return out


def _companies_with_bills():
	"""Companies that actually owe something, worst first.

	Read off the rows rather than listing every Company, so the filter never
	offers an entity with nothing to review.
	"""
	totals = {}
	for r in _build_rows():
		totals[r["company"]] = totals.get(r["company"], 0.0) + r["amount"]
	return [c for c, _amt in sorted(totals.items(), key=lambda kv: -kv[1])]


@frappe.whitelist()
def get_ap_weekly_review(company=None):
	"""The whole grid in one call."""
	_require_access()
	rows = _build_rows(company)
	latest = _latest_entries()

	for r in rows:
		info = latest.get((r["supplier"], r["company"]))
		r["current_status"] = info["current_status"] if info else ""
		r["latest_note"] = info["latest_note"] if info else ""
		r["log_count"] = info["log_count"] if info else 0
		r["statuses"] = STATUSES_BY_TIER.get(r["tier"], [])

	return {
		"rows": rows,
		"as_of": nowdate(),
		"week_of": str(week_start()),
		"companies": _companies_with_bills(),
	}


@frappe.whitelist()
def get_ap_weekly_log(supplier, company):
	"""Full history for one supplier+company, newest first."""
	_require_access()
	return frappe.get_all(
		"AP Weekly Entry",
		filters={"supplier": supplier, "company": company},
		fields=[
			"name", "week_of", "status", "qa", "plan", "notes",
			"contact", "email", "need_finance_signoff",
			"tier_snapshot", "amount_snapshot", "owner",
		],
		order_by="week_of desc, creation desc",
	)


@frappe.whitelist()
def add_ap_weekly_entry(supplier, company, status, qa=None, plan=None, notes=None,
                        contact=None, email=None, need_finance_signoff=0):
	"""File this week's entry.

	week_of, tier_snapshot and amount_snapshot are all computed here -- never
	taken from the client -- so the log stays honest even if the page is stale.
	"""
	_require_access()

	if not status:
		frappe.throw(_("Pick a status before saving this week's entry."))

	tier, amount = _snapshot_for(supplier, company)

	doc = frappe.get_doc({
		"doctype": "AP Weekly Entry",
		"supplier": supplier,
		"company": company,
		"week_of": week_start(),
		"status": status,
		"qa": qa,
		"plan": plan,
		"notes": notes,
		"contact": contact,
		"email": email,
		"need_finance_signoff": 1 if frappe.parse_json(str(need_finance_signoff).lower()) else 0,
		"tier_snapshot": tier,
		"amount_snapshot": amount,
	})
	doc.insert()
	return {"name": doc.name, "week_of": str(doc.week_of), "tier_snapshot": tier}


def _snapshot_for(supplier, company):
	"""Worst tier and total payable for a supplier+company right now.

	A supplier can hold an upcoming row and an overdue row at once; the log
	records the worst tier and the combined balance, which is what someone
	reading the history later actually wants to know.
	"""
	tier, amount = "upcoming", 0.0
	for r in _build_rows(company):
		if r["supplier"] != supplier or r["company"] != company:
			continue
		amount += r["amount"]
		if TIER_RANK[r["tier"]] > TIER_RANK[tier]:
			tier = r["tier"]
	return tier, amount
