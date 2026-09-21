# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""AR Weekly Review — server side.

Tier and outstanding amount are never stored per customer (spec §3): they are
recomputed from Sales Invoice on every load, which is what makes an account
slide from Upcoming into Level 1 the day it passes its due date without any
batch job.

The New AR / Legacy AR split follows option (b) of spec §5 — derived from
posting_date against the project-wide cutover — because Sales Invoice.custom_ledger
is unset on effectively every invoice. NEW_AR_START is imported rather than
re-declared so this page can never drift from the rest of the AR code.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.credit_and_ar.utils import NEW_AR_START
from cannabis_management.credit_and_ar.doctype.ar_weekly_entry.ar_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)

LEDGER_NEW = "New AR"
LEDGER_LEGACY = "Legacy AR"

# (upper bound in days overdue, label, tier). None = no upper bound.
# Matches the bucket table in spec §3 and the badges in the mockup.
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


def _internal_customers():
	return {
		c.name
		for c in frappe.get_all("Customer", filters={"is_internal_customer": 1}, fields=["name"])
	}


def _ledger_for(posting_date):
	return LEDGER_NEW if str(posting_date or "") >= NEW_AR_START else LEDGER_LEGACY


def _open_invoices():
	"""Every submitted, still-outstanding, non-intercompany Sales Invoice."""
	internal = _internal_customers()
	rows = frappe.db.sql(
		"""
		select si.name, si.customer, si.posting_date, si.due_date,
		       si.outstanding_amount, si.company
		from `tabSales Invoice` si
		where si.docstatus = 1 and si.outstanding_amount > 0
		""",
		as_dict=True,
	)
	return [r for r in rows if r.customer not in internal]


def _build_rows(ledger=None):
	"""The §3 aggregation.

	One row per customer + ledger + portion, where portion is "upcoming" (nothing
	yet due) or "overdue". The two are kept apart deliberately: an on-terms
	balance and an overdue balance for the same customer need different
	conversations, and only one of them is moving.
	"""
	today = getdate(nowdate())
	groups = {}

	for inv in _open_invoices():
		inv_ledger = _ledger_for(inv.posting_date)
		if ledger and ledger != "all" and inv_ledger != ledger:
			continue

		days_overdue = (today - getdate(inv.due_date)).days if inv.due_date else 0
		label, tier = _bucket_for(days_overdue)
		portion = "upcoming" if tier == "upcoming" else "overdue"

		key = (inv.customer, inv_ledger, portion)
		g = groups.setdefault(
			key,
			{
				"id": "{0}|{1}|{2}".format(inv.customer, inv_ledger, portion),
				"customer": inv.customer,
				"ledger": inv_ledger,
				"portion": portion,
				"amount": 0.0,
				"tier": "upcoming",
				"days": label,
				"_buckets": {},
				"invoice_count": 0,
			},
		)

		amount = flt(inv.outstanding_amount)
		g["amount"] += amount
		g["invoice_count"] += 1
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


def _bucket_rank(label):
	if label == ON_TERMS[0]:
		return -1
	for i, (_upper, lbl, _tier) in enumerate(BUCKETS):
		if lbl == label:
			return i
	return -1


def _latest_entries():
	"""Most recent AR Weekly Entry per customer+ledger, plus how many exist.

	Status is keyed on customer + ledger (spec §3), not per portion — so an
	account's upcoming and overdue rows share one weekly log.
	"""
	rows = frappe.db.sql(
		"""
		select e.customer, e.ledger, e.status, e.week_of, e.qa, e.plan, e.notes
		from `tabAR Weekly Entry` e
		inner join (
			select customer, ledger, max(week_of) as week_of
			from `tabAR Weekly Entry` group by customer, ledger
		) latest
		on latest.customer = e.customer and latest.ledger = e.ledger
		and latest.week_of = e.week_of
		""",
		as_dict=True,
	)
	counts = frappe.db.sql(
		"""select customer, ledger, count(*) n from `tabAR Weekly Entry`
		   group by customer, ledger""",
		as_dict=True,
	)
	count_map = {(c.customer, c.ledger): c.n for c in counts}

	out = {}
	for r in rows:
		# max(week_of) can tie if two entries were filed the same week; last wins.
		out[(r.customer, r.ledger)] = {
			"current_status": r.status or "",
			"latest_note": r.qa or r.plan or r.notes or "",
			"latest_week": str(r.week_of or ""),
			"log_count": count_map.get((r.customer, r.ledger), 0),
		}
	return out


@frappe.whitelist()
def get_ar_weekly_review(ledger=None):
	"""Method 1 (spec §4): the whole grid in one call."""
	rows = _build_rows(ledger)
	latest = _latest_entries()

	for r in rows:
		info = latest.get((r["customer"], r["ledger"]))
		r["current_status"] = info["current_status"] if info else ""
		r["latest_note"] = info["latest_note"] if info else ""
		r["log_count"] = info["log_count"] if info else 0
		r["statuses"] = STATUSES_BY_TIER.get(r["tier"], [])

	return {
		"rows": rows,
		"as_of": nowdate(),
		"week_of": str(week_start()),
		"new_ar_start": NEW_AR_START,
	}


@frappe.whitelist()
def get_ar_weekly_log(customer, ledger):
	"""Method 2 (spec §4): full history for one customer+ledger, newest first."""
	return frappe.get_all(
		"AR Weekly Entry",
		filters={"customer": customer, "ledger": ledger},
		fields=[
			"name", "week_of", "status", "qa", "plan", "notes",
			"contact", "email", "need_three_way_call",
			"tier_snapshot", "amount_snapshot", "owner",
		],
		order_by="week_of desc, creation desc",
	)


@frappe.whitelist()
def add_ar_weekly_entry(customer, ledger, status, qa=None, plan=None, notes=None,
                        contact=None, email=None, need_three_way_call=0):
	"""Method 3 (spec §4): file this week's entry.

	week_of, tier_snapshot and amount_snapshot are all computed here — never
	taken from the client — so the log stays honest even if the page is stale.
	"""
	if not status:
		frappe.throw(_("Pick a status before saving this week's entry."))

	tier, amount = _snapshot_for(customer, ledger)

	doc = frappe.get_doc({
		"doctype": "AR Weekly Entry",
		"customer": customer,
		"ledger": ledger,
		"week_of": week_start(),
		"status": status,
		"qa": qa,
		"plan": plan,
		"notes": notes,
		"contact": contact,
		"email": email,
		"need_three_way_call": 1 if frappe.parse_json(str(need_three_way_call).lower()) else 0,
		"tier_snapshot": tier,
		"amount_snapshot": amount,
	})
	doc.insert()
	return {"name": doc.name, "week_of": str(doc.week_of), "tier_snapshot": tier}


def _snapshot_for(customer, ledger):
	"""Worst tier and total outstanding for a customer+ledger right now.

	A customer can hold an upcoming row and an overdue row at once; the log
	records the worst tier and the combined balance, which is what someone
	reading the history later actually wants to know.
	"""
	tier, amount = "upcoming", 0.0
	for r in _build_rows(ledger):
		if r["customer"] != customer or r["ledger"] != ledger:
			continue
		amount += r["amount"]
		if TIER_RANK[r["tier"]] > TIER_RANK[tier]:
			tier = r["tier"]
	return tier, amount
