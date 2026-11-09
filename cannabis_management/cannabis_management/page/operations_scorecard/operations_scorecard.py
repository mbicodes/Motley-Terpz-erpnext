import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, flt, get_first_day, get_last_day, getdate, nowdate

PAGE_ROLE = "Operations Scorecard"
G_PER_LB = 453.59237
MTM_COMPANY = "Master Touch Manufacturing"
TREND_PERIODS = 6
MAX_RANGE_DAYS = 400
VIEWS = ("week_month", "weeks", "months", "custom")

TIERS = (
	("T1+", ("Tier 1 Plus",)),
	("T1", ("Tier 1", "Primes")),
	("T2", ("Tier 2", "Subprimes")),
	("T3", ("Tier 3",)),
	("T4", ("Tier 4",)),
	("Food grade", ("Food Grade",)),
	("VRR", ("VRR",)),
	("Other rosin", ("Raw Rosin", "Full Spec")),
)
TIER_NAMES = tuple(tier for tier, _groups in TIERS)
GROUP_LABELS = {
	"Primes": "Primes (old T1 grade)",
	"Subprimes": "Subprimes (old T2 grade)",
	"Raw Rosin": "Raw rosin (not graded yet)",
}
GROUP_TIER = {group: tier for tier, groups in TIERS for group in groups}
LIVE_RESIN_GROUPS = ("Liquid Live Resin", "BHO", "Diamonds")
WASH_LOCATIONS = ("MTM", "Nature", "Other partners")
LIVE_RESIN = "Live resin"
GRAM_UOMS = ("Gram",)


def _require_access():
	if PAGE_ROLE not in frappe.get_roles():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _period(key, band, start, end, today):
	start, end = getdate(start), getdate(end)
	return frappe._dict(
		key=key, band=band, start=start, end=end,
		snapshot=min(end, today), partial=start <= today < end, future=start > today,
	)


def _periods(view, as_of, from_date=None, to_date=None):
	today = getdate(nowdate())
	d = getdate(as_of)
	week = getdate(add_days(d, -d.weekday()))
	month = getdate(get_first_day(d))

	if view == "weeks":
		return [
			_period(f"w{i}", "week", add_days(week, -7 * back), add_days(week, -7 * back + 6), today)
			for i, back in enumerate(range(TREND_PERIODS - 1, -1, -1))
		]
	if view == "months":
		out = []
		for i, back in enumerate(range(TREND_PERIODS - 1, -1, -1)):
			start = getdate(add_months(month, -back))
			out.append(_period(f"m{i}", "month", start, get_last_day(start), today))
		return out
	if view == "custom":
		if not (from_date and to_date):
			frappe.throw(_("Pick a From date and a To date for the custom range."))
		start, end = sorted((getdate(from_date), getdate(to_date)))
		days = date_diff(end, start) + 1
		if days > MAX_RANGE_DAYS:
			frappe.throw(_("Keep the custom range to {0} days or less.").format(MAX_RANGE_DAYS))
		return [
			_period("range", "range", start, end, today),
			_period("prev_range", "range", add_days(start, -days), add_days(start, -1), today),
		]
	return [
		_period("week", "week", week, add_days(week, 6), today),
		_period("prev_week", "week", add_days(week, -7), add_days(week, -1), today),
		_period("month", "month", month, get_last_day(d), today),
		_period("prev_month", "month", get_first_day(add_months(d, -1)), add_days(month, -1), today),
	]


def _kpi_pair(view, periods):
	if view in ("weeks", "months"):
		return periods[-1].key, periods[-2].key
	return periods[0].key, periods[1].key


def _context(as_of=None, company=None, view=None, from_date=None, to_date=None,
             location=None, tier=None, customer=None):
	_require_access()
	ctx = frappe._dict(
		view=view if view in VIEWS else "week_month",
		as_of=getdate(as_of or nowdate()),
		company=company or None,
		location=location or None,
		tier=tier or None,
		customer=customer or None,
	)
	if ctx.company and not frappe.db.exists("Company", ctx.company):
		frappe.throw(_("Unknown company {0}").format(ctx.company))
	if ctx.customer and not frappe.db.exists("Customer", ctx.customer):
		frappe.throw(_("Unknown customer {0}").format(ctx.customer))
	if ctx.location and ctx.location not in WASH_LOCATIONS:
		frappe.throw(_("Unknown wash location {0}").format(ctx.location))
	if ctx.tier and ctx.tier not in TIER_NAMES:
		frappe.throw(_("Unknown tier {0}").format(ctx.tier))
	ctx.periods = _periods(ctx.view, ctx.as_of, from_date, to_date)
	return ctx


def _fresh_frozen_groups():
	root = frappe.db.get_value("Item Group", "Fresh Frozen Main", ["lft", "rgt"], as_dict=True)
	if root:
		return tuple(frappe.get_all(
			"Item Group", filters={"lft": [">=", root.lft], "rgt": ["<=", root.rgt]}, pluck="name",
		))
	return tuple(frappe.get_all("Item Group", filters={"name": ["like", "Fresh Frozen%"]}, pluck="name"))


def _internal_customers():
	names = set(frappe.get_all("Company", pluck="name"))
	names |= set(frappe.db.sql_list(
		"""select name from `tabCustomer`
		   where is_internal_customer = 1 or ifnull(represents_company, '') != ''"""
	))
	names |= {"MT", "MTPZ", "MTM"}
	return tuple(sorted(names))


def _company_cond(company, alias):
	return f" and {alias}.company = %(company)s" if company else ""


def _tier_groups(tier):
	return tuple(g for t, groups in TIERS if not tier or t == tier for g in groups)


def _inventory_items(periods, company, tier=None):
	items = {}
	balances = {}
	groups = _tier_groups(tier)
	for p in periods:
		if p.future:
			continue
		if p.snapshot not in balances:
			balances[p.snapshot] = frappe.db.sql(
				f"""
				select item_code, item_name, item_group, sum(qty) as qty
				from (
					select sle.item_code, i.item_name, i.item_group, sle.qty_after_transaction as qty,
					       row_number() over (
					           partition by sle.item_code, sle.warehouse
					           order by sle.posting_datetime desc, sle.creation desc
					       ) as rn
					from `tabStock Ledger Entry` sle
					join `tabItem` i on i.name = sle.item_code
					where sle.is_cancelled = 0 and sle.posting_date <= %(date)s
					  and i.item_group in %(groups)s and i.stock_uom in %(uoms)s
					  {_company_cond(company, "sle")}
				) latest
				where rn = 1
				group by item_code, item_name, item_group
				""",
				{"date": p.snapshot, "groups": groups, "uoms": GRAM_UOMS, "company": company},
				as_dict=True,
			)
		for r in balances[p.snapshot]:
			item = items.setdefault(r.item_code, frappe._dict(
				item_code=r.item_code, item_name=r.item_name, item_group=r.item_group, qty={},
			))
			item.qty[p.key] = flt(r.qty)
	for item in items.values():
		for p in periods:
			item.qty.setdefault(p.key, 0.0)
	return list(items.values())


def _process_entries(start, end, company, location=None):
	ff = _fresh_frozen_groups()
	if not ff:
		return []
	rows = frappe.db.sql(
		f"""
		select se.name, se.posting_date, se.company, se.purpose,
		       sed.item_code, sed.item_name, i.item_group, i.stock_uom,
		       ifnull(sed.s_warehouse, '') as s_wh, ifnull(sed.t_warehouse, '') as t_wh,
		       sed.transfer_qty as qty
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name
		join `tabItem` i on i.name = sed.item_code
		where se.docstatus = 1 and se.purpose in ('Manufacture', 'Repack')
		  and se.posting_date between %(start)s and %(end)s
		  {_company_cond(company, "se")}
		  and exists (
			select 1 from `tabStock Entry Detail` d join `tabItem` fi on fi.name = d.item_code
			where d.parent = se.name and ifnull(d.s_warehouse, '') != '' and fi.item_group in %(ff)s
		  )
		order by se.posting_date, se.name, sed.idx
		""",
		{"start": start, "end": end, "company": company, "ff": ff},
		as_dict=True,
	)
	ff = set(ff)
	entries = {}
	for r in rows:
		e = entries.setdefault(r.name, frappe._dict(
			name=r.name, posting_date=r.posting_date, company=r.company,
			ff_in={}, ff_out=0.0, inputs={}, outputs={}, out_items={}, wh_lbs={},
		))
		consumed = r.s_wh and not r.t_wh
		produced = r.t_wh and not r.s_wh
		label = r.item_name or r.item_code
		if r.item_group in ff:
			if consumed:
				e.ff_in[r.item_group] = e.ff_in.get(r.item_group, 0) + flt(r.qty)
				e.wh_lbs[r.s_wh] = e.wh_lbs.get(r.s_wh, 0) + flt(r.qty)
				e.inputs[label] = e.inputs.get(label, 0) + flt(r.qty)
			elif produced:
				e.ff_out += flt(r.qty)
		elif produced and r.stock_uom in GRAM_UOMS:
			e.outputs[r.item_group] = e.outputs.get(r.item_group, 0) + flt(r.qty)
			e.out_items[label] = e.out_items.get(label, 0) + flt(r.qty)

	out = []
	for e in entries.values():
		lbs_in = sum(e.ff_in.values())
		lbs = lbs_in - e.ff_out
		grams = sum(e.outputs.values())
		if lbs <= 0 or grams <= 0:
			continue
		scale = lbs / lbs_in
		e.ff_types = {g: q * scale for g, q in e.ff_in.items()}
		e.lbs = lbs
		e.grams = grams
		e.warehouse = max(e.wh_lbs, key=e.wh_lbs.get)
		resin = sum(q for g, q in e.outputs.items() if g in LIVE_RESIN_GROUPS)
		if resin * 2 > grams:
			e.location = LIVE_RESIN
		elif "natur" in e.warehouse.lower():
			e.location = "Nature"
		elif e.company == MTM_COMPANY:
			e.location = "MTM"
		else:
			e.location = "Other partners"
		if location and e.location not in (location, LIVE_RESIN):
			continue
		out.append(e)
	return out


def _sales_lines(start, end, company, tier=None, customer=None):
	groups = _tier_groups(tier) + (() if tier else LIVE_RESIN_GROUPS)
	customer_cond = " and si.customer = %(customer)s" if customer else ""
	return frappe.db.sql(
		f"""
		select si.name as invoice, si.posting_date, si.customer, si.company,
		       sii.item_code, sii.item_name, i.item_group,
		       sii.stock_qty as qty, sii.base_net_amount as amount
		from `tabSales Invoice Item` sii
		join `tabSales Invoice` si on si.name = sii.parent
		join `tabItem` i on i.name = sii.item_code
		where si.docstatus = 1 and si.posting_date between %(start)s and %(end)s
		  and i.item_group in %(groups)s and i.stock_uom in %(uoms)s
		  and si.customer not in %(internal)s
		  {_company_cond(company, "si")}{customer_cond}
		order by si.posting_date, si.name, sii.idx
		""",
		{
			"start": start, "end": end, "company": company, "customer": customer,
			"uoms": GRAM_UOMS, "groups": groups, "internal": _internal_customers(),
		},
		as_dict=True,
	)


def _in(period, d):
	return period.start <= getdate(d) <= period.end


def _sum(periods, records, value, keep=lambda r: True):
	return {p.key: sum(value(r) for r in records if _in(p, r.posting_date) and keep(r)) for p in periods}


def _ratio(periods, num, den, factor=1):
	return {p.key: (num[p.key] / den[p.key] * factor) if den[p.key] else None for p in periods}


def _has_value(values):
	return any(abs(flt(v)) >= 0.005 for v in values.values() if v is not None)


def _row(rid, label, unit, values, **kw):
	return {"id": rid, "label": label, "unit": unit, "values": values, **kw}


def _by(records, periods, field, keep=lambda r: True):
	groups = {}
	for r in records:
		if keep(r):
			for k, v in r[field].items():
				groups.setdefault(k, []).append((r, v))
	out = []
	for k, pairs in sorted(groups.items()):
		values = {p.key: sum(v for r, v in pairs if _in(p, r.posting_date)) for p in periods}
		if _has_value(values):
			out.append((k, values))
	return out


def _ff_label(group):
	label = group.replace("Fresh Frozen", "").strip(" -")
	return label[:1].upper() + label[1:].lower() if label and not label.isupper() else (label or group)


def _location_hint(loc):
	return {
		"MTM": _("Washed in-house at Master Touch Manufacturing (freezers and work orders)"),
		"Nature": _("Tolled at Nature's Lab"),
		"Other partners": _("Washed by other tolling partners, e.g. Bloom"),
	}.get(loc, "")


def _inventory_section(ctx, items):
	periods = ctx.periods
	existing = set(frappe.get_all("Item Group", filters={"name": ["in", list(GROUP_TIER)]}, pluck="name"))
	rows = []
	totals = {p.key: 0.0 for p in periods}
	for tier, groups in TIERS:
		if ctx.tier and tier != ctx.tier:
			continue
		children = []
		tier_values = {p.key: 0.0 for p in periods}
		for group in groups:
			values = {p.key: sum(r.qty[p.key] for r in items if r.item_group == group) for p in periods}
			for k, v in values.items():
				tier_values[k] += v
			if _has_value(values):
				children.append(_row(f"inv:{group}", GROUP_LABELS.get(group, group), "g", values,
				                     drill={"metric": "inventory", "group": group}))
		for k, v in tier_values.items():
			totals[k] += v
		hint = ""
		if not existing.intersection(groups):
			hint = _("No item group named {0} exists yet. This row fills in once one is created.").format(
				" / ".join(groups))
		elif len(groups) > 1:
			hint = _("Includes {0}").format(", ".join(GROUP_LABELS.get(g, g) for g in groups))
		rows.append(_row(f"inv:{tier}", tier, "g", tier_values, hint=hint,
		                 children=children if len(children) > 1 else [],
		                 drill={"metric": "inventory", "tier": tier}))
	if ctx.tier:
		rows[0].update(id="inv:total", total=1)
	else:
		rows.insert(0, _row("inv:total", _("Total"), "g", totals, total=1, drill={"metric": "inventory"}))
	return {
		"key": "inventory",
		"title": _("Rosin inventory by tier"),
		"note": _("Grams on hand at the end of each period, today for a period still running"),
		"rows": rows,
	}


def _wash_block(ctx, wash, head_id, head_label, unit, value, field, scale=1):
	periods = ctx.periods
	locations = [ctx.location] if ctx.location else [
		loc for loc in WASH_LOCATIONS
		if loc != "Other partners" or _has_value(_sum(periods, wash, lambda e: e.lbs, lambda e, l=loc: e.location == l))
	]
	drill_key = "ff_group" if field == "ff_types" else "product"

	def breakdown(loc):
		keep = lambda e, l=loc: e.location == l  # noqa: E731
		return [
			_row(f"{head_id}:{loc}:{g}", _ff_label(g) if field == "ff_types" else g, unit,
			     {k: x * scale for k, x in v.items()}, level=2,
			     drill={"metric": "process", "process": "wash", "location": loc, drill_key: g})
			for g, v in _by(wash, periods, field, keep)
		]

	rows = [{"id": f"{head_id}:head", "label": head_label, "unit": unit, "sub": 1}]
	if ctx.location:
		rows.append(_row(f"{head_id}:total", ctx.location, unit, _sum(periods, wash, value), total=1, level=1,
		                 children=breakdown(ctx.location), hint=_location_hint(ctx.location),
		                 drill={"metric": "process", "process": "wash", "location": ctx.location}))
		return rows
	rows.append(_row(f"{head_id}:total", _("Total"), unit, _sum(periods, wash, value), total=1, level=1,
	                 drill={"metric": "process", "process": "wash"}))
	for loc in locations:
		rows.append(_row(f"{head_id}:{loc}", loc, unit,
		                 _sum(periods, wash, value, lambda e, l=loc: e.location == l), level=1,
		                 children=breakdown(loc), hint=_location_hint(loc),
		                 drill={"metric": "process", "process": "wash", "location": loc}))
	return rows


def _production_section(ctx, entries):
	periods = ctx.periods
	wash = [e for e in entries if e.location != LIVE_RESIN]
	resin = [e for e in entries if e.location == LIVE_RESIN]
	rows = _wash_block(ctx, wash, "wash:lbs", _("Pounds washed"), "lbs", lambda e: e.lbs, "ff_types")
	rows += _wash_block(ctx, wash, "wash:kg", _("Kilos produced"), "kg", lambda e: e.grams / 1000, "outputs",
	                    scale=1 / 1000)

	if not ctx.location:
		resin_lbs = _sum(periods, resin, lambda e: e.lbs)
		resin_g = _sum(periods, resin, lambda e: e.grams)
		drill = {"metric": "process", "process": "resin"}
		rows += [
			{"id": "resin:head", "label": _("Live resin extraction (BHO, not a wash)"), "unit": "", "sub": 1},
			_row("resin:lbs", _("Pounds extracted"), "lbs", resin_lbs, level=1, drill=drill,
			     hint=_("Fresh frozen sent to hydrocarbon extraction (Leaf, Buddies Brand). Kept out of the wash totals.")),
			_row("resin:kg", _("Kilos produced"), "kg", {k: v / 1000 for k, v in resin_g.items()}, level=1, drill=drill),
			_row("resin:yield", _("Yield"), "%",
			     _ratio(periods, resin_g, {k: v * G_PER_LB for k, v in resin_lbs.items()}, 100), level=1, drill=drill),
		]
	return {
		"key": "production",
		"title": _("Washing and production"),
		"note": _("Fresh frozen used by wash runs, and what came out of them"),
		"rows": rows,
	}


def _sales_section(ctx, lines):
	periods = ctx.periods
	rosin = lambda r: r.item_group in GROUP_TIER  # noqa: E731
	grams = lambda r: flt(r.qty)  # noqa: E731
	amount = lambda r: flt(r.amount)  # noqa: E731
	price_children, volume_children, revenue_children = [], [], []
	if not ctx.tier:
		for tier, groups in TIERS:
			keep = lambda r, gs=groups: r.item_group in gs  # noqa: E731
			g = _sum(periods, lines, grams, keep)
			amt = _sum(periods, lines, amount, keep)
			if not (_has_value(g) or _has_value(amt)):
				continue
			drill = {"metric": "sales", "tier": tier}
			price_children.append(_row(f"sales:price:{tier}", tier, "$/g", _ratio(periods, amt, g), level=1, drill=drill))
			volume_children.append(_row(f"sales:g:{tier}", tier, "g", g, level=1, drill=drill))
			revenue_children.append(_row(f"sales:amt:{tier}", tier, "$", amt, level=1, drill=drill))
		resin_keep = lambda r: r.item_group in LIVE_RESIN_GROUPS  # noqa: E731
		resin_g = _sum(periods, lines, grams, resin_keep)
		resin_amt = _sum(periods, lines, amount, resin_keep)
		if _has_value(resin_g) or _has_value(resin_amt):
			price_children.append(_row("sales:price:resin", LIVE_RESIN, "$/g", _ratio(periods, resin_amt, resin_g),
			                           level=1, drill={"metric": "sales", "kind": "resin"}))

	price_label = _("Avg sales price – {0}").format(ctx.tier) if ctx.tier else _("Avg sales price – oil")
	rows = [
		_row("sales:price", price_label, "$/g",
		     _ratio(periods, _sum(periods, lines, amount), _sum(periods, lines, grams)),
		     children=price_children, drill={"metric": "sales"},
		     hint=_("Revenue ÷ grams sold. Oil means rosin of every tier plus live resin.")),
		_row("sales:g", _("Rosin volume sold"), "g", _sum(periods, lines, grams, rosin),
		     children=volume_children, drill={"metric": "sales", "kind": "rosin"}),
		_row("sales:amt", _("Rosin revenue"), "$", _sum(periods, lines, amount, rosin),
		     children=revenue_children, drill={"metric": "sales", "kind": "rosin"}),
	]
	note = _("Submitted invoices to outside customers, net of returns")
	if ctx.customer:
		note = _("Invoices to {0}, net of returns").format(ctx.customer)
	return {"key": "sales", "title": _("Sales"), "note": note, "rows": rows}


def _yield_section(ctx, entries):
	periods = ctx.periods
	wash = [e for e in entries if e.location != LIVE_RESIN]

	def yld(keep=lambda e: True):
		g = _sum(periods, wash, lambda e: e.grams, keep)
		frozen = _sum(periods, wash, lambda e: e.lbs * G_PER_LB, keep)
		return _ratio(periods, g, frozen, 100)

	label = _("Average yield – {0}").format(ctx.location) if ctx.location else _("Average yield")
	rows = [_row("yield:total", label, "%", yld(), total=1,
	             drill={"metric": "process", "process": "wash"},
	             hint=_("Grams produced ÷ grams of fresh frozen washed, weighted by weight"))]
	if not ctx.location:
		locations = [loc for loc in WASH_LOCATIONS
		             if loc != "Other partners" or any(e.location == loc for e in wash)]
		for loc in locations:
			rows.append(_row(f"yield:{loc}", loc, "%", yld(lambda e, l=loc: e.location == l), level=1,
			                 hint=_location_hint(loc),
			                 drill={"metric": "process", "process": "wash", "location": loc}))
	return {
		"key": "yield",
		"title": _("Yield"),
		"note": _("MTM washes return bubble hash; Nature returns pressed rosin"),
		"rows": rows,
	}


def _blank_future(rows, future):
	for r in rows:
		if r.get("values"):
			for k in future:
				r["values"][k] = None
		_blank_future(r.get("children") or [], future)


def _period_dict(p):
	return {"key": p.key, "band": p.band, "start": str(p.start), "end": str(p.end),
	        "snapshot": str(p.snapshot), "partial": int(p.partial), "future": int(p.future)}


@frappe.whitelist()
def get_data(as_of=None, company=None, view=None, from_date=None, to_date=None,
             location=None, tier=None, customer=None):
	ctx = _context(as_of, company, view, from_date, to_date, location, tier, customer)
	periods = ctx.periods
	start = min(p.start for p in periods)
	end = max(p.end for p in periods)

	entries = _process_entries(start, end, ctx.company, ctx.location)
	sections = [
		_inventory_section(ctx, _inventory_items(periods, ctx.company, ctx.tier)),
		_production_section(ctx, entries),
		_sales_section(ctx, _sales_lines(start, end, ctx.company, ctx.tier, ctx.customer)),
		_yield_section(ctx, entries),
	]
	future = [p.key for p in periods if p.future]
	for s in sections:
		_blank_future(s["rows"], future)
	current, compare = _kpi_pair(ctx.view, periods)
	return {
		"today": nowdate(),
		"as_of": str(ctx.as_of),
		"view": ctx.view,
		"periods": [_period_dict(p) for p in periods],
		"kpi": {"current": current, "compare": compare},
		"sections": sections,
		"options": {"locations": WASH_LOCATIONS, "tiers": TIER_NAMES},
	}


@frappe.whitelist()
def get_drill(drill, period, as_of=None, company=None, view=None, from_date=None, to_date=None,
              location=None, tier=None, customer=None):
	ctx = _context(as_of, company, view, from_date, to_date, location, tier, customer)
	drill = frappe._dict(frappe.parse_json(drill) or {})
	p = next((x for x in ctx.periods if x.key == period), None)
	if not p:
		frappe.throw(_("Unknown period"))

	if drill.metric == "inventory":
		rows = []
		for r in _inventory_items([p], ctx.company, ctx.tier):
			if drill.group and r.item_group != drill.group:
				continue
			if drill.tier and GROUP_TIER.get(r.item_group) != drill.tier:
				continue
			qty = r.qty[p.key]
			if abs(qty) < 0.005:
				continue
			rows.append({"item_code": r.item_code, "item_name": r.item_name, "item_group": r.item_group,
			             "tier": GROUP_TIER.get(r.item_group), "qty": qty})
		rows.sort(key=lambda r: -r["qty"])
		return {"kind": "inventory", "period": _period_dict(p), "rows": rows}

	if drill.metric == "process":
		rows = []
		for e in _process_entries(p.start, p.end, ctx.company, ctx.location):
			if (e.location == LIVE_RESIN) != (drill.process == "resin"):
				continue
			if drill.location and e.location != drill.location:
				continue
			if drill.ff_group and drill.ff_group not in e.ff_types:
				continue
			if drill.product and drill.product not in e.outputs:
				continue
			rows.append({
				"name": e.name, "posting_date": str(e.posting_date), "location": e.location,
				"warehouse": e.warehouse, "inputs": ", ".join(sorted(e.inputs)),
				"lbs": e.lbs, "outputs": ", ".join(sorted(e.out_items)), "grams": e.grams,
				"yield": e.grams / (e.lbs * G_PER_LB) * 100,
			})
		return {"kind": "process", "period": _period_dict(p), "rows": rows}

	if drill.metric == "sales":
		rows = []
		for r in _sales_lines(p.start, p.end, ctx.company, ctx.tier, ctx.customer):
			if drill.tier and GROUP_TIER.get(r.item_group) != drill.tier:
				continue
			if drill.kind == "rosin" and r.item_group not in GROUP_TIER:
				continue
			if drill.kind == "resin" and r.item_group not in LIVE_RESIN_GROUPS:
				continue
			rows.append({
				"invoice": r.invoice, "posting_date": str(r.posting_date), "customer": r.customer,
				"item_code": r.item_code, "item_name": r.item_name,
				"tier": GROUP_TIER.get(r.item_group) or LIVE_RESIN,
				"qty": flt(r.qty), "amount": flt(r.amount),
			})
		return {"kind": "sales", "period": _period_dict(p), "rows": rows}

	frappe.throw(_("Unknown metric"))
