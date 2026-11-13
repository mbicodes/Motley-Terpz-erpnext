# Sales Operation Board v2 (change request 13 Nov 2026): seed Sales Pipeline Settings, map old free-text
# values to the new dropdowns (unmatched text goes to Deal Notes), start a stage log on every deal,
# link Customers / create Leads, and add the 4 deals from Matt's owner sections. Safe to run twice.

import frappe
from frappe.utils import cint, now_datetime

from cannabis_management import sales_ops

DT = "Sales Pipeline Deal"

STAGES = [
	# stage, probability, max days, colour, closed, won, notify managers
	("Lead", 10, 21, "#6B7280", 0, 0, 0),
	("Qualified", 20, 10, "#2563EB", 0, 0, 0),
	("Sampling", 35, 7, "#9333EA", 0, 0, 0),
	("Testing / QC", 50, 7, "#EA580C", 0, 0, 0),
	("Pending Buyer", 65, 5, "#DB2777", 0, 0, 0),
	("Buyer Ready", 85, 3, "#16A34A", 0, 0, 1),
	("Closed Won", 100, 0, "#166534", 1, 1, 1),
	("Closed Lost", 0, 0, "#B91C1C", 1, 0, 0),
]
OWNERS = [
	("matt@motleyterpz.com", "Matt", "#0F766E", 1),
	("douglas@motleyterpz.com", "Douglas", "#1D4ED8", 0),
	("dominic@motleyterpz.com", "Dom", "#B45309", 0),
	("alex@motleyterpz.com", "Alex", "#7C3AED", 0),
	("nikki@motleyterpz.com", "Nikki", "#BE185D", 0),
]
MAIN = "Main Storage - MTM"
PRODUCT_LINES = [
	("Cold Cure", "Food grade", ["Food Grade"], MAIN),
	("Cold Cure", "T1", ["Tier 1", "Tier 1 Plus"], MAIN),
	("Cold Cure", "T1 or T2", ["Tier 1", "Tier 1 Plus", "Tier 2"], MAIN),
	("Cold Cure", "T2", ["Tier 2"], MAIN),
	("Cold Cure", "T3", ["Tier 3"], MAIN),
	("VRR", "T1", ["VRR Tier 1"], MAIN),
	("VRR", "T1 or T2", ["VRR Tier 1", "VRR Tier 2"], MAIN),
	("VRR", "T2", ["VRR Tier 2"], MAIN),
	("VRR", "T3", ["VRR Tier 3"], MAIN),
	("LLR", "T1", ["LLR Tier 1"], MAIN),
	("LLR", "T1 or T2", ["LLR Tier 1", "LLR Tier 2"], MAIN),
	("LLR", "T2", ["LLR Tier 2"], MAIN),
	("LLR", "T3", ["LLR Tier 3"], MAIN),
	("Distillate", "", [], ""),
	("Edibles", "", [], ""),
	("Bubble Hash", "", ["Bubble Hash"], ""),
	("Fresh Frozen", "", [], ""),
]
LISTS = {
	"priority_options": "High\nMedium\nLow",
	"tier_options": "Food grade\nT1\nT1 or T2\nT2\nT3",
	"samples_options": "Needed\nSamples\nSamples today\nSent\nApproved\n?",
	"samples_done_options": "Sent\nApproved",
	"hardware_options": "YES\nNO\nClient provides",
	"payment_terms_options": "Prepaid\nCOD\nNet 7\nNet 15\nNet 30\nConsignment",
	"lead_source_options": "Referral\nExisting client\nInbound\nOutbound\nEvent",
}
CHECKS = [
	"alert_followup_overdue", "alert_followup_today", "alert_stalled", "alert_missing_owner",
	"alert_missing_value", "alert_short_stock", "alert_sample_due", "send_daily_digest",
	"notify_on_reassign", "notify_managers_on_stage",
]
# Account names that look like an existing Customer but are not an exact match: left for the user to confirm.
CUSTOMER_CANDIDATES = {
	"cake": 'Cake "She Hits Different"',
	"cannafusion": "Cannafusions",
	"simly marry gummies": "Simply Mary",
	"nature": "Nature's Lab",
}
NEW_DEALS = [
	{"account": "Terpz Distro", "deal_owner": "douglas@motleyterpz.com",
	 "deal_notes": "From Matt's sheet (Douglas): 5–10 kg a month. Grams and price to be confirmed."},
	{"account": "DOM VRR brand", "deal_owner": "dominic@motleyterpz.com", "product_line": "VRR",
	 "deal_notes": "From Matt's sheet (Dom): 60,000, \"15 kg?\". Set Value Override to $60,000 once Matt confirms the figure is dollars."},
	{"account": "Dom Frankie", "deal_owner": "dominic@motleyterpz.com",
	 "deal_notes": "From Matt's sheet (Dom): 20,000, \"2–3 kilo\". Set Value Override to $20,000 once confirmed."},
	{"account": "Bubble hash (account name to confirm)", "deal_owner": "alex@motleyterpz.com", "product_line": "Bubble Hash",
	 "deal_notes": "From Matt's sheet (Alex): 100,000. The account name is missing in the sheet."},
]


def execute():
	for dt in ("sales_pipeline_stage", "sales_pipeline_owner", "sales_pipeline_product_line",
			   "sales_pipeline_stage_log", "sales_pipeline_settings", "sales_pipeline_deal"):
		frappe.reload_doc("cannabis_management", "doctype", dt)
	seed_settings()
	sales_ops.clear_settings_memo()
	s = sales_ops.get_settings()
	map_select_values(s)
	start_stage_logs()
	link_parties()
	add_owner_section_deals()
	sales_ops.clear_settings_memo()
	s = sales_ops.get_settings()
	sales_ops.sync_deal_options(s)
	sales_ops.recompute_probabilities(s)


def seed_settings():
	doc = frappe.get_single("Sales Pipeline Settings")
	if doc.get("stages"):
		return
	for i, (stage, prob, days, colour, closed, won, notify) in enumerate(STAGES, start=1):
		doc.append("stages", {"stage": stage, "sort_order": i * 10, "probability": prob, "max_days": days,
			"colour": colour, "is_closed": closed, "is_won": won, "notify_managers": notify})
	for user, name, colour, manager in OWNERS:
		if frappe.db.exists("User", user):
			doc.append("owners", {"user": user, "display_name": name, "colour": colour, "active": 1, "is_manager": manager})
	for line, tier, groups, wh in PRODUCT_LINES:
		groups = [g for g in groups if frappe.db.exists("Item Group", g)]
		doc.append("product_lines", {"product_line": line, "tier": tier, "item_groups": "\n".join(groups),
			"warehouses": wh if wh and frappe.db.exists("Warehouse", wh) else ""})
	doc.stock_company = "Master Touch Manufacturing" if frappe.db.exists("Company", "Master Touch Manufacturing") else None
	doc.update(LISTS)
	for f in CHECKS:
		doc.set(f, 1)
	doc.sample_due_days = 2
	doc.hide_closed_after_days = 30
	doc.unassigned_alert_days = 2
	doc.flags.ignore_permissions = True
	doc.save()


def map_select_values(s):
	fields = {"samples": s.lists.samples, "hardware": s.lists.hardware,
			  "payment_terms": s.lists.payment_terms, "lead_source": s.lists.lead_source}
	labels = {"samples": "Samples", "hardware": "Hardware", "payment_terms": "Payment Terms", "lead_source": "Lead Source"}
	for d in frappe.get_all(DT, fields=["name", "deal_notes"] + list(fields)):
		updates, moved = {}, []
		for f, options in fields.items():
			v = (d.get(f) or "").strip()
			if not v or v in options:
				continue
			match = next((o for o in options if o.lower() == v.lower()), None)
			if match:
				updates[f] = match
			else:
				updates[f] = None
				moved.append("{0}: {1}".format(labels[f], v))
		if moved:
			updates["deal_notes"] = "\n".join(x for x in [(d.deal_notes or "").strip()] + moved if x)
		if updates:
			frappe.db.set_value(DT, d.name, updates, update_modified=False)


def start_stage_logs():
	for d in frappe.get_all(DT, fields=["name", "stage", "stage_changed_on", "creation", "owner"]):
		if frappe.db.exists("Sales Pipeline Stage Log", {"parent": d.name, "parenttype": DT}):
			continue
		row = frappe.get_doc({
			"doctype": "Sales Pipeline Stage Log", "parent": d.name, "parenttype": DT, "parentfield": "stage_log",
			"idx": 1, "from_stage": "", "to_stage": d.stage, "changed_on": d.stage_changed_on or d.creation,
			"changed_by": d.owner, "days_in_previous": 0,
		})
		row.db_insert()


def link_parties():
	customers = {}
	for c in frappe.get_all("Customer", fields=["name", "customer_name"], filters={"disabled": 0}):
		customers.setdefault((c.customer_name or "").strip().lower(), c.name)
	for d in frappe.get_all(DT, fields=["name", "account", "customer", "lead", "deal_owner"], order_by="creation asc"):
		if d.customer or d.lead:
			continue
		key = (d.account or "").strip().lower()
		if key in customers:
			frappe.db.set_value(DT, d.name, "customer", customers[key], update_modified=False)
			continue
		if key in CUSTOMER_CANDIDATES:
			continue
		lead = frappe.db.sql("select name from `tabLead` where lower(trim(company_name)) = %s order by creation limit 1", key)
		if lead:
			lead = lead[0][0]
		else:
			ld = frappe.get_doc({"doctype": "Lead", "company_name": d.account.strip(), "lead_owner": d.deal_owner})
			ld.flags.ignore_permissions = True
			ld.insert()
			lead = ld.name
		frappe.db.set_value(DT, d.name, "lead", lead, update_modified=False)


def add_owner_section_deals():
	active = {o.user for o in sales_ops.get_settings().owners if o.active}
	for row in NEW_DEALS:
		if frappe.db.exists(DT, {"account": row["account"]}) or row["deal_owner"] not in active:
			continue
		doc = frappe.get_doc(dict(doctype=DT, stage=sales_ops.get_settings().first_stage, **row))
		doc.flags.ignore_permissions = True
		doc.insert()
