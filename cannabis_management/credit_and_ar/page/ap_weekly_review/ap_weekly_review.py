import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.api.sheet_export import send_csv, send_xlsx
from cannabis_management.credit_and_ar.doctype.ap_weekly_entry.ap_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)

PAGE_ROLE = "AP Weekly Review"


def _require_access():
	if PAGE_ROLE not in frappe.get_roles():
		frappe.throw(
			_("You are not permitted to view AP Accountability."),
			frappe.PermissionError,
		)

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

TIER_RANK = {"upcoming": 0, "level1": 1, "level2": 2, "level3": 3}


def _bucket_for(days_overdue):
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
		out[(r.supplier, r.company)] = {
			"current_status": r.status or "",
			"latest_note": r.qa or r.plan or r.notes or "",
			"latest_week": str(r.week_of or ""),
			"log_count": count_map.get((r.supplier, r.company), 0),
		}
	return out


def _companies_with_bills():
	totals = {}
	for r in _build_rows():
		totals[r["company"]] = totals.get(r["company"], 0.0) + r["amount"]
	return [c for c, _amt in sorted(totals.items(), key=lambda kv: -kv[1])]


@frappe.whitelist()
def get_ap_weekly_review(company=None):
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
	tier, amount = "upcoming", 0.0
	for r in _build_rows(company):
		if r["supplier"] != supplier or r["company"] != company:
			continue
		amount += r["amount"]
		if TIER_RANK[r["tier"]] > TIER_RANK[tier]:
			tier = r["tier"]
	return tier, amount

TIER_LABELS = {
	"upcoming": "Upcoming - Not Yet Due",
	"level1": "Past Due Level 1 (0-30)",
	"level2": "Past Due Level 2 (30-60)",
	"level3": "Past Due Level 3 (60+)",
}


def _export_tables(company=None):
	rows = _build_rows(company)
	latest = _latest_entries()
	for r in rows:
		info = latest.get((r["supplier"], r["company"]))
		r["current_status"] = info["current_status"] if info else ""
		r["latest_note"] = info["latest_note"] if info else ""
		r["log_count"] = info["log_count"] if info else 0

	grid = [[
		"Supplier", "Supplier Name", "Company", "Portion", "Level", "Worst Aging",
		"Amount", "Bills", "On Hold Amount", "Bills On Hold", "Oldest Due",
		"Current Status", "Latest Note", "Entries Filed",
	]]
	aging = [["Supplier", "Supplier Name", "Company", "Portion", "Aging Bucket", "Amount"]]

	for r in rows:
		grid.append([
			r["supplier"], r["supplier_name"], r["company"],
			"Scheduled" if r["portion"] == "upcoming" else "Past due",
			TIER_LABELS.get(r["tier"], r["tier"]), r["days"],
			flt(r["amount"], 2), r["invoice_count"],
			flt(r["held_amount"], 2), r["held_count"],
			getdate(r["oldest_due"]) if r["oldest_due"] else None,
			r["current_status"], r["latest_note"], r["log_count"],
		])
		for b in r["breakdown"]:
			aging.append([
				r["supplier"], r["supplier_name"], r["company"],
				"Scheduled" if r["portion"] == "upcoming" else "Past due",
				b["label"], flt(b["amount"], 2),
			])

	log = [[
		"Supplier", "Company", "Week Of", "Status", "Tier At Entry",
		"Payable At Entry", "What is going on?", "When will this be paid?",
		"Notes", "Contact", "Email", "Need Finance Sign-off", "Filed By",
	]]
	for e in frappe.get_all(
		"AP Weekly Entry",
		fields=["supplier", "company", "week_of", "status", "tier_snapshot",
		        "amount_snapshot", "qa", "plan", "notes", "contact", "email",
		        "need_finance_signoff", "owner"],
		order_by="week_of desc, creation desc",
	):
		log.append([
			e.supplier, e.company, getdate(e.week_of) if e.week_of else None,
			e.status, TIER_LABELS.get(e.tier_snapshot, e.tier_snapshot or ""),
			flt(e.amount_snapshot, 2), e.qa, e.plan, e.notes, e.contact, e.email,
			"Yes" if e.need_finance_signoff else "No", e.owner,
		])

	return grid, aging, log


@frappe.whitelist()
def export_xlsx(company=None):
	_require_access()
	grid, aging, log = _export_tables(company)
	send_xlsx(
		_("AP Accountability {0}").format(nowdate()),
		[
			("Payables", grid, [26, 34, 26, 12, 24, 14, 14, 8, 15, 13, 13, 26, 48, 13]),
			("Aging Breakdown", aging, [26, 34, 26, 12, 16, 14]),
			("Weekly Entries", log, [26, 26, 12, 28, 24, 16, 44, 44, 44, 20, 24, 18, 24]),
		],
	)


@frappe.whitelist()
def export_csv(company=None):
	_require_access()
	grid, _aging, _log = _export_tables(company)
	send_csv(_("AP Accountability {0}").format(nowdate()), grid)
