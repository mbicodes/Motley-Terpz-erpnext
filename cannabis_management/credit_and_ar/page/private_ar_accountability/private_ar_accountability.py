import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.api.sheet_export import send_csv, send_xlsx
from cannabis_management.credit_and_ar.doctype.ar_weekly_entry.ar_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)
from cannabis_management.credit_and_ar.page.ar_weekly_review.ar_weekly_review import (
	TIER_LABELS,
	_attach_customer_info,
	_build_rows,
	_customer_columns,
	_snapshot_for,
)
from cannabis_management.credit_and_ar.utils import NEW_AR_START

PAGE_ROLE = "Private AR Accountability"
ENTRY_DOCTYPE = "Private AR Weekly Entry"


def _require_access():
	if PAGE_ROLE not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _latest_entries():
	rows = frappe.db.sql(
		"""
		select e.customer, e.ledger, e.status, e.week_of, e.qa, e.plan, e.notes
		from `tabPrivate AR Weekly Entry` e
		inner join (
			select customer, ledger, max(week_of) as week_of
			from `tabPrivate AR Weekly Entry` group by customer, ledger
		) latest
		on latest.customer = e.customer and latest.ledger = e.ledger
		and latest.week_of = e.week_of
		""",
		as_dict=True,
	)
	counts = frappe.db.sql(
		"""select customer, ledger, count(*) n from `tabPrivate AR Weekly Entry`
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
		ENTRY_DOCTYPE,
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
		"doctype": ENTRY_DOCTYPE,
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
		ENTRY_DOCTYPE,
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
		_("Private AR Accountability {0}").format(nowdate()),
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
	send_csv(_("Private AR Accountability {0}").format(nowdate()), grid)
