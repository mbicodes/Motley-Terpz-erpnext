import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.api.sheet_export import send_csv, send_xlsx
from cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard import (
	AR_FLAG_FIELDS,
	_can_edit_recon,
	get_recon_statuses,
)
from cannabis_management.cannabis_management.page.ar_legacy.ar_legacy import (
	NOT_REACHED_OUT,
	REACH_OUT_FIELD,
	REACH_OUT_STATUSES,
	SEGMENT_FIELD,
	UNASSIGNED,
	get_segments,
)
from cannabis_management.cannabis_management.page.ar_legacy.ar_legacy import _can_edit as _can_edit_segment
from cannabis_management.credit_and_ar.utils import NEW_AR_START
from cannabis_management.credit_and_ar.doctype.ar_weekly_entry.ar_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)

PAGE_ROLE = "AR Weekly Review"


def _require_access():
	if PAGE_ROLE not in frappe.get_roles():
		frappe.throw(
			_("You are not permitted to view AR Accountability."),
			frappe.PermissionError,
		)

RECON_FIELD = "custom_reconciliation_status"


def _attach_customer_info(rows):
	wanted = {"recon_status": RECON_FIELD, "segment": SEGMENT_FIELD, "reach_out": REACH_OUT_FIELD}
	wanted.update(AR_FLAG_FIELDS)
	present = {k: f for k, f in wanted.items() if frappe.db.has_column("Customer", f)}

	customers = sorted({r["customer"] for r in rows})
	info = {}
	if customers and present:
		for c in frappe.get_all("Customer", filters={"name": ["in", customers]},
		                        fields=["name"] + list(present.values())):
			info[c.name] = {k: c.get(f) or "" for k, f in present.items()}
	for r in rows:
		values = info.get(r["customer"], {})
		for k in wanted:
			r[k] = values.get(k, "")
		r["reach_out"] = r["reach_out"] or NOT_REACHED_OUT

	segments = get_segments()
	return {
		"recon_statuses": get_recon_statuses(),
		"segments": [s["value"] for s in segments],
		"segment_colors": {s["value"]: s["color"] for s in segments if s.get("color")},
		"unassigned_label": UNASSIGNED,
		"can_edit_recon": _can_edit_recon(),
		"can_edit_segment": bool(_can_edit_segment() and "segment" in present),
		"reach_out_statuses": REACH_OUT_STATUSES,
		"can_edit_reach_out": bool(_can_edit_segment() and "reach_out" in present),
	}


def _customer_columns(r):
	return [r.get("recon_status") or "", r.get("onboarding") or "",
	        r.get("company_made_contact") or "", r.get("segment") or UNASSIGNED,
	        r.get("reach_out") or NOT_REACHED_OUT]

LEDGER_NEW = "New AR"
LEDGER_LEGACY = "Legacy AR"

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


def _internal_customers():
	return {
		c.name
		for c in frappe.get_all("Customer", filters={"is_internal_customer": 1}, fields=["name"])
	}


def _ledger_for(posting_date):
	return LEDGER_NEW if str(posting_date or "") >= NEW_AR_START else LEDGER_LEGACY


def _open_invoices():
	internal = _internal_customers()
	rows = frappe.db.sql(
		"""
		select si.name, si.customer, si.posting_date, si.due_date,
		       si.outstanding_amount, si.company,
		       if(ifnull(si.base_rounded_total, 0) != 0, si.base_rounded_total, si.base_grand_total) as invoiced
		from `tabSales Invoice` si
		where si.docstatus = 1 and si.outstanding_amount > 0
		""",
		as_dict=True,
	)
	return [r for r in rows if r.customer not in internal]


def _build_rows(ledger=None):
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
				"invoices": [],
			},
		)

		amount = flt(inv.outstanding_amount)
		g["amount"] += amount
		g["invoice_count"] += 1
		g["invoices"].append({
			"name": inv.name,
			"company": inv.company,
			"posting_date": str(inv.posting_date or ""),
			"due_date": str(inv.due_date or ""),
			"aging": label,
			"invoiced": flt(inv.invoiced),
			"paid": flt(inv.invoiced) - amount,
			"outstanding": amount,
		})
		b = g["_buckets"].setdefault(label, {"label": label, "amount": 0.0, "tier": tier})
		b["amount"] += amount

		if TIER_RANK[tier] >= TIER_RANK[g["tier"]]:
			g["tier"] = tier
		if _bucket_rank(label) >= _bucket_rank(g["days"]):
			g["days"] = label

	rows = []
	for g in groups.values():
		g["breakdown"] = sorted(g.pop("_buckets").values(), key=lambda b: _bucket_rank(b["label"]))
		g["invoices"].sort(key=lambda i: (i["due_date"] or "9999-12-31", i["name"]))
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
		out[(r.customer, r.ledger)] = {
			"current_status": r.status or "",
			"latest_note": r.qa or r.plan or r.notes or "",
			"latest_week": str(r.week_of or ""),
			"log_count": count_map.get((r.customer, r.ledger), 0),
		}
	return out


@frappe.whitelist()
def get_ar_weekly_review(ledger=None):
	_require_access()
	rows = _build_rows(ledger)
	latest = _latest_entries()

	for r in rows:
		info = latest.get((r["customer"], r["ledger"]))
		r["current_status"] = info["current_status"] if info else ""
		r["latest_note"] = info["latest_note"] if info else ""
		r["log_count"] = info["log_count"] if info else 0
		r["statuses"] = STATUSES_BY_TIER.get(r["tier"], [])

	out = {
		"rows": rows,
		"as_of": nowdate(),
		"week_of": str(week_start()),
		"new_ar_start": NEW_AR_START,
	}
	out.update(_attach_customer_info(rows))
	return out


@frappe.whitelist()
def get_ar_weekly_log(customer, ledger):
	_require_access()
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
	_require_access()

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
	tier, amount = "upcoming", 0.0
	for r in _build_rows(ledger):
		if r["customer"] != customer or r["ledger"] != ledger:
			continue
		amount += r["amount"]
		if TIER_RANK[r["tier"]] > TIER_RANK[tier]:
			tier = r["tier"]
	return tier, amount

TIER_LABELS = {
	"upcoming": "Upcoming Terms Due",
	"level1": "Bad Debt Level 1 (0-30)",
	"level2": "Bad Debt Level 2 (30-60)",
	"level3": "Bad Debt Level 3 (60+)",
}


def _export_tables(ledger=None):
	rows = _build_rows(ledger)
	latest = _latest_entries()
	for r in rows:
		info = latest.get((r["customer"], r["ledger"]))
		r["current_status"] = info["current_status"] if info else ""
		r["latest_note"] = info["latest_note"] if info else ""
		r["log_count"] = info["log_count"] if info else 0
	_attach_customer_info(rows)

	grid = [[
		"Customer", "Ledger", "Portion", "Level", "Worst Aging", "Amount",
		"Invoices", "Recon Status", "Onboarding", "Company Made Contact", "Segment",
		"Reach Out Status",
		"Current Status", "Latest Note", "Entries Filed",
	]]
	aging = [["Customer", "Ledger", "Portion", "Aging Bucket", "Amount"]]

	for r in rows:
		portion = "On terms" if r["portion"] == "upcoming" else "Overdue"
		grid.append([
			r["customer"], r["ledger"], portion,
			TIER_LABELS.get(r["tier"], r["tier"]), r["days"],
			flt(r["amount"], 2), r["invoice_count"], *_customer_columns(r),
			r["current_status"], r["latest_note"], r["log_count"],
		])
		for b in r["breakdown"]:
			aging.append([r["customer"], r["ledger"], portion, b["label"], flt(b["amount"], 2)])

	log = [[
		"Customer", "Ledger", "Week Of", "Status", "Tier At Entry",
		"Outstanding At Entry", "What is going on?", "What is the plan?",
		"Notes", "Contact", "Email", "Need Three-Way Call", "Filed By",
	]]
	for e in frappe.get_all(
		"AR Weekly Entry",
		fields=["customer", "ledger", "week_of", "status", "tier_snapshot",
		        "amount_snapshot", "qa", "plan", "notes", "contact", "email",
		        "need_three_way_call", "owner"],
		order_by="week_of desc, creation desc",
	):
		log.append([
			e.customer, e.ledger, getdate(e.week_of) if e.week_of else None,
			e.status, TIER_LABELS.get(e.tier_snapshot, e.tier_snapshot or ""),
			flt(e.amount_snapshot, 2), e.qa, e.plan, e.notes, e.contact, e.email,
			"Yes" if e.need_three_way_call else "No", e.owner,
		])

	return grid, aging, log


@frappe.whitelist()
def export_xlsx(ledger=None):
	_require_access()
	grid, aging, log = _export_tables(ledger)
	send_xlsx(
		_("AR Accountability {0}").format(nowdate()),
		[
			("Receivables", grid, [34, 12, 11, 24, 14, 14, 10, 28, 12, 20, 24, 20, 26, 48, 13]),
			("Aging Breakdown", aging, [34, 12, 11, 16, 14]),
			("Weekly Entries", log, [34, 12, 12, 24, 24, 18, 44, 44, 44, 20, 24, 18, 24]),
		],
	)


@frappe.whitelist()
def export_csv(ledger=None):
	_require_access()
	grid, _aging, _log = _export_tables(ledger)
	send_csv(_("AR Accountability {0}").format(nowdate()), grid)
