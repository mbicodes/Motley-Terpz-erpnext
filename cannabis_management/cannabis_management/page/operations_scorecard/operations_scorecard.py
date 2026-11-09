import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, nowdate

PAGE_ROLE = "Operations Scorecard"
G_PER_LB = 453.59237
MTM_COMPANY = "Master Touch Manufacturing"

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


def _periods(as_of):
	d = getdate(as_of or nowdate())
	today = getdate(nowdate())
	week = add_days(d, -d.weekday())
	month = get_first_day(d)
	spans = (
		("week", _("Week"), week, add_days(week, 6)),
		("prev_week", _("Previous week"), add_days(week, -7), add_days(week, -1)),
		("month", _("Month"), month, get_last_day(d)),
		("prev_month", _("Previous month"), get_first_day(add_months(d, -1)), add_days(month, -1)),
	)
	out = []
	for key, label, start, end in spans:
		start, end = getdate(start), getdate(end)
		out.append(frappe._dict(
			key=key, label=label, start=start, end=end,
			snapshot=min(end, today), partial=end > today, future=start > today,
		))
	return out


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


def _inventory_items(periods, company):
	items = {}
	balances = {}
	for p in periods:
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
				{"date": p.snapshot, "groups": tuple(GROUP_TIER), "uoms": GRAM_UOMS, "company": company},
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


def _process_entries(start, end, company):
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
		if r.item_group in ff:
			if consumed:
				e.ff_in[r.item_group] = e.ff_in.get(r.item_group, 0) + flt(r.qty)
				e.wh_lbs[r.s_wh] = e.wh_lbs.get(r.s_wh, 0) + flt(r.qty)
				e.inputs[r.item_name or r.item_code] = e.inputs.get(r.item_name or r.item_code, 0) + flt(r.qty)
			elif produced:
				e.ff_out += flt(r.qty)
		elif produced and r.stock_uom in GRAM_UOMS:
			e.outputs[r.item_group] = e.outputs.get(r.item_group, 0) + flt(r.qty)
			name = r.item_name or r.item_code
			e.out_items[name] = e.out_items.get(name, 0) + flt(r.qty)

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
		out.append(e)
	return out


def _sales_lines(start, end, company):
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
		  {_company_cond(company, "si")}
		order by si.posting_date, si.name, sii.idx
		""",
		{
			"start": start, "end": end, "company": company, "uoms": GRAM_UOMS,
			"groups": tuple(GROUP_TIER) + LIVE_RESIN_GROUPS, "internal": _internal_customers(),
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


def _inventory_section(periods, items):
	existing = set(frappe.get_all("Item Group", filters={"name": ["in", list(GROUP_TIER)]}, pluck="name"))
	rows = []
	totals = {p.key: 0.0 for p in periods}
	for tier, groups in TIERS:
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
	rows.insert(0, _row("inv:total", _("Total"), "g", totals, total=1, drill={"metric": "inventory"}))
	return {
		"key": "inventory",
		"title": _("Rosin inventory by tier"),
		"note": _("Grams on hand at the end of each period (today for the current one)"),
		"rows": rows,
	}


def _by(records, periods, field_key, value_key, keep=lambda r: True):
	groups = {}
	for r in records:
		if not keep(r):
			continue
		for k, v in r[field_key].items():
			groups.setdefault(k, []).append((r, v))
	out = []
	for k, pairs in sorted(groups.items()):
		values = {p.key: sum(v for r, v in pairs if _in(p, r.posting_date)) for p in periods}
		if _has_value(values):
			out.append((k, values))
	return out


def _production_section(periods, entries):
	wash = [e for e in entries if e.location != LIVE_RESIN]
	resin = [e for e in entries if e.location == LIVE_RESIN]
	rows = []

	locations = [loc for loc in WASH_LOCATIONS
	             if loc != "Other partners" or _has_value(_sum(periods, wash, lambda e: e.lbs, lambda e, l=loc: e.location == l))]

	rows.append({"id": "wash:lbs:head", "label": _("Pounds washed"), "unit": "lbs", "sub": 1})
	rows.append(_row("wash:lbs:total", _("Total"), "lbs", _sum(periods, wash, lambda e: e.lbs), total=1, level=1,
	                 drill={"metric": "process", "process": "wash"}))
	for loc in locations:
		keep = lambda e, l=loc: e.location == l  # noqa: E731
		children = [
			_row(f"wash:lbs:{loc}:{g}", g, "lbs", v, level=2,
			     drill={"metric": "process", "process": "wash", "location": loc, "ff_group": g})
			for g, v in _by(wash, periods, "ff_types", None, keep)
		]
		rows.append(_row(f"wash:lbs:{loc}", loc, "lbs", _sum(periods, wash, lambda e: e.lbs, keep), level=1,
		                 children=children, hint=_location_hint(loc),
		                 drill={"metric": "process", "process": "wash", "location": loc}))

	rows.append({"id": "wash:kg:head", "label": _("Kilos produced"), "unit": "kg", "sub": 1})
	rows.append(_row("wash:kg:total", _("Total"), "kg", _sum(periods, wash, lambda e: e.grams / 1000), total=1,
	                 level=1, drill={"metric": "process", "process": "wash"}))
	for loc in locations:
		keep = lambda e, l=loc: e.location == l  # noqa: E731
		children = [
			_row(f"wash:kg:{loc}:{g}", g, "kg", {k: x / 1000 for k, x in v.items()}, level=2,
			     drill={"metric": "process", "process": "wash", "location": loc, "product": g})
			for g, v in _by(wash, periods, "outputs", None, keep)
		]
		rows.append(_row(f"wash:kg:{loc}", loc, "kg", _sum(periods, wash, lambda e: e.grams / 1000, keep), level=1,
		                 children=children, hint=_location_hint(loc),
		                 drill={"metric": "process", "process": "wash", "location": loc}))

	resin_lbs = _sum(periods, resin, lambda e: e.lbs)
	resin_g = _sum(periods, resin, lambda e: e.grams)
	rows.append({"id": "resin:head", "label": _("Live resin extraction (BHO, not a wash)"), "unit": "", "sub": 1})
	rows.append(_row("resin:lbs", _("Pounds extracted"), "lbs", resin_lbs, level=1,
	                 drill={"metric": "process", "process": "resin"},
	                 hint=_("Fresh frozen sent to hydrocarbon extraction (Leaf, Buddies Brand, etc.). Kept out of the wash totals.")))
	rows.append(_row("resin:kg", _("Kilos produced"), "kg", {k: v / 1000 for k, v in resin_g.items()}, level=1,
	                 drill={"metric": "process", "process": "resin"}))
	rows.append(_row("resin:yield", _("Yield"), "%", _ratio(periods, resin_g, {k: v * G_PER_LB for k, v in resin_lbs.items()}, 100),
	                 level=1, drill={"metric": "process", "process": "resin"}))

	return {
		"key": "production",
		"title": _("Washing and production"),
		"note": _("Fresh frozen consumed by wash runs, and what came out of them"),
		"rows": rows,
	}, locations


def _location_hint(loc):
	return {
		"MTM": _("Washed in-house at Master Touch Manufacturing (freezers and work orders)"),
		"Nature": _("Tolled at Nature's Lab"),
		"Other partners": _("Washed by other tolling partners, e.g. Bloom"),
	}.get(loc, "")


def _sales_section(periods, lines):
	rosin = lambda r: r.item_group in GROUP_TIER  # noqa: E731
	grams = lambda r: flt(r.qty)  # noqa: E731
	amount = lambda r: flt(r.amount)  # noqa: E731

	oil_g = _sum(periods, lines, grams)
	oil_amt = _sum(periods, lines, amount)
	price_children = []
	volume_children = []
	revenue_children = []
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

	rows = [
		_row("sales:price", _("Avg sales price – oil"), "$/g", _ratio(periods, oil_amt, oil_g),
		     children=price_children, drill={"metric": "sales"},
		     hint=_("Revenue ÷ grams for rosin (all tiers) and live resin sold to outside customers")),
		_row("sales:g", _("Rosin volume sold"), "g", _sum(periods, lines, grams, rosin),
		     children=volume_children, drill={"metric": "sales", "kind": "rosin"}),
		_row("sales:amt", _("Rosin revenue"), "$", _sum(periods, lines, amount, rosin),
		     children=revenue_children, drill={"metric": "sales", "kind": "rosin"}),
	]
	return {
		"key": "sales",
		"title": _("Sales"),
		"note": _("Submitted sales invoices to outside customers, net of returns; intercompany sales left out"),
		"rows": rows,
	}


def _yield_section(periods, entries, locations):
	wash = [e for e in entries if e.location != LIVE_RESIN]

	def yld(keep=lambda e: True):
		g = _sum(periods, wash, lambda e: e.grams, keep)
		frozen = _sum(periods, wash, lambda e: e.lbs * G_PER_LB, keep)
		return _ratio(periods, g, frozen, 100)

	rows = [_row("yield:total", _("Average yield"), "%", yld(), total=1,
	             drill={"metric": "process", "process": "wash"},
	             hint=_("Grams produced ÷ grams of fresh frozen washed, weighted by weight"))]
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


def _companies():
	return frappe.get_all("Company", pluck="name", order_by="name")


def _clean_company(company):
	if company and company not in _companies():
		frappe.throw(_("Unknown company {0}").format(company))
	return company or None


@frappe.whitelist()
def get_data(as_of=None, company=None):
	_require_access()
	company = _clean_company(company)
	periods = _periods(as_of)
	start = min(p.start for p in periods)
	end = max(p.end for p in periods)

	entries = _process_entries(start, end, company)
	production, locations = _production_section(periods, entries)
	sections = [
		_inventory_section(periods, _inventory_items(periods, company)),
		production,
		_sales_section(periods, _sales_lines(start, end, company)),
		_yield_section(periods, entries, locations),
	]
	return {
		"as_of": str(getdate(as_of or nowdate())),
		"today": nowdate(),
		"company": company or "",
		"companies": _companies(),
		"periods": [
			{"key": p.key, "label": p.label, "start": str(p.start), "end": str(p.end),
			 "snapshot": str(p.snapshot), "partial": int(p.partial), "future": int(p.future)}
			for p in periods
		],
		"sections": sections,
	}


@frappe.whitelist()
def get_drill(drill, period, as_of=None, company=None):
	_require_access()
	company = _clean_company(company)
	drill = frappe._dict(frappe.parse_json(drill) or {})
	p = next((x for x in _periods(as_of) if x.key == period), None)
	if not p:
		frappe.throw(_("Unknown period"))

	if drill.metric == "inventory":
		items = _inventory_items([p], company)
		rows = []
		for r in items:
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
		for e in _process_entries(p.start, p.end, company):
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
				"warehouse": e.warehouse,
				"inputs": ", ".join(sorted(e.inputs)),
				"lbs": e.lbs, "outputs": ", ".join(sorted(e.out_items)), "grams": e.grams,
				"yield": e.grams / (e.lbs * G_PER_LB) * 100,
			})
		return {"kind": "process", "period": _period_dict(p), "rows": rows}

	if drill.metric == "sales":
		rows = []
		for r in _sales_lines(p.start, p.end, company):
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


def _period_dict(p):
	return {"key": p.key, "label": p.label, "start": str(p.start), "end": str(p.end), "snapshot": str(p.snapshot)}
