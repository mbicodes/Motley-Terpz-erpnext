# Sales Operation Board v3 (15 Nov 2026): the Leads board becomes one card per account (relationship) with
# lead statuses; the Deals board keeps the deals, several per account.
# 1. Stage table: Board = Lead rows are now lead statuses (Lead, Qualified Lead, Active / Recurring / Dormant /
#    Lost Customer); deal stages follow Matt's list (In Discussion moves to Deals, Proposal / Quote Sent added,
#    Pending Buyer renamed Pending Buyer Approval, Recurring becomes a lead status).
# 2. Deals in the old Lead stage move to Active Opportunity (their product and value are kept).
# 3. One Sales Pipeline Account per buyer (Customer, else Lead, else account name); every deal is linked.
#    The first lead status is worked out from Sales Invoices and the deals. Safe to run twice.

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from cannabis_management import sales_ops

DT = sales_ops.DEAL
ACC = sales_ops.ACCOUNT

LEAD_STATUSES = [
	# status, probability (weighs monthly potential), max days, colour, closed, active customer
	("Lead", 10, 21, "#6B7280", 0, 0),
	("Qualified Lead", 30, 14, "#0EA5E9", 0, 0),
	("Active Customer", 75, 0, "#16A34A", 0, 1),
	("Recurring Customer", 90, 0, "#0D9488", 0, 1),
	("Dormant Customer", 10, 0, "#CA8A04", 0, 0),
	("Lost Customer", 0, 0, "#B91C1C", 1, 0),
]
DEAL_STAGES = [
	# stage, probability, max days, colour, closed, won, notify managers
	("Active Opportunity", 20, 10, "#2563EB", 0, 0, 0),
	("In Discussion", 25, 10, "#0EA5E9", 0, 0, 0),
	("Sampling", 35, 7, "#9333EA", 0, 0, 0),
	("Testing / QC", 50, 7, "#EA580C", 0, 0, 0),
	("Proposal / Quote Sent", 60, 5, "#CA8A04", 0, 0, 0),
	("Pending Buyer Approval", 65, 5, "#DB2777", 0, 0, 0),
	("Buyer Ready", 85, 3, "#16A34A", 0, 0, 1),
	("Closed Won", 100, 0, "#166534", 1, 1, 1),
	("Closed Lost", 0, 0, "#B91C1C", 1, 0, 0),
]
RENAMED = {"Pending Buyer": "Pending Buyer Approval"}
OLD_LEAD_STAGES = ("Lead",)  # deals in these move to the first deal stage
ACTIVE_DAYS = 120  # an invoice within this many days = still buying
RECURRING_MONTHS = 3  # invoices in at least this many different months = recurring


def execute():
	for dt in ("sales_pipeline_stage", "sales_pipeline_settings", "sales_pipeline_volume", "sales_pipeline_account", "sales_pipeline_deal"):
		frappe.reload_doc("cannabis_management", "doctype", dt)
	frappe.flags.in_patch = True
	restructure_stages()
	sales_ops.clear_settings_memo()
	s = sales_ops.get_settings()
	sales_ops.sync_deal_options(s)
	sales_ops.clear_settings_memo()
	s = sales_ops.get_settings()
	created = link_accounts(s)
	set_first_statuses(s, created)
	move_lead_stage_deals(s)
	sales_ops.recompute_probabilities(s)


def restructure_stages():
	doc = frappe.get_single("Sales Pipeline Settings")
	if any(r.stage == "Qualified Lead" and r.board == "Lead" for r in doc.stages):
		return
	old = {r.stage: r for r in doc.stages}
	# deals in a renamed stage follow it
	for a, b in RENAMED.items():
		frappe.db.sql("update `tab{0}` set stage = %s where stage = %s".format(DT), (b, a))
	rows = []
	for i, (name, prob, days, colour, closed, active) in enumerate(LEAD_STATUSES, start=1):
		rows.append({"stage": name, "board": "Lead", "sort_order": i * 10, "probability": prob, "max_days": days,
			"colour": colour, "is_closed": closed, "is_won": 0, "notify_managers": 0, "is_active_customer": active})
	for i, (name, prob, days, colour, closed, won, notify) in enumerate(DEAL_STAGES, start=1):
		prev = old.get(name) or next((old[a] for a, b in RENAMED.items() if b == name and a in old), None)
		row = {"stage": name, "board": "Deal", "sort_order": 100 + i * 10, "probability": prob, "max_days": days,
			"colour": colour, "is_closed": closed, "is_won": won, "notify_managers": notify, "is_active_customer": 0}
		if prev and prev.board == "Deal":
			# keep what the team tuned on existing deal stages
			row.update({"probability": prev.probability, "max_days": prev.max_days, "colour": prev.colour or colour,
				"notify_managers": prev.notify_managers})
		rows.append(row)
	doc.set("stages", [])
	for r in rows:
		doc.append("stages", r)
	if not doc.get("lost_reason_options"):
		doc.lost_reason_options = "\n".join(sales_ops.DEFAULT_LOST_REASONS)
	doc.flags.ignore_permissions = True
	doc.save()


def _customer_of(customer, lead):
	if customer:
		return customer
	if lead:
		return frappe.db.get_value("Customer", {"lead_name": lead}, "name")
	return None


def link_accounts(s):
	"""One account per buyer. Deals are grouped by Customer, then Lead, then account name. Returns the new accounts."""
	created = set()
	rows = frappe.get_all(DT, fields=["name", "account", "customer", "lead", "deal_owner", "contact_name", "phone", "email",
		"location_address", "license_number", "lead_source", "stage", "modified", "pipeline_account"], order_by="modified desc")
	for d in rows:
		if d.pipeline_account:
			continue
		acc = sales_ops.find_account(d.customer, d.lead, d.account)
		if not acc:
			acc = sales_ops.make_account({
				"account_name": d.account, "account_owner": d.deal_owner, "customer": d.customer, "lead": d.lead,
				"contact_name": d.contact_name, "phone": d.phone, "email": d.email, "location_address": d.location_address,
				"license_number": d.license_number, "lead_source": d.lead_source,
			}).name
			created.add(acc)
		else:
			# the account learns the Customer / contact details another deal of the same buyer has
			cur = frappe.db.get_value(ACC, acc, ["customer", "lead", "contact_name", "phone", "email", "location_address", "license_number"], as_dict=True)
			upd = {f: d[f] for f in ("customer", "contact_name", "phone", "email", "location_address", "license_number") if d.get(f) and not cur.get(f)}
			if d.lead and not cur.lead and not cur.customer:
				upd["lead"] = d.lead
			if upd:
				frappe.db.set_value(ACC, acc, upd, update_modified=False)
		frappe.db.set_value(DT, d.name, "pipeline_account", acc, update_modified=False)
	return created


def move_lead_stage_deals(s):
	first = s.first_stage
	for name in frappe.get_all(DT, filters={"stage": ("in", OLD_LEAD_STAGES)}, pluck="name"):
		doc = frappe.get_doc(DT, name)
		doc.stage = first
		doc.flags.ignore_permissions = True
		doc.save()


def set_first_statuses(s, created):
	"""First lead status of each new account, from its Sales Invoices and its deals (run before the Lead-stage move):
	invoices in the last 120 days -> Recurring Customer (3+ months with invoices) or Active Customer; older invoices only
	-> Dormant Customer; a won deal -> Active Customer; a deal past In Discussion -> Qualified Lead; otherwise Lead."""
	today = getdate(nowdate())
	cutoff = getdate(add_days(today, -ACTIVE_DAYS))
	won = sales_ops.won_stage(s)
	worked_stages = {x.name for x in s.stages if not x.is_closed} - {"In Discussion"}
	names = {x.name for x in s.lead_statuses}
	for name in created:
		a = frappe.db.get_value(ACC, name, ["name", "customer", "lead"], as_dict=True)
		customer = _customer_of(a.customer, a.lead)
		status = None
		if customer:
			inv = frappe.db.sql(
				"""select count(distinct date_format(posting_date, '%%Y-%%m')) months, max(posting_date) last
				from `tabSales Invoice` where customer = %s and docstatus = 1 and is_return = 0""", customer, as_dict=True)[0]
			if inv.last:
				if getdate(inv.last) >= cutoff:
					status = "Recurring Customer" if (inv.months or 0) >= RECURRING_MONTHS else "Active Customer"
				else:
					status = "Dormant Customer"
		stages = set(frappe.get_all(DT, filters={"pipeline_account": name}, pluck="stage"))
		if not status and won and won.name in stages:
			status = "Active Customer"
		if not status:
			status = "Qualified Lead" if stages & worked_stages else "Lead"
		upd = {"lead_status": status if status in names else s.first_status, "status_changed_on": now_datetime()}
		if customer and not a.customer:
			upd["customer"] = customer
		frappe.db.set_value(ACC, name, upd, update_modified=False)
