"""Conversion & Tolling dashboard.

Reads submitted Conversion Entries and splits them in two: Tolling (reasons =
"Tolling") and Conversion (everything else -- Blending, Co-packing, Others and
the early entries with no reason at all).

A Conversion Entry Item row is a fixed set of slots (Raw Material 1-7, Finished
Good 1-3), so every row is exploded into one line per filled slot before
anything is summed. Weights are reported in grams whatever the item is stocked
in (LBS of fresh frozen, grams of rosin); count items such as hardware and
packaged vapes are reported in units and never mixed into a gram total.

Tolling yields follow the floor's own sheet -- Fresh Frozen to Hash, Fresh
Frozen to Rosin, Hash to Rosin, and grams per rosin tier. The grams typed into
the row's yield fields win when filled; otherwise they are read off the items.
"""

from collections import defaultdict

import frappe
from frappe.utils import flt, getdate

from cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry import (
	grams_per_unit,
)

RM_SLOTS = 7
FG_SLOTS = 3

HARDWARE_GROUP = "Hardware Inventory"
HASH_GROUP = "Bubble Hash"
TIER_GROUPS = {"Tier 1": "tier_1", "Tier 1 Plus": "tier_1", "Tier 2": "tier_2", "Tier 3": "tier_3"}
ROSIN_GROUPS = set(TIER_GROUPS) | {"Raw Rosin"}


def _is_frozen(group):
	return (group or "").startswith("Fresh Frozen")


@frappe.whitelist()
def get_filter_options():
	return {
		"companies": frappe.get_all(
			"Conversion Entry", filters={"docstatus": 1}, pluck="company", distinct=True
		),
	}


@frappe.whitelist()
def get_data(from_date=None, to_date=None, company=None, customer=None):
	frappe.has_permission("Conversion Entry", "read", throw=True)

	conds = ["docstatus = 1"]
	values = {}
	if from_date:
		conds.append("posting_date >= %(from_date)s")
		values["from_date"] = getdate(from_date)
	if to_date:
		conds.append("posting_date <= %(to_date)s")
		values["to_date"] = getdate(to_date)
	if company:
		conds.append("company = %(company)s")
		values["company"] = company
	if customer:
		conds.append("customer = %(customer)s")
		values["customer"] = customer

	headers = frappe.db.sql(
		f"""
		select name, posting_date, company, customer, project, reasons, workstation
		from `tabConversion Entry`
		where {" and ".join(conds)}
		order by posting_date desc, name desc
		""",
		values,
		as_dict=True,
	)
	if not headers:
		return {"tolling": _empty(), "conversion": _empty()}

	by_name = {h.name: h for h in headers}
	rows = frappe.get_all(
		"Conversion Entry Item",
		filters={"parent": ["in", list(by_name)], "parenttype": "Conversion Entry"},
		fields=["*"],
		order_by="parent, idx",
	)

	items = _item_meta(rows)
	factors = {}

	def grams(qty, uom):
		if uom not in factors:
			factors[uom] = grams_per_unit(uom)
		return flt(qty) * factors[uom]

	segments = {"tolling": [], "conversion": []}
	for h in headers:
		segments["tolling" if h.reasons == "Tolling" else "conversion"].append(h.name)

	# One line per filled slot: (entry, row, side, item_code, qty, grams, units)
	lines = []
	for r in rows:
		for side, slots, item_f, qty_f in (
			("in", RM_SLOTS, "raw_material_{}", "qty_rm_{}"),
			("out", FG_SLOTS, "finished_good_{}", "qty_fg_{}"),
		):
			for i in range(1, slots + 1):
				code = r.get(item_f.format(i))
				qty = flt(r.get(qty_f.format(i)))
				if not code or not qty:
					continue
				meta = items.get(code) or frappe._dict(item_name=code, item_group=None, stock_uom=None)
				g = grams(qty, meta.stock_uom)
				lines.append(frappe._dict(
					entry=r.parent, row=r.name, side=side, item_code=code,
					item_name=meta.item_name, item_group=meta.item_group or "(No group)",
					uom=meta.stock_uom, qty=qty, grams=g, units=0 if g else qty,
				))

	lines_by_entry = defaultdict(list)
	for ln in lines:
		lines_by_entry[ln.entry].append(ln)
	rows_by_entry = defaultdict(list)
	for r in rows:
		rows_by_entry[r.parent].append(r)

	out = {}
	for key, names in segments.items():
		seg_lines = [ln for n in names for ln in lines_by_entry[n]]
		out[key] = _summarise(
			[by_name[n] for n in names], seg_lines, lines_by_entry, rows_by_entry
		)
	return out


def _item_meta(rows):
	codes = set()
	for r in rows:
		for i in range(1, RM_SLOTS + 1):
			if r.get(f"raw_material_{i}"):
				codes.add(r.get(f"raw_material_{i}"))
		for i in range(1, FG_SLOTS + 1):
			if r.get(f"finished_good_{i}"):
				codes.add(r.get(f"finished_good_{i}"))
	if not codes:
		return {}
	return {
		d.name: d
		for d in frappe.get_all(
			"Item",
			filters={"name": ["in", list(codes)]},
			fields=["name", "item_name", "item_group", "stock_uom"],
		)
	}


def _empty():
	return _summarise([], [], {}, {})


def _summarise(entries, lines, lines_by_entry, rows_by_entry):
	ins = [ln for ln in lines if ln.side == "in"]
	outs = [ln for ln in lines if ln.side == "out"]
	hardware = [ln for ln in ins if ln.item_group == HARDWARE_GROUP]
	material_in = [ln for ln in ins if ln.item_group != HARDWARE_GROUP]

	input_g = sum(ln.grams for ln in material_in)
	output_g = sum(ln.grams for ln in outs)

	kpis = {
		"entries": len(entries),
		"customers": len({e.customer for e in entries if e.customer}),
		"input_g": flt(input_g, 2),
		"output_g": flt(output_g, 2),
		"yield_pct": flt(output_g / input_g * 100, 2) if input_g else None,
		"hardware_units": flt(sum(ln.qty for ln in hardware), 2),
		"units_out": flt(sum(ln.units for ln in outs), 2),
	}

	yields = [_entry_yield(e, lines_by_entry[e.name], rows_by_entry[e.name]) for e in entries]
	yields = [y for y in yields if y]
	totals = {k: sum(y[k] for y in yields) for k in ("frozen_g", "hash_g", "rosin_g", "tier_1", "tier_2", "tier_3")}
	# Each ratio only over the entries that have both of its sides, so an entry
	# that pressed bought-in hash does not count as a 0% wash, and vice versa.
	def ratio(num_key, den_key):
		both = [y for y in yields if y[num_key] and y[den_key]]
		return _pct(sum(y[num_key] for y in both), sum(y[den_key] for y in both))

	yield_totals = dict(
		{k: flt(v, 2) for k, v in totals.items()},
		frozen_to_hash=ratio("hash_g", "frozen_g"),
		frozen_to_rosin=ratio("rosin_g", "frozen_g"),
		hash_to_rosin=ratio("rosin_g", "hash_g"),
	)

	return {
		"kpis": kpis,
		"trend": _trend(entries, lines),
		"inputs_by_group": _by_group(material_in),
		"outputs_by_group": _by_group(outs),
		"top_inputs": _by_item(material_in)[:15],
		"top_outputs": _by_item(outs)[:15],
		"hardware": _by_item(hardware),
		"hardware_into": _hardware_into(hardware, lines),
		"by_customer": _by_customer(entries, lines),
		"yields": yields[:200],
		"yield_totals": yield_totals,
		"recent": [
			{
				"name": e.name, "posting_date": str(e.posting_date), "customer": e.customer,
				"company": e.company, "reasons": e.reasons or "",
				"input_g": flt(sum(ln.grams for ln in lines_by_entry[e.name] if ln.side == "in" and ln.item_group != HARDWARE_GROUP), 2),
				"output_g": flt(sum(ln.grams for ln in lines_by_entry[e.name] if ln.side == "out"), 2),
				"hardware_units": flt(sum(ln.qty for ln in lines_by_entry[e.name] if ln.side == "in" and ln.item_group == HARDWARE_GROUP), 2),
			}
			for e in entries[:50]
		],
	}


def _pct(num, den):
	return flt(num / den * 100, 2) if den else None


def _entry_yield(entry, lines, rows):
	"""The sheet's yield line for one entry, or None when it moved no frozen, hash or rosin."""
	frozen = sum(ln.grams for ln in lines if ln.side == "in" and _is_frozen(ln.item_group))
	hash_out = sum(ln.grams for ln in lines if ln.side == "out" and ln.item_group == HASH_GROUP)
	hash_in = sum(ln.grams for ln in lines if ln.side == "in" and ln.item_group == HASH_GROUP)
	tiers = {"tier_1": 0.0, "tier_2": 0.0, "tier_3": 0.0}
	rosin = 0.0
	for ln in lines:
		if ln.side == "out" and ln.item_group in ROSIN_GROUPS:
			rosin += ln.grams
			if ln.item_group in TIER_GROUPS:
				tiers[TIER_GROUPS[ln.item_group]] += ln.grams

	# Yield fields typed on the floor are the better number when present.
	typed_frozen = sum(flt(r.total_frozen_grams) for r in rows)
	typed_hash = sum(flt(r.bh_total_grams) for r in rows)
	typed_rosin = sum(flt(r.rosin_total_grams) for r in rows)
	frozen = typed_frozen or frozen
	hash_g = typed_hash or hash_out or hash_in
	rosin = typed_rosin or rosin

	# Frozen that only moved to other frozen (SHO relabelled as BHO, say) was
	# not washed, so it has no yield to report.
	if not (hash_g or rosin):
		return None
	return {
		"name": entry.name,
		"posting_date": str(entry.posting_date),
		"customer": entry.customer,
		"frozen_g": flt(frozen, 2),
		"hash_g": flt(hash_g, 2),
		"rosin_g": flt(rosin, 2),
		# A side that never happened in this entry is "not measured", not 0%.
		"frozen_to_hash": _pct(hash_g, frozen) if hash_g else None,
		"frozen_to_rosin": _pct(rosin, frozen) if rosin else None,
		"hash_to_rosin": _pct(rosin, hash_g) if rosin else None,
		**{k: flt(v, 2) for k, v in tiers.items()},
	}


def _by_group(lines):
	acc = defaultdict(lambda: {"grams": 0.0, "units": 0.0, "lines": 0})
	for ln in lines:
		a = acc[ln.item_group]
		a["grams"] += ln.grams
		a["units"] += ln.units
		a["lines"] += 1
	out = [{"group": g, **{k: flt(v, 2) for k, v in a.items()}} for g, a in acc.items()]
	out.sort(key=lambda r: (-r["grams"], -r["units"]))
	return out


def _by_item(lines):
	acc = {}
	for ln in lines:
		a = acc.setdefault(ln.item_code, {
			"item_code": ln.item_code, "item_name": ln.item_name, "item_group": ln.item_group,
			"uom": ln.uom, "qty": 0.0, "grams": 0.0, "entries": set(),
		})
		a["qty"] += ln.qty
		a["grams"] += ln.grams
		a["entries"].add(ln.entry)
	out = []
	for a in acc.values():
		a["entries"] = len(a["entries"])
		a["qty"] = flt(a["qty"], 2)
		a["grams"] = flt(a["grams"], 2)
		out.append(a)
	out.sort(key=lambda r: (-r["grams"], -r["qty"]))
	return out


def _hardware_into(hardware, lines):
	"""What the hardware ended up as: finished goods made on the same rows."""
	hw_rows = {ln.row for ln in hardware}
	acc = {}
	for ln in lines:
		if ln.side != "out" or ln.row not in hw_rows:
			continue
		a = acc.setdefault(ln.item_code, {
			"item_code": ln.item_code, "item_name": ln.item_name, "item_group": ln.item_group,
			"uom": ln.uom, "qty": 0.0,
		})
		a["qty"] += ln.qty
	out = sorted(acc.values(), key=lambda r: -r["qty"])
	for a in out:
		a["qty"] = flt(a["qty"], 2)
	return out[:15]


def _by_customer(entries, lines):
	entry_customer = {e.name: e.customer or "(No customer)" for e in entries}
	acc = defaultdict(lambda: {"entries": set(), "input_g": 0.0, "output_g": 0.0, "hardware_units": 0.0})
	for e in entries:
		acc[entry_customer[e.name]]["entries"].add(e.name)
	for ln in lines:
		a = acc[entry_customer[ln.entry]]
		if ln.side == "out":
			a["output_g"] += ln.grams
		elif ln.item_group == HARDWARE_GROUP:
			a["hardware_units"] += ln.qty
		else:
			a["input_g"] += ln.grams
	out = [
		{"customer": c, "entries": len(a["entries"]), "input_g": flt(a["input_g"], 2),
		 "output_g": flt(a["output_g"], 2), "hardware_units": flt(a["hardware_units"], 2)}
		for c, a in acc.items()
	]
	out.sort(key=lambda r: (-r["input_g"], -r["entries"]))
	return out


def _trend(entries, lines):
	"""Grams in/out and hardware units per week, oldest first."""
	if not entries:
		return []
	week_of = {}
	for e in entries:
		d = getdate(e.posting_date)
		week_of[e.name] = str(frappe.utils.add_days(d, -d.weekday()))
	acc = defaultdict(lambda: {"entries": 0, "input_g": 0.0, "output_g": 0.0, "hardware_units": 0.0})
	for e in entries:
		acc[week_of[e.name]]["entries"] += 1
	for ln in lines:
		a = acc[week_of[ln.entry]]
		if ln.side == "out":
			a["output_g"] += ln.grams
		elif ln.item_group == HARDWARE_GROUP:
			a["hardware_units"] += ln.qty
		else:
			a["input_g"] += ln.grams
	return [{"week": w, **{k: flt(v, 2) for k, v in a.items()}} for w, a in sorted(acc.items())]
