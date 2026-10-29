import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.api.sheet_export import send_csv, send_xlsx
from cannabis_management.cannabis_management.doctype.conversion_entry.conversion_entry import (
	grams_per_unit,
)

PAGE_ROLES = ("Ops Manager", "Production Manager", "System Manager", "Accounts Manager")

SOURCE_CONVERSION = "Conversion"
SOURCE_MANUFACTURING = "Manufacturing"

STAGES = (
	("frozen_hash", "Frozen to Hash",
	 lambda g: g.startswith("Fresh Frozen"), lambda g: g == "Bubble Hash"),
	("hash_rosin", "Hash to Rosin",
	 lambda g: g == "Bubble Hash", lambda g: "Rosin" in g),
	("frozen_rosin", "Frozen to Rosin",
	 lambda g: g.startswith("Fresh Frozen"), lambda g: "Rosin" in g),
)

IMPOSSIBLE_YIELD_PCT = 100.0


def _require_access():
	if not set(PAGE_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("You are not permitted to view the Yield Dashboard."), frappe.PermissionError)


def _stage_for(rm_group, fg_group):
	for key, label, rm_test, fg_test in STAGES:
		if rm_test(rm_group or "") and fg_test(fg_group or ""):
			return key, label
	return "other", "{0} to {1}".format(rm_group or "?", fg_group or "?")


class _Grams:
	def __init__(self):
		self._factors = {}

	def __call__(self, uom, qty):
		if uom not in self._factors:
			self._factors[uom] = grams_per_unit(uom)
		return flt(qty) * self._factors[uom] if self._factors[uom] else 0.0

	def known(self, uom):
		if uom not in self._factors:
			self._factors[uom] = grams_per_unit(uom)
		return bool(self._factors[uom])


def _item_map(codes):
	if not codes:
		return {}
	return {
		i.name: i for i in frappe.get_all(
			"Item", filters={"name": ("in", list(codes))},
			fields=["name", "item_name", "stock_uom", "item_group"])
	}


def _build_run(meta, inputs, outputs, grams):
	if not inputs or not outputs:
		return None

	in_lines, in_total, in_bad = [], 0.0, False
	for code, qty, uom, it in inputs:
		g = grams(uom, qty)
		if not g:
			in_bad = True
		in_total += g
		in_lines.append({
			"item_code": code, "item_name": (it.item_name or code),
			"item_group": it.item_group or "", "qty": flt(qty, 3),
			"uom": uom or "", "grams": flt(g, 2),
		})

	out_total, out_bad, out_names = 0.0, False, []
	for code, qty, uom, it in outputs:
		g = grams(uom, qty)
		if not g:
			out_bad = True
		out_total += g
		out_names.append(it.item_name or code)

	usable = in_total > 0 and out_total > 0 and not in_bad and not out_bad
	pct = flt(out_total / in_total * 100, 2) if usable else None

	for line in in_lines:
		line["share_pct"] = flt(line["grams"] / in_total * 100, 2) if in_total else None
		line["out_grams"] = flt(out_total * line["grams"] / in_total, 2) if in_total else 0.0
		line["yield_pct"] = (
			flt(line["out_grams"] / line["grams"] * 100, 2)
			if (usable and line["grams"]) else None
		)

	primary_in = inputs[0][3]
	primary_out = outputs[0][3]
	stage_key, stage_label = _stage_for(primary_in.item_group, primary_out.item_group)

	run = dict(meta)
	run.update({
		"stage": stage_key, "stage_label": stage_label,
		"rm_name": " + ".join(l["item_name"] for l in in_lines),
		"rm_group": primary_in.item_group or "", "rm_count": len(in_lines),
		"fg_name": " + ".join(out_names),
		"fg_group": primary_out.item_group or "", "fg_count": len(out_names),
		"in_grams": flt(in_total, 2), "out_grams": flt(out_total, 2),
		"yield_pct": pct,
		"materials": in_lines,
		"flag": "impossible" if (pct is not None and pct > IMPOSSIBLE_YIELD_PCT) else "",
	})
	return run


def _conversion_runs(filters, grams):
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
		       i.bh_total_grams, i.rosin_total_grams,
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
	items = _item_map(codes)
	blank = frappe._dict({"item_name": "", "stock_uom": "", "item_group": ""})

	out = []
	for r in rows:
		def side(prefix, qty_prefix, count):
			lines = []
			for n in range(1, count + 1):
				code = r.get("%s_%d" % (prefix, n))
				qty = flt(r.get("%s_%d" % (qty_prefix, n)))
				if code and qty > 0:
					it = items.get(code) or blank
					lines.append((code, qty, it.stock_uom, it))
			return lines

		run = _build_run({
			"source": SOURCE_CONVERSION,
			"entry": r.name, "row_id": r.row_id,
			"posting_date": str(r.posting_date or ""),
			"company": r.company, "project": r.project or "",
			"reasons": r.reasons or "", "party": r.supplier or r.customer or "",
			"warehouse": r.source_warehouse or "",
			"run_type": r.conversion_type or "",
			"hash_grams": flt(r.bh_total_grams, 2),
			"rosin_grams": flt(r.rosin_total_grams, 2),
		}, side("raw_material", "qty_rm", 7), side("finished_good", "qty_fg", 3), grams)
		if run:
			out.append(run)
	return out


def _manufacturing_runs(filters, grams):
	conds = ["se.docstatus = 1", "se.purpose = 'Manufacture'"]
	values = {}
	for key, clause in (("from_date", "se.posting_date >= %(from_date)s"),
	                    ("to_date", "se.posting_date <= %(to_date)s"),
	                    ("company", "se.company = %(company)s"),
	                    ("project", "se.project = %(project)s")):
		if filters.get(key):
			conds.append(clause)
			values[key] = filters[key]

	rows = frappe.db.sql(
		"""
		select se.name, se.posting_date, se.company, se.project, se.work_order,
		       d.item_code, d.transfer_qty, d.stock_uom, d.s_warehouse, d.t_warehouse,
		       d.is_finished_item
		from `tabStock Entry` se
		inner join `tabStock Entry Detail` d on d.parent = se.name
		where {conds}
		order by se.posting_date desc, se.name desc, d.idx
		""".format(conds=" and ".join(conds)),
		values, as_dict=True,
	)
	if not rows:
		return []

	items = _item_map({r.item_code for r in rows})
	blank = frappe._dict({"item_name": "", "stock_uom": "", "item_group": ""})

	grouped = {}
	for r in rows:
		g = grouped.setdefault(r.name, {"meta": r, "in": [], "out": []})
		it = items.get(r.item_code) or blank
		line = (r.item_code, flt(r.transfer_qty), r.stock_uom, it)
		if r.is_finished_item:
			g["out"].append(line)
		elif r.s_warehouse and not r.t_warehouse:
			g["in"].append(line)

	out = []
	for name, g in grouped.items():
		m = g["meta"]
		run = _build_run({
			"source": SOURCE_MANUFACTURING,
			"entry": name, "row_id": name,
			"posting_date": str(m.posting_date or ""),
			"company": m.company, "project": m.project or "",
			"reasons": "", "party": m.work_order or "",
			"warehouse": "", "run_type": "Manufacture",
			"hash_grams": 0.0, "rosin_grams": 0.0,
		}, g["in"], g["out"], grams)
		if run:
			out.append(run)
	return out


def _runs(filters):
	grams = _Grams()
	source = filters.get("source") or ""
	runs = []
	if source != SOURCE_MANUFACTURING:
		runs += _conversion_runs(filters, grams)
	if source != SOURCE_CONVERSION:
		runs += _manufacturing_runs(filters, grams)
	runs.sort(key=lambda r: (r["posting_date"], r["entry"]), reverse=True)
	return runs


def _median(values):
	if not values:
		return None
	s = sorted(values)
	mid = len(s) // 2
	return s[mid] if len(s) % 2 else flt((s[mid - 1] + s[mid]) / 2, 2)


def _roll_up(buckets):
	out = []
	for b in buckets.values():
		pcts = b.pop("pcts")
		b["weighted_pct"] = flt(b["out_grams"] / b["in_grams"] * 100, 2) if b["in_grams"] else None
		b["avg_pct"] = flt(sum(pcts) / len(pcts), 2) if pcts else None
		b["median_pct"] = _median(pcts)
		b["best_pct"] = max(pcts) if pcts else None
		b["worst_pct"] = min(pcts) if pcts else None
		b["in_grams"] = flt(b["in_grams"], 2)
		b["out_grams"] = flt(b["out_grams"], 2)
		out.append(b)
	return out


def _summarise(runs):
	by = {}
	for r in runs:
		key = (r["source"], r["stage"])
		s = by.setdefault(key, {
			"stage": r["stage"], "label": r["stage_label"], "source": r["source"],
			"runs": 0, "in_grams": 0.0, "out_grams": 0.0, "pcts": [],
			"flagged": 0, "no_pct": 0,
		})
		s["runs"] += 1
		if r["flag"]:
			s["flagged"] += 1
			continue
		s["in_grams"] += r["in_grams"]
		s["out_grams"] += r["out_grams"]
		if r["yield_pct"] is None:
			s["no_pct"] += 1
		else:
			s["pcts"].append(r["yield_pct"])

	named = [k for k, _l, _a, _b in STAGES]
	out = _roll_up(by)
	out.sort(key=lambda s: (s["source"] != SOURCE_CONVERSION,
	                        named.index(s["stage"]) if s["stage"] in named else 99,
	                        -s["in_grams"]))
	return out


def _by_material(runs):
	by = {}
	for r in runs:
		if r["flag"]:
			continue
		for m in r["materials"]:
			b = by.setdefault(m["item_code"], {
				"item_code": m["item_code"], "label": m["item_name"],
				"item_group": m["item_group"], "runs": 0, "blended_runs": 0,
				"in_grams": 0.0, "out_grams": 0.0, "pcts": [], "flagged": 0,
				"no_pct": 0, "sources": set(),
			})
			b["runs"] += 1
			if r["rm_count"] > 1:
				b["blended_runs"] += 1
			b["sources"].add(r["source"])
			b["in_grams"] += m["grams"]
			b["out_grams"] += m["out_grams"]
			if m["yield_pct"] is None:
				b["no_pct"] += 1
			else:
				b["pcts"].append(m["yield_pct"])

	for b in by.values():
		b["sources"] = ", ".join(sorted(b["sources"]))
	out = _roll_up(by)
	out.sort(key=lambda b: -b["in_grams"])
	return out


@frappe.whitelist()
def get_data(filters=None):
	_require_access()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	runs = _runs(filters)
	return {
		"runs": runs,
		"summary": _summarise(runs),
		"materials": _by_material(runs),
		"as_of": nowdate(),
		"companies": frappe.get_all("Company", pluck="name", order_by="name"),
		"stages": [{"key": k, "label": l} for k, l, _a, _b in STAGES],
		"sources": [SOURCE_CONVERSION, SOURCE_MANUFACTURING],
	}


def _tables(filters):
	runs = _runs(filters)

	s_rows = [["Source", "Stage", "Runs", "Input (g)", "Output (g)", "Weighted Yield %",
	           "Average %", "Median %", "Best %", "Worst %", "Flagged", "No % (UOM)"]]
	for s in _summarise(runs):
		s_rows.append([s["source"], s["label"], s["runs"], s["in_grams"], s["out_grams"],
		               s["weighted_pct"], s["avg_pct"], s["median_pct"],
		               s["best_pct"], s["worst_pct"], s["flagged"], s["no_pct"]])

	m_rows = [["Raw Material", "Item Code", "Item Group", "Source", "Runs",
	           "Blended Runs", "Input (g)", "Output (g)", "Weighted Yield %",
	           "Average %", "Median %", "Best %", "Worst %"]]
	for m in _by_material(runs):
		m_rows.append([m["label"], m["item_code"], m["item_group"], m["sources"],
		               m["runs"], m["blended_runs"], m["in_grams"], m["out_grams"],
		               m["weighted_pct"], m["avg_pct"], m["median_pct"],
		               m["best_pct"], m["worst_pct"]])

	r_rows = [["Date", "Source", "Reference", "Stage", "Company", "Project", "Party",
	           "Type", "Raw Materials", "Inputs", "Input (g)",
	           "Finished Goods", "Outputs", "Output (g)", "Yield %", "Flag"]]
	d_rows = [["Date", "Source", "Reference", "Stage", "Raw Material", "Item Code",
	           "Item Group", "Qty", "UOM", "Input (g)", "Share of Input %",
	           "Output Credited (g)", "Yield %"]]
	for r in runs:
		date = getdate(r["posting_date"]) if r["posting_date"] else None
		r_rows.append([
			date, r["source"], r["entry"], r["stage_label"], r["company"],
			r["project"], r["party"], r["run_type"], r["rm_name"], r["rm_count"],
			r["in_grams"], r["fg_name"], r["fg_count"], r["out_grams"],
			r["yield_pct"], "Over 100% - check entry" if r["flag"] else "",
		])
		for m in r["materials"]:
			d_rows.append([
				date, r["source"], r["entry"], r["stage_label"], m["item_name"],
				m["item_code"], m["item_group"], m["qty"], m["uom"], m["grams"],
				m["share_pct"], m["out_grams"], m["yield_pct"],
			])
	return s_rows, m_rows, r_rows, d_rows


@frappe.whitelist()
def export_xlsx(filters=None):
	_require_access()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	s_rows, m_rows, r_rows, d_rows = _tables(filters)
	send_xlsx(_("Yields {0}").format(nowdate()), [
		("By Stage", s_rows, [14, 26, 8, 14, 14, 16, 12, 12, 10, 11, 10, 12]),
		("By Raw Material", m_rows, [34, 16, 22, 16, 8, 13, 14, 14, 16, 12, 12, 10, 11]),
		("Runs", r_rows, [12, 14, 20, 24, 24, 18, 22, 12, 38, 8, 12, 38, 8, 12, 10, 22]),
		("Run Materials", d_rows, [12, 14, 20, 24, 30, 16, 22, 10, 8, 12, 14, 18, 10]),
	])


@frappe.whitelist()
def export_csv(filters=None):
	_require_access()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	_s, _m, r_rows, _d = _tables(filters)
	send_csv(_("Yields {0}").format(nowdate()), r_rows)
