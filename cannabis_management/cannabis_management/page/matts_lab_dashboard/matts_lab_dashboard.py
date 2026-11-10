import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	date_diff,
	flt,
	get_first_day,
	get_last_day,
	getdate,
	now_datetime,
	nowdate,
)

PAGE_ROLE = "Lab Dashboard"
G_PER_LB = 453.59237
TREND_PERIODS = 6
MAX_RANGE_DAYS = 400
VIEWS = ("week_month", "weeks", "months", "custom")
WASH_OPERATIONS = ("Washing", "Hash Processing")
TOLLING_TYPE = "Tolling Partner"
SAMPLES_TYPE = "Samples"
MAIN_STORAGE = "main storage"
MR_CLOSED = ("Completed", "Stopped", "Cancelled")
LOCATIONS = ("MTM", "Nature")
GRAM_UOMS = ("Gram",)

ROSIN_TIERS = (
	("T1+", ("Tier 1 Plus",)),
	("T1", ("Tier 1", "Primes")),
	("T2", ("Tier 2", "Subprimes")),
	("T3", ("Tier 3",)),
	("T4", ("Tier 4",)),
	("Ungraded", ("Raw Rosin", "Full Spec")),
)
OTHER_STOCK = (
	("Food grade", ("Food Grade",)),
	("VRR", ("VRR",)),
	("LLR", ("Liquid Live Resin",)),
	("Distillate", ("Distallate",)),
)
CATEGORIES = ROSIN_TIERS + OTHER_STOCK
TIER_NAMES = tuple(t for t, _g in ROSIN_TIERS)
GROUP_CATEGORY = {g: c for c, gs in CATEGORIES for g in gs}
ROSIN_GROUPS = tuple(g for _t, gs in ROSIN_TIERS for g in gs)
VRR_GROUPS = ("VRR",)
LLR_GROUPS = ("Liquid Live Resin",)
FG_GROUPS = ("Food Grade",)
DISTILLATE_GROUPS = ("Distallate",)
CONSUMABLE_GROUPS = ("Consumable",)
BUBBLE_HASH = "Bubble Hash"
RAW_ROSIN = "Raw Rosin"
CONCENTRATE_GROUPS = ROSIN_GROUPS + VRR_GROUPS + LLR_GROUPS + FG_GROUPS + DISTILLATE_GROUPS + (
	BUBBLE_HASH, "BHO", "Diamonds", "ISOLATED MATERIAL",
)
GROUP_LABELS = {
	"Primes": "Primes (old T1 grade)",
	"Subprimes": "Subprimes (old T2 grade)",
	"Raw Rosin": "Raw rosin (not graded yet)",
	"Distallate": "Distillate",
	"Liquid Live Resin": "Liquid live resin (LLR)",
}


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


def _check_company(company):
	if company and not frappe.db.exists("Company", company):
		frappe.throw(_("Unknown company {0}").format(company))
	return company or None


def _context(as_of=None, company=None, view=None, from_date=None, to_date=None,
             location=None, tier=None, customer=None):
	_require_access()
	ctx = frappe._dict(
		view=view if view in VIEWS else "week_month",
		as_of=getdate(as_of or nowdate()),
		company=_check_company(company),
		location=location or None,
		tier=tier or None,
		customer=customer or None,
	)
	if ctx.customer and not frappe.db.exists("Customer", ctx.customer):
		frappe.throw(_("Unknown customer {0}").format(ctx.customer))
	if ctx.location and ctx.location not in LOCATIONS:
		frappe.throw(_("Unknown wash location {0}").format(ctx.location))
	if ctx.tier and ctx.tier not in TIER_NAMES:
		frappe.throw(_("Unknown tier {0}").format(ctx.tier))
	ctx.periods = _periods(ctx.view, ctx.as_of, from_date, to_date)
	return ctx


def _company_cond(company, alias):
	return f" and {alias}.company = %(company)s" if company else ""


def _fresh_frozen_groups():
	root = frappe.db.get_value("Item Group", "Fresh Frozen Main", ["lft", "rgt"], as_dict=True)
	if root:
		return tuple(frappe.get_all(
			"Item Group", filters={"lft": [">=", root.lft], "rgt": ["<=", root.rgt]}, pluck="name",
		))
	return tuple(frappe.get_all("Item Group", filters={"name": ["like", "Fresh Frozen%"]}, pluck="name"))


def _ff_label(group):
	label = group.replace("Fresh Frozen", "").strip(" -")
	return label[:1].upper() + label[1:].lower() if label and not label.isupper() else (label or group)


def _internal_customers():
	names = set(frappe.get_all("Company", pluck="name"))
	names |= set(frappe.db.sql_list(
		"""select name from `tabCustomer`
		   where is_internal_customer = 1 or ifnull(represents_company, '') != ''"""
	))
	names |= {"MT", "MTPZ", "MTM"}
	return tuple(sorted(names))


def _tier_groups(tier):
	return tuple(g for t, groups in ROSIN_TIERS if not tier or t == tier for g in groups)


def _mtm_washes(start, end, company):
	ff = _fresh_frozen_groups()
	runs = frappe.db.sql(
		f"""
		select wo.material_request as mr,
		       max(date(coalesce(jc.actual_end_date, jc.posting_date))) as done_on,
		       group_concat(distinct jc.name order by jc.name separator ', ') as job_cards,
		       group_concat(distinct wo.name order by wo.name separator ', ') as work_orders
		from `tabJob Card` jc
		join `tabWork Order` wo on wo.name = jc.work_order
		where jc.docstatus = 1 and jc.status = 'Completed' and jc.operation in %(ops)s
		  and ifnull(wo.material_request, '') != ''
		  {_company_cond(company, "wo")}
		group by wo.material_request
		having done_on between %(start)s and %(end)s
		""",
		{"ops": WASH_OPERATIONS, "start": start, "end": end, "company": company},
		as_dict=True,
	)
	if not runs or not ff:
		return []
	lines = frappe.db.sql(
		"""
		select mri.parent, mri.item_code, mri.item_name, i.item_group, mri.stock_qty
		from `tabMaterial Request Item` mri
		join `tabItem` i on i.name = mri.item_code
		where mri.parent in %(mrs)s and i.item_group in %(ff)s
		""",
		{"mrs": tuple(r.mr for r in runs), "ff": ff},
		as_dict=True,
	)
	by_mr = {}
	for line in lines:
		by_mr.setdefault(line.parent, []).append(line)
	out = []
	for r in runs:
		items = by_mr.get(r.mr, [])
		lbs = sum(flt(i.stock_qty) for i in items)
		if lbs <= 0:
			continue
		ff_types = {}
		for i in items:
			ff_types[i.item_group] = ff_types.get(i.item_group, 0) + flt(i.stock_qty)
		out.append(frappe._dict(
			posting_date=r.done_on, location="MTM", lbs=lbs, ff_types=ff_types,
			doc_type="Material Request", doc=r.mr,
			refs=_("Job card {0} · work order {1}").format(r.job_cards, r.work_orders),
			inputs=", ".join(sorted({i.item_name or i.item_code for i in items})),
		))
	return out


def _nature_washes(start, end, company):
	ff = _fresh_frozen_groups()
	if not ff:
		return []
	rows = frappe.db.sql(
		f"""
		select se.name, se.posting_date, sed.item_code, sed.item_name, i.item_group, i.stock_uom,
		       ifnull(sed.s_warehouse, '') as s_wh, ifnull(sed.t_warehouse, '') as t_wh, sed.transfer_qty as qty
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name
		join `tabItem` i on i.name = sed.item_code
		where se.docstatus = 1 and se.purpose in ('Manufacture', 'Repack')
		  and se.posting_date between %(start)s and %(end)s
		  {_company_cond(company, "se")}
		  and exists (
			select 1 from `tabStock Entry Detail` d join `tabItem` fi on fi.name = d.item_code
			where d.parent = se.name and ifnull(d.s_warehouse, '') like %(nature)s and fi.item_group in %(ff)s
		  )
		order by se.posting_date, se.name, sed.idx
		""",
		{"start": start, "end": end, "company": company, "ff": ff, "nature": "%natur%"},
		as_dict=True,
	)
	ff = set(ff)
	entries = {}
	for r in rows:
		e = entries.setdefault(r.name, frappe._dict(
			name=r.name, posting_date=r.posting_date, ff_in={}, ff_out=0.0, grams=0.0,
			resin=0.0, inputs=set(), outputs=set(),
		))
		consumed = r.s_wh and not r.t_wh
		produced = r.t_wh and not r.s_wh
		if r.item_group in ff:
			if consumed:
				e.ff_in[r.item_group] = e.ff_in.get(r.item_group, 0) + flt(r.qty)
				e.inputs.add(r.item_name or r.item_code)
			elif produced:
				e.ff_out += flt(r.qty)
		elif produced and r.stock_uom in GRAM_UOMS:
			e.grams += flt(r.qty)
			e.outputs.add(r.item_name or r.item_code)
			if r.item_group in LLR_GROUPS + ("BHO", "Diamonds"):
				e.resin += flt(r.qty)
	out = []
	for e in entries.values():
		lbs_in = sum(e.ff_in.values())
		lbs = lbs_in - e.ff_out
		if lbs <= 0 or e.grams <= 0 or e.resin * 2 > e.grams:
			continue
		scale = lbs / lbs_in
		out.append(frappe._dict(
			posting_date=e.posting_date, location="Nature", lbs=lbs,
			ff_types={g: q * scale for g, q in e.ff_in.items()},
			doc_type="Stock Entry", doc=e.name, refs=_("Tolled at Nature's Lab"),
			inputs=", ".join(sorted(e.inputs)), outputs=", ".join(sorted(e.outputs)),
		))
	return out


def _manufacture_entries(start, end, company):
	ff = set(_fresh_frozen_groups())
	rows = frappe.db.sql(
		f"""
		select se.name, se.posting_date, se.work_order, sed.item_code, sed.item_name, i.item_group,
		       i.stock_uom, ifnull(sed.s_warehouse, '') as s_wh, ifnull(sed.t_warehouse, '') as t_wh,
		       sed.transfer_qty as qty, sed.is_finished_item
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name
		join `tabItem` i on i.name = sed.item_code
		where se.docstatus = 1 and se.purpose = 'Manufacture'
		  and se.posting_date between %(start)s and %(end)s
		  {_company_cond(company, "se")}
		order by se.posting_date, se.name, sed.idx
		""",
		{"start": start, "end": end, "company": company},
		as_dict=True,
	)
	entries = {}
	for r in rows:
		e = entries.setdefault(r.name, frappe._dict(
			name=r.name, posting_date=r.posting_date, work_order=r.work_order,
			outputs={}, ff_lbs=0.0, bh_in=0.0, in_items=set(), out_items=set(),
		))
		if r.s_wh and not r.t_wh:
			if r.item_group in ff:
				e.ff_lbs += flt(r.qty)
				e.in_items.add(r.item_name or r.item_code)
			elif r.item_group == BUBBLE_HASH and r.stock_uom in GRAM_UOMS:
				e.bh_in += flt(r.qty)
				e.in_items.add(r.item_name or r.item_code)
		elif r.t_wh and r.is_finished_item and r.stock_uom in GRAM_UOMS:
			e.outputs[r.item_group] = e.outputs.get(r.item_group, 0) + flt(r.qty)
			e.out_items.add(r.item_name or r.item_code)
	out = []
	for e in entries.values():
		if not e.outputs:
			continue
		e.grams = sum(e.outputs.values())
		e.bh_out = e.outputs.get(BUBBLE_HASH, 0.0) if e.ff_lbs else 0.0
		e.rosin_out = e.outputs.get(RAW_ROSIN, 0.0) if e.bh_in else 0.0
		out.append(e)
	return out


def _sales_lines(start, end, company, tier=None, customer=None):
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
			"start": start, "end": end, "company": company, "customer": customer, "uoms": GRAM_UOMS,
			"groups": _tier_groups(tier) + VRR_GROUPS + LLR_GROUPS, "internal": _internal_customers(),
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


def _by_ff(records, periods, keep):
	groups = {}
	for r in records:
		if keep(r):
			for g, v in r.ff_types.items():
				groups.setdefault(g, []).append((r, v))
	out = []
	for g, pairs in sorted(groups.items()):
		values = {p.key: sum(v for r, v in pairs if _in(p, r.posting_date)) for p in periods}
		if _has_value(values):
			out.append((g, values))
	return out


def _production_section(ctx, washes, entries):
	periods = ctx.periods
	locations = [ctx.location] if ctx.location else list(LOCATIONS)
	hints = {
		"MTM": _("Completed washing job cards at MTM: pounds on the material request behind each work order"),
		"Nature": _("Washed by Nature's Lab under tolling (their stock entries; Nature does not use job cards)"),
	}

	def wash_children(loc):
		keep = lambda r, l=loc: r.location == l  # noqa: E731
		return [
			_row(f"wash:lbs:{loc}:{g}", _ff_label(g), "lbs", v, level=2,
			     drill={"metric": "wash", "location": loc, "ff_group": g})
			for g, v in _by_ff(washes, periods, keep)
		]

	rows = [{"id": "wash:lbs:head", "label": _("Pounds washed"), "unit": "lbs", "sub": 1}]
	if ctx.location:
		rows.append(_row("wash:lbs:total", ctx.location, "lbs", _sum(periods, washes, lambda r: r.lbs), total=1,
		                 level=1, children=wash_children(ctx.location), hint=hints[ctx.location],
		                 drill={"metric": "wash", "location": ctx.location}))
	else:
		rows.append(_row("wash:lbs:total", _("Total"), "lbs", _sum(periods, washes, lambda r: r.lbs), total=1,
		                 level=1, drill={"metric": "wash"}))
		for loc in locations:
			rows.append(_row(f"wash:lbs:{loc}", loc, "lbs",
			                 _sum(periods, washes, lambda r: r.lbs, lambda r, l=loc: r.location == l), level=1,
			                 children=wash_children(loc), hint=hints[loc],
			                 drill={"metric": "wash", "location": loc}))

	product_children = []
	for group in sorted({g for e in entries for g in e.outputs}):
		values = _sum(periods, entries, lambda e, g=group: e.outputs.get(g, 0) / 1000)
		if _has_value(values):
			product_children.append(_row(f"mfg:kg:{group}", group, "kg", values, level=2,
			                             drill={"metric": "manufacture", "product": group}))
	rows += [
		{"id": "mfg:kg:head", "label": _("Kilos produced"), "unit": "kg", "sub": 1},
		_row("mfg:kg:total", _("Total"), "kg", _sum(periods, entries, lambda e: e.grams / 1000), total=1, level=1,
		     children=product_children, drill={"metric": "manufacture"},
		     hint=_("Finished items of submitted Manufacture stock entries (bubble hash from washing, raw rosin from pressing)")),
	]
	return {
		"key": "production",
		"title": _("Washing and production"),
		"note": _("Completed washes, and what the Manufacture entries produced"),
		"rows": rows,
	}


def _yield_section(ctx, entries):
	periods = ctx.periods
	bh_out = _sum(periods, entries, lambda e: e.bh_out)
	ff_in = _sum(periods, entries, lambda e: e.ff_lbs * G_PER_LB if e.bh_out else 0)
	rosin_out = _sum(periods, entries, lambda e: e.rosin_out)
	bh_in = _sum(periods, entries, lambda e: e.bh_in if e.rosin_out else 0)
	return {
		"key": "yield",
		"title": _("Yield (running)"),
		"note": _("Output ÷ input over each period, from Manufacture entries"),
		"rows": [
			_row("yield:bh", _("Avg yield – Bubble hash"), "%", _ratio(periods, bh_out, ff_in, 100), total=1,
			     drill={"metric": "manufacture", "yield": "bh"},
			     hint=_("Bubble hash out ÷ fresh frozen in (1 lb = 453.59 g)")),
			_row("yield:rosin", _("Avg yield – Rosin"), "%", _ratio(periods, rosin_out, bh_in, 100), total=1,
			     drill={"metric": "manufacture", "yield": "rosin"},
			     hint=_("Raw rosin out ÷ bubble hash pressed")),
		],
	}


def _sales_section(ctx, lines):
	periods = ctx.periods
	grams = lambda r: flt(r.qty)  # noqa: E731
	amount = lambda r: flt(r.amount)  # noqa: E731
	is_rosin = lambda r: r.item_group in ROSIN_GROUPS  # noqa: E731
	is_vrr = lambda r: r.item_group in VRR_GROUPS  # noqa: E731
	is_llr = lambda r: r.item_group in LLR_GROUPS  # noqa: E731
	volume_children, revenue_children = [], []
	if not ctx.tier:
		for tier, groups in ROSIN_TIERS:
			keep = lambda r, gs=groups: r.item_group in gs  # noqa: E731
			g = _sum(periods, lines, grams, keep)
			amt = _sum(periods, lines, amount, keep)
			if not (_has_value(g) or _has_value(amt)):
				continue
			drill = {"metric": "sales", "kind": "rosin", "tier": tier}
			volume_children.append(_row(f"sales:rosin_g:{tier}", tier, "g", g, level=1, drill=drill))
			revenue_children.append(_row(f"sales:rosin_amt:{tier}", tier, "$", amt, level=1, drill=drill))
	rosin_label = _("Rosin {0}").format(ctx.tier) if ctx.tier else _("Rosin")
	llr_drill = {"metric": "sales", "kind": "llr"}
	vrr_drill = {"metric": "sales", "kind": "vrr"}
	rows = [
		_row("sales:llr_price", _("Avg sales price – Oil (LLR)"), "$/g",
		     _ratio(periods, _sum(periods, lines, amount, is_llr), _sum(periods, lines, grams, is_llr)),
		     drill=llr_drill, hint=_("LLR net amount ÷ LLR grams sold")),
		_row("sales:rosin_g", _("{0} volume sold").format(rosin_label), "g", _sum(periods, lines, grams, is_rosin),
		     children=volume_children, drill={"metric": "sales", "kind": "rosin"},
		     hint=_("All rosin tiers; T1 includes Primes and T2 Subprimes")),
		_row("sales:rosin_amt", _("{0} revenue").format(rosin_label), "$", _sum(periods, lines, amount, is_rosin),
		     children=revenue_children, drill={"metric": "sales", "kind": "rosin"}),
		_row("sales:vrr_g", _("VRR sold"), "g", _sum(periods, lines, grams, is_vrr), drill=vrr_drill),
		_row("sales:vrr_amt", _("VRR revenue"), "$", _sum(periods, lines, amount, is_vrr), drill=vrr_drill),
		_row("sales:llr_g", _("LLR sold"), "g", _sum(periods, lines, grams, is_llr), drill=llr_drill),
		_row("sales:llr_amt", _("LLR revenue"), "$", _sum(periods, lines, amount, is_llr), drill=llr_drill),
	]
	note = _("Submitted invoices to outside customers, net of returns")
	if ctx.customer:
		note = _("Invoices to {0}, net of returns").format(ctx.customer)
	return {"key": "sales", "title": _("Sales"), "note": note, "rows": rows}


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

	washes = []
	if ctx.location in (None, "MTM"):
		washes += _mtm_washes(start, end, ctx.company)
	if ctx.location in (None, "Nature"):
		washes += _nature_washes(start, end, ctx.company)
	entries = _manufacture_entries(start, end, ctx.company)
	sections = [
		_production_section(ctx, washes, entries),
		_yield_section(ctx, entries),
		_sales_section(ctx, _sales_lines(start, end, ctx.company, ctx.tier, ctx.customer)),
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
	}


def _warehouse_kinds(company):
	filters = {"is_group": 0}
	if company:
		filters["company"] = company
	kinds = {}
	for w in frappe.get_all("Warehouse", filters=filters, fields=["name", "warehouse_type"]):
		if w.warehouse_type == SAMPLES_TYPE or "sample" in w.name.lower():
			kinds[w.name] = "samples"
		elif w.warehouse_type == TOLLING_TYPE:
			kinds[w.name] = "partner"
		elif w.name.lower().startswith(MAIN_STORAGE):
			kinds[w.name] = "main"
		else:
			kinds[w.name] = "other"
	return kinds


def _stock_row(rid, label, unit, bins, **kw):
	qty = sum(flt(b.qty) for b in bins)
	skus = len({b.item_code for b in bins if abs(flt(b.qty)) >= 0.005})
	if unit == "kg":
		qty = qty / 1000
	return {"id": rid, "label": label, "unit": unit, "qty": qty,
	        "value": sum(flt(b.value) for b in bins), "skus": skus, **kw}


def _stock_sections(bins, mr_lines, tier, samples_configured):
	ff = set(_fresh_frozen_groups())
	own = [b for b in bins if b.kind == "main" and abs(flt(b.qty)) >= 0.005]
	own_g = [b for b in own if b.uom in GRAM_UOMS]
	partner = [b for b in bins if b.kind == "partner" and abs(flt(b.qty)) >= 0.005]
	samples = [b for b in bins if b.kind == "samples" and abs(flt(b.qty)) >= 0.005]
	tiers = [(t, gs) for t, gs in ROSIN_TIERS if not tier or t == tier]
	existing = set(frappe.get_all("Item Group", filters={"name": ["in", list(GROUP_CATEGORY)]}, pluck="name"))

	def in_groups(rows, groups):
		return [b for b in rows if b.item_group in groups]

	def tier_rows(prefix, unit, level=0):
		out = []
		for t, gs in tiers:
			children = []
			for g in gs:
				gb = in_groups(own_g, (g,))
				if gb:
					children.append(_stock_row(f"{prefix}:{g}", GROUP_LABELS.get(g, g), unit, gb, level=level + 1,
					                           drill={"kind": "stock", "scope": "main", "groups": [g]}))
			hint = ""
			if not existing.intersection(gs):
				hint = _("No item group named {0} exists yet.").format(" / ".join(gs))
			elif len(gs) > 1:
				hint = _("Includes {0}").format(", ".join(GROUP_LABELS.get(g, g) for g in gs))
			out.append(_stock_row(f"{prefix}:{t}", t, unit, in_groups(own_g, gs), level=level, hint=hint,
			                      children=children if len(children) > 1 else [],
			                      drill={"kind": "stock", "scope": "main", "groups": list(gs)}))
		return out

	rosin_groups = [g for _t, gs in tiers for g in gs]
	rosin = tier_rows("stock:rosin", "g")
	if tier:
		rosin[0].update(id="stock:rosin:total", total=1)
	else:
		rosin.insert(0, _stock_row("stock:rosin:total", _("Total"), "g", in_groups(own_g, rosin_groups), total=1,
		                           drill={"kind": "stock", "scope": "main", "groups": rosin_groups}))

	def by_warehouse(prefix, rows, unit, bucket):
		out = []
		for wh in sorted({b.warehouse for b in rows}):
			wb = [b for b in rows if b.warehouse == wh]
			out.append(_stock_row(f"{prefix}:{wh}", wh, unit, wb, level=2,
			                      drill={"kind": "stock", "scope": "partner", "bucket": bucket, "warehouse": wh}))
		return out

	p_ff = [b for b in partner if b.item_group in ff]
	p_conc = [b for b in partner if b.item_group in CONCENTRATE_GROUPS and b.uom in GRAM_UOMS]
	p_other = [b for b in partner if b not in p_ff and b not in p_conc]
	open_lines = [m for m in mr_lines if m.item_group in ff]
	mr_lbs = sum(flt(m.pending) for m in open_lines)
	pending_total = sum(flt(b.qty) for b in p_ff) + mr_lbs
	mr_children = []
	for g in sorted({m.item_group for m in open_lines}):
		lines = [m for m in open_lines if m.item_group == g]
		mr_children.append({"id": f"pending:mr:{g}", "label": _ff_label(g), "unit": "lbs", "level": 2,
		                    "qty": sum(flt(m.pending) for m in lines), "skus": len({m.item_code for m in lines}),
		                    "drill": {"kind": "mr", "ff_group": g}})
	other_row = _stock_row("pending:other", _("Other items at tolling partners"), "items", p_other, level=1,
	                       children=by_warehouse("pending:other", p_other, "items", "other"),
	                       drill={"kind": "stock", "scope": "partner", "bucket": "other"},
	                       hint=_("Hardware, packaged goods and anything else counted in its own units"))
	other_row["qty"] = other_row["skus"]
	for c in other_row["children"]:
		c["qty"] = c["skus"]
	pending = [
		{"id": "pending:total", "label": _("Total pending fresh frozen"), "unit": "lbs", "total": 1,
		 "qty": pending_total, "skus": len({b.item_code for b in p_ff} | {m.item_code for m in open_lines}),
		 "value": sum(flt(b.value) for b in p_ff),
		 "hint": _("Fresh frozen at tolling partners plus open material requests")},
		_stock_row("pending:ff", _("Fresh frozen at tolling partners"), "lbs", p_ff, level=1,
		           children=by_warehouse("pending:ff", p_ff, "lbs", "ff"),
		           drill={"kind": "stock", "scope": "partner", "bucket": "ff"}),
		{"id": "pending:mr", "label": _("Open material requests (not yet made)"), "unit": "lbs", "level": 1,
		 "qty": mr_lbs, "skus": len({m.item_code for m in open_lines}), "children": mr_children,
		 "drill": {"kind": "mr"},
		 "hint": _("Submitted material requests that are not completed: quantity less ordered quantity")},
		_stock_row("pending:conc", _("Hash, rosin and oil at tolling partners"), "g", p_conc, level=1,
		           children=by_warehouse("pending:conc", p_conc, "g", "conc"),
		           drill={"kind": "stock", "scope": "partner", "bucket": "conc"},
		           hint=_("Concentrates held in warehouses typed Tolling Partner (not counted in rosin stock)")),
		other_row,
	]

	back_rosin = _stock_row("back:rosin", _("Rosin"), "kg", in_groups(own_g, rosin_groups), level=1,
	                        children=tier_rows("back:rosin", "kg", level=2),
	                        drill={"kind": "stock", "scope": "main", "groups": rosin_groups})
	back_parts = [
		back_rosin,
		_stock_row("back:vrr", _("VRR"), "kg", in_groups(own_g, VRR_GROUPS), level=1,
		           drill={"kind": "stock", "scope": "main", "groups": list(VRR_GROUPS)}),
		_stock_row("back:llr", _("LLR"), "kg", in_groups(own_g, LLR_GROUPS), level=1,
		           drill={"kind": "stock", "scope": "main", "groups": list(LLR_GROUPS)}),
		_stock_row("back:fg", _("Food grade"), "kg", in_groups(own_g, FG_GROUPS), level=1,
		           drill={"kind": "stock", "scope": "main", "groups": list(FG_GROUPS)}),
	]
	back_groups = rosin_groups + list(VRR_GROUPS + LLR_GROUPS + FG_GROUPS)
	back = [_stock_row("back:total", _("Total"), "kg", in_groups(own_g, back_groups), total=1,
	                   drill={"kind": "stock", "scope": "main", "groups": back_groups})] + back_parts

	consumables = in_groups(own, CONSUMABLE_GROUPS)
	consumable_row = _stock_row("other:consumables", _("Consumables"), "items", consumables,
	                            drill={"kind": "stock", "scope": "main", "groups": list(CONSUMABLE_GROUPS)},
	                            hint=_("Items in stock in the Consumable item group. The 2.5 threshold is still to be confirmed."))
	consumable_row["qty"] = consumable_row["skus"]
	samples_row = _stock_row("other:samples", _("Samples"), "g", [b for b in samples if b.uom in GRAM_UOMS],
	                         drill={"kind": "stock", "scope": "samples"},
	                         children=[
		                         _stock_row(f"other:samples:{wh}", wh, "g",
		                                    [b for b in samples if b.warehouse == wh and b.uom in GRAM_UOMS], level=1,
		                                    drill={"kind": "stock", "scope": "samples", "warehouse": wh})
		                         for wh in sorted({b.warehouse for b in samples})
	                         ],
	                         hint=_("Stock in warehouses of type Samples (one per partner, e.g. Samples - Leef)")
	                         if samples_configured else
	                         _("No samples warehouse yet. Create a warehouse of type Samples for each partner "
	                           "(e.g. Samples - Leef - MT) and its stock shows here."))
	other = [
		_stock_row("other:distillate", _("Distillate back stock"), "kg", in_groups(own_g, DISTILLATE_GROUPS),
		           drill={"kind": "stock", "scope": "main", "groups": list(DISTILLATE_GROUPS)}),
		consumable_row,
		samples_row,
	]
	return [
		{"key": "rosin", "title": _("Rosin stock"), "note": _("Grams in Main Storage"), "rows": rosin},
		{"key": "pending", "title": _("Pending batches"), "note": _("At tolling partners, plus open material requests"), "rows": pending},
		{"key": "back", "title": _("Back stock"), "note": _("Kilos in Main Storage by product"), "rows": back},
		{"key": "other", "title": _("Distillate, consumables and samples"), "note": _("Distillate and consumables in Main Storage; samples in Samples warehouses"), "rows": other},
	]


@frappe.whitelist()
def get_stock(company=None, tier=None):
	_require_access()
	company = _check_company(company)
	tier = tier or None
	if tier and tier not in TIER_NAMES:
		frappe.throw(_("Unknown tier {0}").format(tier))
	kinds = _warehouse_kinds(company)
	if not kinds:
		kinds = {"": "other"}
	ff = _fresh_frozen_groups()
	tracked = tuple(GROUP_CATEGORY) + CONSUMABLE_GROUPS
	bins = frappe.db.sql(
		"""
		select b.item_code, i.item_name, i.item_group, i.stock_uom as uom, b.warehouse,
		       b.actual_qty as qty, b.reserved_qty as reserved, b.stock_value as value
		from `tabBin` b
		join `tabItem` i on i.name = b.item_code
		where b.warehouse in %(warehouses)s and (b.actual_qty != 0 or b.reserved_qty != 0)
		""",
		{"warehouses": tuple(kinds)},
		as_dict=True,
	)
	keep = []
	for b in bins:
		b.kind = kinds.get(b.warehouse, "other")
		if b.kind in ("partner", "samples") or b.item_group in tracked:
			b.category = GROUP_CATEGORY.get(b.item_group)
			keep.append(b)
	catalog = frappe.db.sql(
		"""
		select i.name as item_code, i.item_name, i.item_group, i.stock_uom as uom, i.disabled
		from `tabItem` i
		where i.item_group in %(groups)s
		  and (i.disabled = 0 or exists (select 1 from `tabBin` b where b.item_code = i.name and b.actual_qty != 0))
		""",
		{"groups": tuple(GROUP_CATEGORY)},
		as_dict=True,
	)
	last_moved = dict(frappe.db.sql(
		f"""
		select sle.item_code, max(sle.posting_date)
		from `tabStock Ledger Entry` sle
		join `tabItem` i on i.name = sle.item_code
		where sle.is_cancelled = 0 and i.item_group in %(groups)s
		  {_company_cond(company, "sle")}
		group by sle.item_code
		""",
		{"groups": tuple(GROUP_CATEGORY), "company": company},
	))
	for c in catalog:
		c.category = GROUP_CATEGORY.get(c.item_group)
		c.group_label = GROUP_LABELS.get(c.item_group, c.item_group)
		c.last_moved = str(last_moved[c.item_code]) if last_moved.get(c.item_code) else None
	mr_lines = frappe.db.sql(
		f"""
		select mr.name as mr, mr.transaction_date, mr.status, mr.company, mri.item_code, mri.item_name,
		       i.item_group, mri.stock_qty as qty, mri.ordered_qty as ordered,
		       mri.stock_qty - ifnull(mri.ordered_qty, 0) as pending, mri.stock_uom as uom, mri.warehouse
		from `tabMaterial Request Item` mri
		join `tabMaterial Request` mr on mr.name = mri.parent
		join `tabItem` i on i.name = mri.item_code
		where mr.docstatus = 1 and mr.status not in %(closed)s
		  and mri.stock_qty > ifnull(mri.ordered_qty, 0)
		  {_company_cond(company, "mr")}
		order by mr.transaction_date, mr.name
		""",
		{"closed": MR_CLOSED, "company": company},
		as_dict=True,
	)
	samples_configured = any(k == "samples" for k in kinds.values())
	return {
		"as_of": str(now_datetime()),
		"company": company or "",
		"categories": [{"key": c, "groups": list(gs), "rosin": int(c in TIER_NAMES)} for c, gs in CATEGORIES],
		"sections": _stock_sections(keep, mr_lines, tier, samples_configured),
		"bins": keep,
		"catalog": catalog,
		"mr_lines": mr_lines,
		"ff_groups": list(ff),
		"concentrate_groups": list(CONCENTRATE_GROUPS),
		"group_labels": GROUP_LABELS,
	}


@frappe.whitelist()
def get_drill(drill, period, as_of=None, company=None, view=None, from_date=None, to_date=None,
              location=None, tier=None, customer=None):
	ctx = _context(as_of, company, view, from_date, to_date, location, tier, customer)
	drill = frappe._dict(frappe.parse_json(drill) or {})
	p = next((x for x in ctx.periods if x.key == period), None)
	if not p:
		frappe.throw(_("Unknown period"))

	if drill.metric == "wash":
		loc = drill.location or ctx.location
		records = []
		if loc in (None, "MTM"):
			records += _mtm_washes(p.start, p.end, ctx.company)
		if loc in (None, "Nature"):
			records += _nature_washes(p.start, p.end, ctx.company)
		rows = [
			{"posting_date": str(r.posting_date), "location": r.location, "doc_type": r.doc_type, "doc": r.doc,
			 "refs": r.refs, "inputs": r.inputs,
			 "lbs": r.ff_types.get(drill.ff_group, 0) if drill.ff_group else r.lbs}
			for r in sorted(records, key=lambda r: (r.posting_date, r.doc))
			if not drill.ff_group or drill.ff_group in r.ff_types
		]
		return {"kind": "wash", "period": _period_dict(p), "rows": rows}

	if drill.metric == "manufacture":
		rows = []
		for e in _manufacture_entries(p.start, p.end, ctx.company):
			if drill.product and drill.product not in e.outputs:
				continue
			if drill.get("yield") == "bh" and not e.bh_out:
				continue
			if drill.get("yield") == "rosin" and not e.rosin_out:
				continue
			if drill.get("yield") == "rosin":
				inp, inp_unit, out = e.bh_in, "g", e.rosin_out
				pct = out / inp * 100 if inp else None
			elif drill.get("yield") == "bh" or (e.ff_lbs and not e.bh_in):
				inp, inp_unit, out = e.ff_lbs, "lbs", e.bh_out or e.grams
				pct = out / (inp * G_PER_LB) * 100 if inp else None
			else:
				inp, inp_unit, out = e.bh_in, "g", e.grams
				pct = out / inp * 100 if inp else None
			if drill.product:
				out = e.outputs.get(drill.product, 0)
			rows.append({
				"posting_date": str(e.posting_date), "name": e.name, "work_order": e.work_order,
				"inputs": ", ".join(sorted(e.in_items)), "input": inp, "input_unit": inp_unit,
				"outputs": ", ".join(sorted(e.out_items)), "grams": out, "yield": pct,
			})
		return {"kind": "manufacture", "period": _period_dict(p), "rows": rows}

	if drill.metric == "sales":
		rows = []
		for r in _sales_lines(p.start, p.end, ctx.company, ctx.tier, ctx.customer):
			if drill.kind == "rosin" and r.item_group not in ROSIN_GROUPS:
				continue
			if drill.kind == "vrr" and r.item_group not in VRR_GROUPS:
				continue
			if drill.kind == "llr" and r.item_group not in LLR_GROUPS:
				continue
			if drill.tier and GROUP_CATEGORY.get(r.item_group) != drill.tier:
				continue
			rows.append({
				"invoice": r.invoice, "posting_date": str(r.posting_date), "customer": r.customer,
				"item_code": r.item_code, "item_name": r.item_name,
				"tier": GROUP_CATEGORY.get(r.item_group) or r.item_group,
				"qty": flt(r.qty), "amount": flt(r.amount),
			})
		return {"kind": "sales", "period": _period_dict(p), "rows": rows}

	frappe.throw(_("Unknown metric"))
