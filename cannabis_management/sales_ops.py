# Sales Operation Board (/app/sales-operation-board): shared rules for Sales Pipeline Deal.
# Settings come from the single DocType "Sales Pipeline Settings"; nothing about stages, owners,
# product lines or alert switches is hard-coded here. Used by the deal controller, the page API,
# the permission hooks and the daily digest.

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, formatdate, get_datetime, get_url, getdate, nowdate

DEAL = "Sales Pipeline Deal"
ACCOUNT = "Sales Pipeline Account"
VOLUME = "Sales Pipeline Volume"
SETTINGS = "Sales Pipeline Settings"
CO_OWNER = "Sales Pipeline Co Owner"
REQUIREMENT = "Sales Pipeline Requirement"
# Stage rows with Board = Deal are deal stages; Board = Lead rows are the lead statuses of an account.
BOARDS = ("Lead", "Deal")
BOARD_ROUTE = "sales-operation-board"
UNIT_GRAMS = {"g": 1.0, "kg": 1000.0, "lb": 453.59237}
WEEKS_PER_MONTH = 52.0 / 12.0
DEFAULT_LOST_REASONS = [
	"Price too high", "Failed testing / QC", "Went with another supplier", "No response from the buyer",
	"Not the right product", "Timing / no budget", "Other",
]

# Deal fields whose Select options are driven by Settings: fieldname -> settings list key.
SELECT_SOURCES = {
	"priority": "priority",
	"tier": "tier",
	"samples": "samples",
	"hardware": "hardware",
	"payment_terms": "payment_terms",
	"lead_source": "lead_source",
}


def _lines(text):
	out = []
	for line in (text or "").replace(",", "\n").splitlines():
		line = line.strip()
		if line and line not in out:
			out.append(line)
	return out


def _plain_lines(text):
	"""Like _lines but keeps commas (list options such as 'Net 7')."""
	out = []
	for line in (text or "").splitlines():
		line = line.strip()
		if line and line not in out:
			out.append(line)
	return out


def get_settings():
	"""Settings as a plain dict, memoised for the request."""
	if getattr(frappe.local, "sales_ops_settings", None) is not None:
		return frappe.local.sales_ops_settings
	doc = frappe.get_cached_doc(SETTINGS)
	stages = sorted(doc.get("stages") or [], key=lambda r: (cint(r.sort_order), r.idx))
	all_rows = [
		frappe._dict(
			name=(r.stage or "").strip(),
			sort_order=cint(r.sort_order),
			probability=flt(r.probability),
			max_days=cint(r.max_days),
			colour=r.colour or "",
			board=r.get("board") if r.get("board") in BOARDS else "Deal",
			is_closed=cint(r.is_closed),
			is_won=cint(r.is_won),
			notify_managers=cint(r.notify_managers),
			is_active_customer=cint(r.get("is_active_customer")),
		)
		for r in stages
		if (r.stage or "").strip()
	]
	stage_list = [x for x in all_rows if x.board == "Deal"]
	lead_statuses = [x for x in all_rows if x.board == "Lead"]
	open_stages = [x for x in stage_list if not x.is_closed]
	open_statuses = [x for x in lead_statuses if not x.is_closed]
	product_lines = []
	for r in doc.get("product_lines") or []:
		if not (r.product_line or "").strip():
			continue
		product_lines.append(
			frappe._dict(
				product_line=r.product_line.strip(),
				tier=(r.tier or "").strip(),
				item_groups=_lines(r.item_groups),
				warehouses=_lines(r.warehouses),
				default_price=flt(r.default_price),
				quotation_item=r.quotation_item or "",
				unit=r.get("unit") if r.get("unit") in UNIT_GRAMS else "",
				group=(r.get("product_group") or "").strip(),
			)
		)
	line_names = []
	line_units = {}
	line_groups = {}
	for r in product_lines:
		if r.product_line not in line_names:
			line_names.append(r.product_line)
		if r.unit and r.product_line not in line_units:
			line_units[r.product_line] = r.unit
		if r.group and r.product_line not in line_groups:
			line_groups[r.product_line] = r.group
	s = frappe._dict(
		stages=stage_list,
		first_stage=open_stages[0].name if open_stages else (stage_list[0].name if stage_list else None),
		lead_statuses=lead_statuses,
		first_status=open_statuses[0].name if open_statuses else (lead_statuses[0].name if lead_statuses else None),
		owners=[
			frappe._dict(
				user=r.user,
				name=(r.display_name or "").strip() or r.user,
				colour=r.colour or "",
				active=cint(r.active),
				is_manager=cint(r.is_manager),
				no_email=cint(r.get("no_email")),
			)
			for r in (doc.get("owners") or [])
			if r.user
		],
		product_lines=product_lines,
		product_line_names=line_names,
		# {"Fresh Frozen": "lb", "VRR": "g"}: how the team counts each line
		line_units={n: line_units.get(n) or "g" for n in line_names},
		# {"VRR": "Extracts", "Fresh Frozen": "Fresh Frozen", "Tolling": "Tolling"}: the board totals one group at a time
		line_groups={n: line_groups.get(n) or n for n in line_names},
		stock_company=doc.stock_company,
		lists=frappe._dict(
			priority=_plain_lines(doc.priority_options) or ["High", "Medium", "Low"],
			tier=_plain_lines(doc.tier_options),
			samples=_plain_lines(doc.samples_options),
			samples_done=_plain_lines(doc.samples_done_options),
			hardware=_plain_lines(doc.hardware_options),
			payment_terms=_plain_lines(doc.payment_terms_options),
			lead_source=_plain_lines(doc.lead_source_options),
			quick_notes=_plain_lines(doc.get("quick_note_options")),
			lost_reasons=_plain_lines(doc.get("lost_reason_options")) or list(DEFAULT_LOST_REASONS),
		),
		alerts=frappe._dict(
			followup_overdue=cint(doc.alert_followup_overdue),
			followup_today=cint(doc.alert_followup_today),
			stalled=cint(doc.alert_stalled),
			missing_owner=cint(doc.alert_missing_owner),
			missing_value=cint(doc.alert_missing_value),
			short_stock=cint(doc.alert_short_stock),
			sample_due=cint(doc.alert_sample_due),
		),
		sample_due_days=cint(doc.sample_due_days),
		hide_closed_after_days=cint(doc.hide_closed_after_days),
		send_daily_digest=cint(doc.send_daily_digest),
		notify_on_reassign=cint(doc.notify_on_reassign),
		notify_managers_on_stage=cint(doc.notify_managers_on_stage),
		unassigned_alert_days=cint(doc.unassigned_alert_days),
		email_cc=_email_list(doc.get("email_cc")),
	)
	frappe.local.sales_ops_settings = s
	return s


def clear_settings_memo():
	frappe.local.sales_ops_settings = None


def stage_info(s, stage):
	return next((x for x in s.stages if x.name == stage), None)


def won_stage(s):
	return next((x for x in s.stages if x.is_closed and x.is_won), None)


def lost_stage(s):
	return next((x for x in s.stages if x.is_closed and not x.is_won), None)


def status_info(s, status):
	return next((x for x in s.lead_statuses if x.name == status), None)


def customer_status(s):
	"""First lead status that means 'buys from us' (Active Customer)."""
	return next((x for x in s.lead_statuses if x.is_active_customer), None)


def lost_status(s):
	"""Lead status for a relationship that has ended (Lost Customer)."""
	return next((x for x in s.lead_statuses if x.is_closed), None)


def needs_followup(s, st):
	return bool(st) and not st.is_closed and st.name != s.first_stage


def default_priority(s):
	p = s.lists.priority
	return p[len(p) // 2] if p else None


def owner_label(s, user):
	o = next((x for x in s.owners if x.user == user), None)
	if o:
		return o.name
	return frappe.db.get_value("User", user, "full_name") or user if user else _("Unassigned")


def manager_users(s=None):
	s = s or get_settings()
	return [o.user for o in s.owners if o.active and o.is_manager]


# ---------- permissions ----------


def is_manager(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	try:
		s = get_settings()
	except Exception:
		return False
	return any(o.user == user and o.is_manager for o in s.owners)


def deal_query_conditions(user=None):
	user = user or frappe.session.user
	if is_manager(user):
		return ""
	# sales people see only the deals they are assigned to: owner or co-owner (not unassigned deals)
	u = frappe.db.escape(user)
	return (
		"(`tab{dt}`.`deal_owner` = {u} or exists (select 1 from `tab{co}` spco"
		" where spco.parent = `tab{dt}`.`name` and spco.parenttype = '{dt}' and spco.user = {u}))"
	).format(dt=DEAL, co=CO_OWNER, u=u)


def co_owner_users(name):
	"""Saved co-owners of a deal (in row order)."""
	if not name:
		return []
	return frappe.get_all(
		CO_OWNER, filters={"parent": name, "parenttype": DEAL}, pluck="user", order_by="idx asc"
	)


def is_co_owner(name, user=None):
	user = user or frappe.session.user
	return bool(name) and bool(frappe.db.exists(CO_OWNER, {"parent": name, "parenttype": DEAL, "user": user}))


def deal_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if is_manager(user):
		return None
	owner = doc.get("deal_owner") or ""
	saved_owner = owner
	saved = doc.get("name") and not doc.get("__islocal")
	if saved:
		saved_owner = frappe.db.get_value(DEAL, doc.get("name"), "deal_owner") or ""
	if ptype == "create":
		return None
	if ptype == "delete":
		return None if saved_owner == user else False
	# only deals the user is assigned to: owner or co-owner (changing the owner list is checked in validate)
	if saved and (saved_owner == user or is_co_owner(doc.get("name"), user)):
		return None
	if not saved and owner == user:
		return None
	return False


def _deal_access_sql(user):
	"""Deals a sales person may see (owner or co-owner), as an SQL condition on alias spd."""
	u = frappe.db.escape(user)
	return (
		"(spd.deal_owner = {u} or exists (select 1 from `tab{co}` spco"
		" where spco.parent = spd.name and spco.parenttype = '{dt}' and spco.user = {u}))"
	).format(co=CO_OWNER, dt=DEAL, u=u)


def account_query_conditions(user=None):
	user = user or frappe.session.user
	if is_manager(user):
		return ""
	# the relationship manager, plus anyone working a deal on the account
	return (
		"(`tab{acc}`.`account_owner` = {u} or exists (select 1 from `tab{dt}` spd"
		" where spd.pipeline_account = `tab{acc}`.`name` and {deals}))"
	).format(acc=ACCOUNT, dt=DEAL, u=frappe.db.escape(user), deals=_deal_access_sql(user))


def works_account(name, user=None):
	"""The user owns a deal (or co-owns one) on this account."""
	user = user or frappe.session.user
	if not name:
		return False
	return bool(frappe.db.sql(
		"select 1 from `tab{dt}` spd where spd.pipeline_account = %s and {deals} limit 1".format(dt=DEAL, deals=_deal_access_sql(user)),
		name,
	))


def account_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if is_manager(user) or ptype == "create":
		return None
	saved = doc.get("name") and not doc.get("__islocal")
	owner = (frappe.db.get_value(ACCOUNT, doc.get("name"), "account_owner") if saved else doc.get("account_owner")) or ""
	if ptype == "delete":
		return None if owner == user else False
	if owner == user or (saved and works_account(doc.get("name"), user)):
		return None
	return False


def settings_has_permission(doc, ptype=None, user=None, debug=False):
	if ptype in ("read", "print", "email", "report", "export"):
		return None
	return None if is_manager(user) else False


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def active_owner_query(doctype, txt, searchfield, start, page_len, filters):
	s = get_settings()
	txt = (txt or "").lower()
	rows = [
		(o.user, o.name)
		for o in s.owners
		if o.active and (not txt or txt in o.user.lower() or txt in o.name.lower())
	]
	start, page_len = cint(start), cint(page_len) or 20
	return rows[start : start + page_len]


# ---------- buyer details from a Customer ----------


def customer_buyer_info(customer):
	"""Name, primary contact (name, phone, email) and primary address of a Customer, for prefilling a deal."""
	if not customer:
		return {}
	c = frappe.db.get_value(
		"Customer", customer,
		["customer_name", "customer_primary_contact", "customer_primary_address", "email_id", "mobile_no"],
		as_dict=True,
	)
	if not c:
		return {}

	def linked(doctype, primary_flag):
		rows = frappe.db.sql(
			"""select d.name from `tab{dt}` d
			join `tabDynamic Link` dl on dl.parent = d.name and dl.parenttype = %(dt)s
				and dl.link_doctype = 'Customer' and dl.link_name = %(c)s
			order by d.{flag} desc, d.modified desc limit 1""".format(dt=doctype, flag=primary_flag),
			{"dt": doctype, "c": customer},
		)
		return rows[0][0] if rows else None

	out = {"account": c.customer_name or customer}
	contact = c.customer_primary_contact or linked("Contact", "is_primary_contact")
	if contact:
		ct = frappe.db.get_value(
			"Contact", contact, ["first_name", "last_name", "full_name", "email_id", "mobile_no", "phone"], as_dict=True
		)
		if ct:
			name = (ct.full_name or " ".join(x for x in (ct.first_name, ct.last_name) if x) or "").strip()
			# ERPNext names a company contact after the customer; that is not a person's name
			if name and name.lower() != (c.customer_name or "").strip().lower():
				out["contact_name"] = name
			out["email"] = ct.email_id or None
			out["phone"] = ct.mobile_no or ct.phone or None
	out["email"] = out.get("email") or c.email_id or None
	out["phone"] = out.get("phone") or c.mobile_no or None
	address = c.customer_primary_address or linked("Address", "is_primary_address")
	if address:
		a = frappe.db.get_value(
			"Address", address, ["address_line1", "address_line2", "city", "state", "pincode"], as_dict=True
		)
		if a:
			line2 = ", ".join(x for x in (a.city, " ".join(y for y in (a.state, a.pincode) if y)) if x)
			out["location_address"] = "\n".join(x for x in (a.address_line1, a.address_line2, line2) if x) or None
	return out


def customer_email(customer):
	"""Customer email for the Email button: the Customer's email, else its primary contact's."""
	return customer_buyer_info(customer).get("email") if customer else None


# ---------- stock and attention flags ----------


def stock_map(s):
	"""{"Cold Cure|T1": {"grams": ..., "label": ...}} — one query for every product line row."""
	groups = sorted({g for r in s.product_lines for g in r.item_groups})
	if not groups:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT i.item_group, b.warehouse, w.company,
			SUM(b.actual_qty) AS actual, SUM(b.reserved_qty) AS on_orders
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE i.item_group IN %(groups)s AND i.stock_uom = 'Gram'
		  AND IFNULL(w.is_rejected_warehouse, 0) = 0
		GROUP BY i.item_group, b.warehouse, w.company
		""",
		{"groups": tuple(groups)},
		as_dict=True,
	)
	out = {}
	for r in s.product_lines:
		if not r.item_groups:
			continue
		actual = on_orders = 0.0
		for x in rows:
			if x.item_group not in r.item_groups:
				continue
			if r.warehouses:
				if x.warehouse not in r.warehouses:
					continue
			elif s.stock_company and x.company != s.stock_company:
				continue
			actual += flt(x.actual)
			on_orders += flt(x.on_orders)
		out[r.product_line + "|" + r.tier] = frappe._dict(
			grams=max(0.0, actual - on_orders),
			on_hand=actual,
			on_orders=on_orders,
			groups=r.item_groups,
			warehouses=r.warehouses or ([s.stock_company] if s.stock_company else []),
		)
	return out


def product_row(s, product_line, tier):
	if not product_line:
		return None
	exact = next((r for r in s.product_lines if r.product_line == product_line and r.tier == (tier or "")), None)
	return exact or next((r for r in s.product_lines if r.product_line == product_line and not r.tier), None)


def stock_for(stock, product_line, tier):
	if not product_line:
		return None
	return stock.get(product_line + "|" + (tier or "")) or stock.get(product_line + "|")


def deal_lines(d):
	"""Requirement lines of a deal row (d.requirements = list of dicts); a deal without lines uses its own fields."""
	rows = [r for r in (d.get("requirements") or []) if r.get("product_line")]
	if rows:
		return [frappe._dict(r) for r in rows]
	if d.get("product_line") or flt(d.get("total_grams")) or flt(d.get("price_per_gram")):
		return [frappe._dict(
			name=None, product_line=d.get("product_line") or "", tier=d.get("tier") or "",
			total_grams=flt(d.get("total_grams")), price_per_gram=flt(d.get("price_per_gram")),
			amount=flt(d.get("total_grams")) * flt(d.get("price_per_gram")), details="",
		)]
	return []


def lines_short(lines, stock):
	"""Grams short across all lines: lines asking for the same stock are added up first."""
	need = {}
	for r in lines:
		stk = stock_for(stock, r.product_line, r.tier)
		if stk and flt(r.total_grams):
			key = id(stk)
			need.setdefault(key, [stk, 0.0])[1] += flt(r.total_grams)
	return sum(max(0.0, g - stk.grams) for stk, g in need.values())


def enrich(d, s, today, stock):
	"""Adds probability, weighted value, stage age, stock and attention flags to a deal row (in place)."""
	st = stage_info(s, d.stage) or frappe._dict(probability=0, max_days=0, is_closed=0, is_won=0)
	d.probability = st.probability
	d.deal_value = flt(d.deal_value)
	d.weighted_value = d.deal_value * flt(st.probability) / 100.0
	d.is_closed = st.is_closed
	d.is_won = st.is_closed and st.is_won
	since = getdate(d.stage_changed_on or d.creation)
	d.days_in_stage = max(0, date_diff(today, since))
	d.is_lost = bool(st.is_closed and not st.is_won)
	# won deals drop off after the hide window; lost deals stay in Active Opportunity so they can be won back
	d.hidden_closed = bool(st.is_closed and st.is_won and s.hide_closed_after_days and d.days_in_stage > s.hide_closed_after_days)
	d.won_this_month = bool(d.is_won and since.year == today.year and since.month == today.month)
	lines = deal_lines(d)
	for r in lines:
		stk = stock_for(stock, r.product_line, r.tier)
		r.amount = flt(r.total_grams) * flt(r.price_per_gram)
		r.stock_grams = stk.grams if stk else None
		r.on_orders = stk.on_orders if stk else None
		r.stock_groups = stk.groups if stk else []
		r.short = max(0.0, flt(r.total_grams) - stk.grams) if (stk and flt(r.total_grams)) else 0.0
	d.lines = lines
	d.stock = stock_for(stock, lines[0].product_line, lines[0].tier) if lines else None
	d.short = lines_short(lines, stock)
	for f in ("next_step_due", "sample_date", "expected_close", "delivery_pickup"):
		d[f] = str(d[f]) if d.get(f) else None
	d.flags = deal_flags(d, s, st, today)
	d.attention = any(f["kind"] == "action" for f in d.flags)
	return d


def deal_flags(d, s, st, today):
	flags = []
	if st.is_closed:
		return flags
	a = s.alerts

	def add(key, label, kind):
		flags.append({"key": key, "label": label, "kind": kind})

	follow = getdate(d.next_step_due) if d.get("next_step_due") else None
	if follow and follow < today and a.followup_overdue:
		add("overdue", _("Overdue follow-up · {0}").format(formatdate(follow)), "action")
	elif follow and follow == today and a.followup_today:
		add("followup_today", _("Follow-up today"), "info")
	if a.stalled and st.max_days and cint(d.get("days_in_stage")) > st.max_days:
		add("stalled", _("Stalled · {0} days").format(cint(d.days_in_stage)), "action")
	if a.missing_owner and not d.get("deal_owner"):
		add("no_owner", _("No owner"), "action")
	if a.missing_value and not flt(d.get("deal_value")) and d.stage != s.first_stage:
		add("no_value", _("No value"), "action")
	if a.short_stock and flt(d.get("short")) > 0:
		add("short", _("Short {0} g").format(frappe.utils.fmt_money(d.short, precision=0)), "action")
	sample = getdate(d.sample_date) if d.get("sample_date") else None
	if (
		a.sample_due
		and sample
		and date_diff(sample, today) <= cint(s.sample_due_days)
		and (d.get("samples") or "") not in s.lists.samples_done
	):
		add("sample_due", _("Sample due · {0}").format(formatdate(sample)), "action")
	return flags


# ---------- accounts (Leads board): lead status, volume and demand ----------


def line_unit(s, product_line):
	"""lb, g or kg: the unit the team counts this product line in (Settings, filled from its items' stock unit)."""
	return (s.line_units or {}).get(product_line) or "g"


def line_units_allowed(s, product_line):
	"""Fresh frozen is always counted in lb; extracts in g or kg."""
	return ["lb"] if line_unit(s, product_line) == "lb" else ["g", "kg"]


def price_unit(s, product_line):
	"""Prices are per lb for lb lines and per gram for everything else."""
	return "lb" if line_unit(s, product_line) == "lb" else "g"


def volume_row(r):
	"""Grams per week they move, grams per month they want from us, and that month's value (in place).
	The price is per price_unit (lb or g)."""
	per = UNIT_GRAMS.get(r.get("uom") or "g", 1.0)
	r.weekly_grams = flt(r.get("weekly_volume")) * per
	wants = flt(r.get("wants_qty")) * per
	r.monthly_grams = wants * WEEKS_PER_MONTH if (r.get("wants_per") or "Month") == "Week" else wants
	pu = UNIT_GRAMS.get(r.get("price_unit") or "g", 1.0)
	r.price_per_gram = flt(r.get("price")) / pu
	r.monthly_value = flt(r.monthly_grams) / pu * flt(r.get("price"))
	return r


def default_price(s, product_line, tier):
	"""Settings default price, in the line's price unit (per lb or per gram)."""
	row = product_row(s, product_line, tier)
	return flt(row.default_price) if row else 0.0


def deal_stats(deals):
	"""{account: {open_deals, open_value, open_weighted, won_value, lost_deals}} from enriched deal rows."""
	out = {}
	for d in deals:
		acc = d.get("pipeline_account")
		if not acc:
			continue
		x = out.setdefault(acc, frappe._dict(open_deals=0, open_value=0.0, open_weighted=0.0, won_value=0.0, won_deals=0, lost_deals=0, deals=[]))
		x.deals.append(d.name)
		if not d.get("is_closed"):
			x.open_deals += 1
			x.open_value += flt(d.get("deal_value"))
			x.open_weighted += flt(d.get("weighted_value"))
		elif d.get("is_won"):
			x.won_deals += 1
			x.won_value += flt(d.get("deal_value"))
		else:
			x.lost_deals += 1
	return out


def enrich_account(a, s, today, stats):
	"""Adds status probability, weighted potential, days in status, deal totals and attention flags (in place)."""
	st = status_info(s, a.lead_status) or frappe._dict(probability=0, max_days=0, is_closed=0, is_active_customer=0)
	a.account = a.account_name
	a.probability = st.probability
	a.is_closed = st.is_closed
	a.is_customer = st.is_active_customer
	a.weekly_volume = flt(a.weekly_volume)
	a.monthly_demand = flt(a.monthly_demand)
	a.monthly_potential = flt(a.monthly_potential)
	a.weighted_potential = a.monthly_potential * flt(st.probability) / 100.0
	since = getdate(a.status_changed_on or a.creation)
	a.days_in_stage = max(0, date_diff(today, since))
	a.next_step_due = str(a.next_step_due) if a.get("next_step_due") else None
	a.update(stats.get(a.name) or frappe._dict(open_deals=0, open_value=0.0, open_weighted=0.0, won_value=0.0, won_deals=0, lost_deals=0, deals=[]))
	flags = []
	if not st.is_closed:
		follow = getdate(a.next_step_due) if a.next_step_due else None
		if follow and follow < today and s.alerts.followup_overdue:
			flags.append({"key": "overdue", "label": _("Overdue follow-up · {0}").format(formatdate(follow)), "kind": "action"})
		elif follow and follow == today and s.alerts.followup_today:
			flags.append({"key": "followup_today", "label": _("Follow-up today"), "kind": "info"})
		if s.alerts.stalled and st.max_days and a.days_in_stage > st.max_days:
			flags.append({"key": "stalled", "label": _("{0} for {1} days").format(a.lead_status, a.days_in_stage), "kind": "action"})
		if s.alerts.missing_owner and not a.get("account_owner"):
			flags.append({"key": "no_owner", "label": _("No owner"), "kind": "action"})
	a.flags = flags
	a.attention = any(f["kind"] == "action" for f in flags)
	return a


def find_account(customer=None, lead=None, name=None):
	"""An existing account for this buyer: by Customer, then Lead, then the same account name."""
	if customer:
		hit = frappe.db.get_value(ACCOUNT, {"customer": customer}, "name", order_by="creation asc")
		if hit:
			return hit
	if lead:
		hit = frappe.db.get_value(ACCOUNT, {"lead": lead}, "name", order_by="creation asc")
		if hit:
			return hit
	if customer and not lead:
		# the Customer was made from a Lead that already has an account
		from_lead = frappe.db.get_value("Customer", customer, "lead_name")
		if from_lead:
			hit = frappe.db.get_value(ACCOUNT, {"lead": from_lead}, "name", order_by="creation asc")
			if hit:
				return hit
	name = (name or "").strip()
	if name:
		rows = frappe.db.sql(
			"select name from `tab{0}` where lower(trim(account_name)) = lower(%s) order by creation limit 1".format(ACCOUNT), name
		)
		if rows:
			return rows[0][0]
	return None


def make_account(values, status=None):
	"""New account from a deal (or the migration). values: account_name, owner, customer, lead, contact fields."""
	s = get_settings()
	doc = frappe.new_doc(ACCOUNT)
	doc.account_name = (values.get("account_name") or "").strip() or values.get("customer") or _("New account")
	doc.lead_status = status or s.first_status
	doc.account_owner = values.get("account_owner")
	for f in ("customer", "lead", "contact_name", "phone", "email", "location_address", "license_number", "lead_source", "next_step_due"):
		if values.get(f):
			doc.set(f, values[f])
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc


# ---------- notifications ----------


def deal_link(name):
	return get_url("/app/{0}?deal={1}".format(BOARD_ROUTE, name))


def notify(users, subject, deal=None, html=None):
	"""In-app alert (bell). Sent after commit, never to the person who made the change."""
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	users = [u for u in dict.fromkeys(users or []) if u and u != frappe.session.user]
	if not users:
		return
	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"subject": subject,
			"document_type": DEAL if deal else None,
			"document_name": deal,
			"from_user": frappe.session.user,
			"email_content": html or subject,
		},
	)


def _email_list(text):
	"""Valid addresses from a comma / semicolon / newline separated field, in order, no repeats."""
	from frappe.utils import validate_email_address

	out = []
	for part in (text or "").replace(";", ",").replace("\n", ",").split(","):
		addr = validate_email_address(part.strip()) if part.strip() else ""
		if addr and addr.lower() not in [x.lower() for x in out]:
			out.append(addr)
	return out


def no_email_users(s=None):
	"""Owners ticked "No Email" in Settings: no pipeline email to them, not even as CC."""
	s = s or get_settings()
	return {o.user.lower() for o in s.owners if o.get("no_email") and o.user}


def email_cc_for(recipient, s=None):
	"""Settings CC list for a pipeline email to `recipient` (never the recipient or a No Email owner)."""
	s = s or get_settings()
	skip = no_email_users(s) | {(recipient or "").lower()}
	return [c for c in s.get("email_cc") or [] if c.lower() not in skip]


def send_daily_digest():
	"""Scheduler, daily 8:00 AM site time: each owner gets their follow-ups, stalled deals and samples due;
	pipeline managers also get deals that have been unassigned too long."""
	if not frappe.db.exists("DocType", SETTINGS):
		return
	clear_settings_memo()
	s = get_settings()
	if not s.stages:
		return
	today = getdate(nowdate())
	rows = frappe.get_all(
		DEAL,
		fields=[
			"name", "account", "stage", "deal_owner", "next_step_due", "sample_date", "samples",
			"stage_changed_on", "creation", "deal_value", "product_line", "tier", "total_grams",
			"expected_close", "delivery_pickup",
		],
	)
	co_map = {}
	for r in frappe.get_all(CO_OWNER, filters={"parenttype": DEAL}, fields=["parent", "user"], order_by="idx asc"):
		co_map.setdefault(r.parent, []).append(r.user)
	by_owner = {}
	shared = {}
	new_bucket = lambda: {"overdue": [], "followup_today": [], "stalled": [], "sample_due": []}  # noqa: E731
	for d in rows:
		enrich(d, s, today, {})
		if d.is_closed:
			continue
		# co-owners get every open shared deal under "Shared with you"
		for u in co_map.get(d.name, []):
			if u and u != d.deal_owner:
				shared.setdefault(u, []).append(d)
		if not d.deal_owner:
			continue
		keys = {f["key"] for f in d.flags}
		bucket = by_owner.setdefault(d.deal_owner, new_bucket())
		for k in bucket:
			if k in keys:
				bucket[k].append(d)

	sections = [
		("overdue", _("Overdue follow-ups"), "next_step_due"),
		("followup_today", _("Follow-ups today"), "next_step_due"),
		("stalled", _("Stalled deals"), None),
		("sample_due", _("Samples due"), "sample_date"),
	]
	if s.send_daily_digest:
		for user in list(dict.fromkeys(list(by_owner) + list(shared))):
			bucket = by_owner.get(user) or new_bucket()
			mine = shared.get(user) or []
			total = sum(len(v) for v in bucket.values()) + len(mine)
			if not total:
				continue
			html = [
				"<p>{0}</p>".format(_("Your Sales Operation Board for {0}:").format(formatdate(today))),
			]
			for key, title, date_field in sections:
				if not bucket[key]:
					continue
				html.append("<h4 style='margin:14px 0 6px'>{0} ({1})</h4><ul>".format(title, len(bucket[key])))
				for d in bucket[key]:
					extra = formatdate(d[date_field]) if date_field and d.get(date_field) else _("{0} days in {1}").format(d.days_in_stage, d.stage)
					html.append(
						"<li><a href='{0}'>{1}</a> · {2} · {3}</li>".format(
							deal_link(d.name), frappe.utils.escape_html(d.account), frappe.utils.escape_html(d.stage), extra
						)
					)
				html.append("</ul>")
			if mine:
				html.append("<h4 style='margin:14px 0 6px'>{0} ({1})</h4><ul>".format(_("Shared with you"), len(mine)))
				for d in mine:
					status = ", ".join(f["label"] for f in d.flags) or (
						_("Next follow-up {0}").format(formatdate(d.next_step_due)) if d.get("next_step_due") else _("No follow-up date")
					)
					html.append(
						"<li><a href='{0}'>{1}</a> · {2} · {3} {4} · {5}</li>".format(
							deal_link(d.name), frappe.utils.escape_html(d.account), frappe.utils.escape_html(d.stage),
							_("Owner:"), frappe.utils.escape_html(owner_label(s, d.deal_owner) if d.deal_owner else _("Unassigned")),
							frappe.utils.escape_html(status),
						)
					)
				html.append("</ul>")
			html.append("<p><a href='{0}'>{1}</a></p>".format(get_url("/app/" + BOARD_ROUTE), _("Open the Sales Operation Board")))
			attention = total - len(mine)
			if attention:
				subject = _("Sales pipeline: {0} item(s) need your attention today").format(attention)
			else:
				subject = _("Sales pipeline: your {0} shared deal(s) today").format(len(mine))
			body = "".join(html)
			notify([user], subject, html=body)
			if user.lower() in no_email_users(s) or not _email_list(user):
				continue  # bell alert only (No Email owners; "Administrator" has no address — it errored daily)
			try:
				frappe.sendmail(recipients=[user], cc=email_cc_for(user, s), subject=subject, message=body, delayed=True)
			except Exception:
				frappe.log_error(title="Sales Operation Board digest email failed")

	days = cint(s.unassigned_alert_days)
	if days > 0:
		cutoff = get_datetime(add_days(today, -days))
		stale = [d for d in rows if not d.deal_owner and not d.is_closed and get_datetime(d.creation) < cutoff]
		if stale:
			items = "".join(
				"<li><a href='{0}'>{1}</a> · {2}</li>".format(deal_link(d.name), frappe.utils.escape_html(d.account), frappe.utils.escape_html(d.stage))
				for d in stale
			)
			notify(
				manager_users(s),
				_("{0} deal(s) have been unassigned for more than {1} days").format(len(stale), days),
				html="<ul>{0}</ul>".format(items),
			)
	frappe.db.commit()


# ---------- settings side effects ----------


def _set_options(doctype, field, options):
	"""Property setter for a Select field's options; True when it changed."""
	if not frappe.db.exists("DocType", doctype):
		return False
	df = frappe.get_meta(doctype).get_field(field)
	if not df or df.fieldtype != "Select" or (df.options or "") == options:
		return False
	frappe.make_property_setter(
		{"doctype": doctype, "fieldname": field, "property": "options", "value": options, "property_type": "Text"},
		validate_fields_for_doctype=False,
	)
	frappe.clear_cache(doctype=doctype)
	return True


def sync_account_options(s):
	"""Lead statuses, lead sources and product lines into the account and volume Select fields."""
	_set_options(ACCOUNT, "lead_status", "\n".join(x.name for x in s.lead_statuses))
	_set_options(ACCOUNT, "lead_source", "\n" + "\n".join(s.lists.lead_source))
	_set_options(VOLUME, "product_line", "\n".join(s.product_line_names))
	_set_options(VOLUME, "tier", "\n" + "\n".join(s.lists.tier))
	if s.first_status and frappe.db.exists("DocType", ACCOUNT):
		df = frappe.get_meta(ACCOUNT).get_field("lead_status")
		if df and df.default != s.first_status:
			frappe.make_property_setter(
				{"doctype": ACCOUNT, "fieldname": "lead_status", "property": "default", "value": s.first_status, "property_type": "Text"},
				validate_fields_for_doctype=False,
			)
			frappe.clear_cache(doctype=ACCOUNT)


def sync_deal_options(s):
	"""Push Settings lists into the deal's Select options (stage, product line and the fixed lists)."""
	sync_account_options(s)
	meta = frappe.get_meta(DEAL)
	wanted = {
		"stage": "\n".join(x.name for x in s.stages),
		"product_line": "\n" + "\n".join(s.product_line_names),
	}
	for field, key in SELECT_SOURCES.items():
		values = s.lists.get(key) or []
		wanted[field] = ("" if field == "priority" else "\n") + "\n".join(values)
	changed = False
	for field, options in wanted.items():
		df = meta.get_field(field)
		if not df or df.fieldtype != "Select" or (df.options or "") == options:
			continue
		frappe.make_property_setter(
			{"doctype": DEAL, "fieldname": field, "property": "options", "value": options, "property_type": "Text"},
			validate_fields_for_doctype=False,
		)
		changed = True
	defaults = {"stage": s.first_stage, "priority": default_priority(s)}
	for field, value in defaults.items():
		df = meta.get_field(field)
		if df and value and df.default != value:
			frappe.make_property_setter(
				{"doctype": DEAL, "fieldname": field, "property": "default", "value": value, "property_type": "Text"},
				validate_fields_for_doctype=False,
			)
			changed = True
	if frappe.db.exists("DocType", REQUIREMENT):
		rmeta = frappe.get_meta(REQUIREMENT)
		for field, options in (("product_line", "\n".join(s.product_line_names)), ("tier", "\n" + "\n".join(s.lists.tier))):
			df = rmeta.get_field(field)
			if df and df.fieldtype == "Select" and (df.options or "") != options:
				frappe.make_property_setter(
					{"doctype": REQUIREMENT, "fieldname": field, "property": "options", "value": options, "property_type": "Text"},
					validate_fields_for_doctype=False,
				)
				frappe.clear_cache(doctype=REQUIREMENT)
	if changed:
		frappe.clear_cache(doctype=DEAL)


def recompute_probabilities(s):
	"""Stage probability lives in Settings; keep stored probability / weighted value in step on every deal."""
	for st in s.stages:
		frappe.db.sql(
			"""UPDATE `tab{dt}` SET probability = %(p)s, weighted_value = deal_value * %(p)s / 100
			WHERE stage = %(stage)s AND (probability != %(p)s OR weighted_value != deal_value * %(p)s / 100)""".format(dt=DEAL),
			{"p": st.probability, "stage": st.name},
		)


def publish_board_update(name=None):
	frappe.publish_realtime("sales_pipeline_update", {"name": name}, after_commit=True)
