# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Yield Dashboard — what every conversion actually returned, for Operations.

Yields are computed from the conversions themselves (Raw Material 1 in, Finished
Good 1 out, both normalised to grams) rather than from the micron fields on
Conversion Entry Item. Those fields exist and are read here when they are
filled, but they are new and currently empty on every row, so a dashboard built
on them alone would show nothing. The conversions are 264 entries deep.

The three named stages are the ratios Operations asked for:

    Frozen to Hash   Fresh Frozen -> Bubble Hash
    Hash to Rosin    Bubble Hash  -> Rosin
    Frozen to Rosin  Fresh Frozen -> Rosin, in one step

They are matched on item group, because that is what distinguishes a run in this
data: a single tolling job is a chain of entries, 60 lbs of frozen becoming 466 g
of hash in one entry and 300 g of rosin in the next, so there is no one row that
holds a whole frozen-to-rosin yield. Every other RM->FG pairing is still shown,
grouped by its own pair, so nothing is invisible just because it was not named.

A run whose output cannot be converted to grams (anything sold in Nos) is listed
with its quantities but no percentage -- a made-up denominator would be worse
than an empty cell.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.api.sheet_export import send_csv, send_xlsx
from cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry import (
	grams_per_unit,
)

PAGE_ROLES = ("Ops Manager", "Production Manager", "System Manager", "Accounts Manager")

# (stage key, label, RM group test, FG group test)
STAGES = (
	("frozen_hash", "Frozen to Hash",
	 lambda g: g.startswith("Fresh Frozen"), lambda g: g == "Bubble Hash"),
	("hash_rosin", "Hash to Rosin",
	 lambda g: g == "Bubble Hash", lambda g: "Rosin" in g),
	("frozen_rosin", "Frozen to Rosin",
	 lambda g: g.startswith("Fresh Frozen"), lambda g: "Rosin" in g),
)

# A pure extraction cannot return more than went in. Anything above this is a
# keying error, not a good day, and Operations wants it surfaced rather than
# averaged into the numbers.
IMPOSSIBLE_YIELD_PCT = 100.0


def _require_access():
	"""The Page's `roles` only gate the route; these methods are reachable over
	/api/method by any logged-in user, so the check is repeated here."""
	if not set(PAGE_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("You are not permitted to view the Yield Dashboard."), frappe.PermissionError)


def _stage_for(rm_group, fg_group):
	for key, label, rm_test, fg_test in STAGES:
		if rm_test(rm_group or "") and fg_test(fg_group or ""):
			return key, label
	return "other", "{0} to {1}".format(rm_group or "?", fg_group or "?")


def _runs(filters):
	"""One row per Conversion Entry Item, summed across every material it moved.

	Every Raw Material 1..7 counts toward the input and every Finished Good 1..3
	toward the output. Reading only Raw Material 1 would divide a 2-to-1 run by
	half its feedstock -- CONV-00225 puts in 10 g plus 20 g and takes out 100 g,
	which reads as 1000% if the second input is ignored. 473 rows here carry a
	second raw material, so this is the common case, not an edge one.

	The stage is still named after the Raw Material 1 -> Finished Good 1 pairing,
	because that is the headline transformation; the other materials are usually
	the same group being topped up.
	"""
	conds = ["ce.docstatus = 1", "ifnull(i.raw_material_1,'') != ''",
	         "ifnull(i.finished_good_1,'') != ''", "ifnull(i.qty_rm_1,0) > 0"]
	values = {}

	for key, clause in (("from_date", "ce.posting_date >= %(from_date)s"),
	                    ("to_date", "ce.posting_date <= %(to_date)s"),
	                    ("company", "ce.company = %(company)s"),
	                    ("project", "ce.project = %(project)s"),
	                    ("reasons", "ce.reasons = %(reasons)s")):
		if filters.get(key):
			conds.append(clause)
			values[key] = filters[key]

	rm_cols = ", ".join("i.raw_material_%d, i.qty_rm_%d" % (n, n) for n in range(1, 8))
	fg_cols = ", ".join("i.finished_good_%d, i.qty_fg_%d" % (n, n) for n in range(1, 4))

	rows = frappe.db.sql(
		"""
		select ce.name, ce.posting_date, ce.company, ce.project, ce.reasons,
		       ce.supplier, ce.customer, i.name as row_id,
		       i.conversion_type, i.source_warehouse,
		       i.bh_total_grams, i.rosin_total_grams, i.total_frozen_grams,
		       {rm_cols}, {fg_cols}
		from `tabConversion Entry Item` i
		inner join `tabConversion Entry` ce on ce.name = i.parent
		where {conds}
		order by ce.posting_date desc, ce.name desc
		""".format(rm_cols=rm_cols, fg_cols=fg_cols, conds=" and ".join(conds)),
		values, as_dict=True,
	)
	if not rows:
		return []

	codes = set()
	for r in rows:
		for n in range(1, 8):
			if r.get("raw_material_%d" % n):
				codes.add(r["raw_material_%d" % n])
		for n in range(1, 4):
			if r.get("finished_good_%d" % n):
				codes.add(r["finished_good_%d" % n])

	items = {
		i.name: i for i in frappe.get_all(
			"Item", filters={"name": ("in", list(codes))},
			fields=["name", "item_name", "stock_uom", "item_group"])
	}

	factors = {}

	def grams(uom, qty):
		if uom not in factors:
			factors[uom] = grams_per_unit(uom)
		return flt(qty) * factors[uom] if factors[uom] else 0.0

	def side(r, prefix, qty_prefix, count):
		"""(total grams, [names], primary item, any UOM that cannot convert)."""
		total, names, primary, unconvertible = 0.0, [], None, False
		for n in range(1, count + 1):
			code = r.get("%s_%d" % (prefix, n))
			qty = flt(r.get("%s_%d" % (qty_prefix, n)))
			if not code or qty <= 0:
				continue
			it = items.get(code) or frappe._dict(
				{"item_name": code, "stock_uom": "", "item_group": ""})
			if primary is None:
				primary = it
			names.append(it.item_name or code)
			g = grams(it.stock_uom, qty)
			if not g:
				unconvertible = True
			total += g
		return total, names, primary, unconvertible

	out = []
	for r in rows:
		in_g, rm_names, rm_primary, rm_bad = side(r, "raw_material", "qty_rm", 7)
		out_g, fg_names, fg_primary, fg_bad = side(r, "finished_good", "qty_fg", 3)
		if rm_primary is None or fg_primary is None:
			continue

		stage_key, stage_label = _stage_for(rm_primary.item_group, fg_primary.item_group)
		# A missing UOM conversion makes the ratio meaningless, not merely small,
		# so it is left blank rather than computed off a partial denominator.
		usable = in_g > 0 and out_g > 0 and not rm_bad and not fg_bad
		pct = flt(out_g / in_g * 100, 2) if usable else None

		out.append({
			"entry": r.name, "row_id": r.row_id, "posting_date": str(r.posting_date or ""),
			"company": r.company, "project": r.project or "", "reasons": r.reasons or "",
			"party": r.supplier or r.customer or "",
			"warehouse": r.source_warehouse or "",
			"conversion_type": r.conversion_type or "",
			"stage": stage_key, "stage_label": stage_label,
			"rm_name": " + ".join(rm_names), "rm_group": rm_primary.item_group or "",
			"rm_count": len(rm_names),
			"fg_name": " + ".join(fg_names), "fg_group": fg_primary.item_group or "",
			"fg_count": len(fg_names),
			"in_grams": flt(in_g, 2), "out_grams": flt(out_g, 2),
			"yield_pct": pct,
			"hash_grams": flt(r.bh_total_grams, 2),
			"rosin_grams": flt(r.rosin_total_grams, 2),
			"flag": "impossible" if (pct is not None and pct > IMPOSSIBLE_YIELD_PCT) else "",
		})
	return out


def _median(values):
	if not values:
		return None
	s = sorted(values)
	mid = len(s) // 2
	return s[mid] if len(s) % 2 else flt((s[mid - 1] + s[mid]) / 2, 2)


def _summarise(runs):
	"""Per-stage totals. The headline is weighted, not an average of averages.

	A mean of run percentages lets a 4 lb run count as much as a 60 lb one; the
	weighted figure (total out / total in) is the yield the month actually
	returned. Both are shown, because a gap between them is itself the signal.
	"""
	by = {}
	for r in runs:
		s = by.setdefault(r["stage"], {
			"stage": r["stage"], "label": r["stage_label"], "runs": 0,
			"in_grams": 0.0, "out_grams": 0.0, "pcts": [], "flagged": 0,
			"no_pct": 0,
		})
		s["runs"] += 1
		s["in_grams"] += r["in_grams"]
		s["out_grams"] += r["out_grams"]
		if r["flag"]:
			s["flagged"] += 1
		if r["yield_pct"] is None:
			s["no_pct"] += 1
		elif not r["flag"]:
			s["pcts"].append(r["yield_pct"])

	out = []
	for s in by.values():
		pcts = s.pop("pcts")
		s["weighted_pct"] = flt(s["out_grams"] / s["in_grams"] * 100, 2) if s["in_grams"] else None
		s["avg_pct"] = flt(sum(pcts) / len(pcts), 2) if pcts else None
		s["median_pct"] = _median(pcts)
		s["best_pct"] = max(pcts) if pcts else None
		s["worst_pct"] = min(pcts) if pcts else None
		s["in_grams"] = flt(s["in_grams"], 2)
		s["out_grams"] = flt(s["out_grams"], 2)
		out.append(s)

	named = [k for k, _l, _a, _b in STAGES]
	out.sort(key=lambda s: (named.index(s["stage"]) if s["stage"] in named else 99, -s["in_grams"]))
	return out


@frappe.whitelist()
def get_data(filters=None):
	_require_access()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	runs = _runs(filters)
	return {
		"runs": runs,
		"summary": _summarise(runs),
		"as_of": nowdate(),
		"companies": frappe.get_all("Company", pluck="name", order_by="name"),
		"stages": [{"key": k, "label": l} for k, l, _a, _b in STAGES],
	}


def _tables(filters):
	runs = _runs(filters)
	summary = _summarise(runs)

	s_rows = [["Stage", "Runs", "Input (g)", "Output (g)", "Weighted Yield %",
	           "Average %", "Median %", "Best %", "Worst %", "Flagged", "No % (UOM)"]]
	for s in summary:
		s_rows.append([s["label"], s["runs"], s["in_grams"], s["out_grams"],
		               s["weighted_pct"], s["avg_pct"], s["median_pct"],
		               s["best_pct"], s["worst_pct"], s["flagged"], s["no_pct"]])

	r_rows = [["Date", "Conversion Entry", "Stage", "Company", "Project", "Party",
	           "Conversion Type", "Raw Materials", "Inputs", "Input (g)",
	           "Finished Goods", "Outputs", "Output (g)", "Yield %", "Flag"]]
	for r in runs:
		r_rows.append([
			getdate(r["posting_date"]) if r["posting_date"] else None,
			r["entry"], r["stage_label"], r["company"], r["project"], r["party"],
			r["conversion_type"], r["rm_name"], r["rm_count"], r["in_grams"],
			r["fg_name"], r["fg_count"], r["out_grams"],
			r["yield_pct"], "Over 100% - check entry" if r["flag"] else "",
		])
	return s_rows, r_rows


@frappe.whitelist()
def export_xlsx(filters=None):
	_require_access()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	s_rows, r_rows = _tables(filters)
	send_xlsx(_("Yields {0}").format(nowdate()), [
		("By Stage", s_rows, [26, 8, 14, 14, 16, 12, 12, 10, 11, 10, 12]),
		("Runs", r_rows, [12, 18, 24, 24, 18, 24, 14, 38, 8, 12, 38, 8, 12, 10, 22]),
	])


@frappe.whitelist()
def export_csv(filters=None):
	_require_access()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	_s_rows, r_rows = _tables(filters)
	send_csv(_("Yields {0}").format(nowdate()), r_rows)
