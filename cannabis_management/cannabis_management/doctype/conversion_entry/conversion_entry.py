import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime
from frappe.utils.data import time_diff_in_seconds

VAPE_ITEM_GROUPS = {
	"0.5g O2 Vape",
	"0.5G Vapes (Packaged)",
	"1g Jarred Rosin",
	"1g O2 Vapes",
	"1G Vapes (Packaged)",
	"Packaged goods",
}

_RM_FIELDS = [
	("raw_material_1", "rm_1_item_group"),
	("raw_material_2", "rm_2_item_group"),
	("raw_material_3", "rm_3_item_group"),
	("raw_material_4", "rm_4_item_group"),
	("raw_material_5", "rm_5_item_group"),
	("raw_material_6", "rm_6_item_group"),
	("raw_material_7", "rm_7_item_group"),
]

_FG_FIELDS = [
	("finished_good_1", "fg_1_item_group"),
	("finished_good_2", "fg_2_item_group"),
	("finished_good_3", "fg_3_item_group"),
]


MICRON_SIZES = ("150u", "120u_73u", "45u")


class ConversionEntry(Document):
	def validate(self):
		self._populate_item_groups()
		self._validate_items()
		self._validate_item_groups()
		self._calculate_total_time()
		self._sync_micron_totals()

	def _sync_micron_totals(self):
		"""Total the micron grams per product, then the yields off those totals.

		One pass: a yield is only ever a ratio of bh_total_grams and
		rosin_total_grams against the frozen weight, so it is settled where
		those totals are settled rather than in a second sweep that could run
		against a stale number.

		Micron grams only count while their tick stands, so an untick clears
		the figure under it before it can reach a total.

		A zero denominator leaves the ratio at zero rather than throwing: a
		half-filled draft is normal while a run is still being recorded.
		"""
		factors = {}
		for row in (self.items or []):
			# Hash and rosin collected, by micron.
			for prefix, flag in (("bh", "is_bubble_hash"), ("rosin", "is_rosin")):
				on = row.get(flag)
				total = 0.0
				for size in MICRON_SIZES:
					grams_field = "%s_grams_%s" % (prefix, size)
					check_field = "%s_micron_%s" % (prefix, size)
					if not on or not row.get(check_field):
						row.set(check_field, 0 if not on else row.get(check_field))
						row.set(grams_field, 0)
						continue
					total += flt(row.get(grams_field))
				row.set("%s_total_grams" % prefix, flt(total, 2))

			# Frozen weight that went in, in grams -- every raw material, so a
			# multi-material row yields against all of what it consumed.
			frozen_grams = 0.0
			for n in range(1, 8):
				item_code = row.get("raw_material_%d" % n)
				qty = flt(row.get("qty_rm_%d" % n))
				grams = 0.0
				if item_code and qty:
					if item_code not in factors:
						factors[item_code] = grams_per_unit(
							frappe.db.get_value("Item", item_code, "stock_uom")
						)
					grams = qty * factors[item_code]
				row.set("qty_rm_%d_g" % n, flt(grams, 2))
				frozen_grams += grams

			hash_g = flt(row.get("bh_total_grams"))
			rosin_g = flt(row.get("rosin_total_grams"))

			row.set("total_frozen_grams", flt(frozen_grams, 2))
			row.set("frozen_to_hash_pct", flt(hash_g / frozen_grams * 100, 2) if frozen_grams else 0)
			row.set("hash_to_rosin_pct", flt(rosin_g / hash_g * 100, 2) if hash_g else 0)
			row.set("frozen_to_rosin_pct", flt(rosin_g / frozen_grams * 100, 2) if frozen_grams else 0)

	def before_submit(self):
		if self.timer_status == "Work In Progress":
			frappe.throw(
				_("The job timer is still running. Please pause or complete it before submitting.")
			)

	def _calculate_total_time(self):
		total = 0.0
		for r in (self.time_logs or []):
			mins = flt(r.time_in_mins)
			if not mins and r.from_time and r.to_time:
				diff = time_diff_in_seconds(r.to_time, r.from_time) / 60.0
				if diff > 0:
					r.time_in_mins = flt(diff, 4)
					mins = r.time_in_mins
			total += mins
		self.total_time_in_minutes = total

	# ── Timer ──────────────────────────────────────────────────────────────────

	def add_time_log(self, args):
		last_row = self.time_logs[-1] if self.time_logs else None

		# Close any open row (Pause / Complete)
		if last_row and args.get("complete_time"):
			for row in self.time_logs:
				if not row.to_time:
					row.to_time = get_datetime(args.get("complete_time"))
					if row.from_time:
						row.time_in_mins = flt(
							time_diff_in_seconds(row.to_time, row.from_time) / 60.0, 2
						)

		# Open a new row (Start / Resume)
		if args.get("start_time"):
			self.append("time_logs", {
				"from_time": get_datetime(args.get("start_time")),
				"employee":  args.get("employee") or "",
			})

		# Update status / timer tracking fields
		status = args.get("status")
		if status in ("Work In Progress", "Resume Job"):
			self.timer_status = "Work In Progress"
			self.started_time = get_datetime(args.get("start_time"))
			if status == "Work In Progress":
				self.current_time = 0
		elif status == "On Hold":
			self.timer_status = "On Hold"
			self.started_time = None
			if last_row:
				self.current_time = int(flt(time_diff_in_seconds(
					get_datetime(args.get("complete_time")), last_row.from_time
				)))
		elif status == "Complete":
			self.timer_status = ""
			self.started_time = None
			self.current_time = int(sum(
				flt(time_diff_in_seconds(r.to_time, r.from_time))
				for r in self.time_logs
				if r.from_time and r.to_time
			))

		self._calculate_total_time()
		self.save()

	# ── Validation ─────────────────────────────────────────────────────────────

	def _validate_items(self):
		for idx, row in enumerate(self.items, 1):
			if not row.raw_material_1 or flt(row.qty_rm_1) <= 0:
				frappe.throw(_("Row {0}: Raw Material 1 and its Qty are required.").format(idx))

			if not row.finished_good_1 or flt(row.qty_fg_1) <= 0:
				frappe.throw(_("Row {0}: Finished Good 1 and its Qty are required.").format(idx))

			if row.conversion_type in ["2 to 1", "2 to 2", "3 to 1", "3 to 2", "3 to 3", "4 to 1", "4 to 2", "4 to 3", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_2 or flt(row.qty_rm_2) <= 0:
					frappe.throw(_("Row {0}: Raw Material 2 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["3 to 1", "3 to 2", "3 to 3", "4 to 1", "4 to 2", "4 to 3", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_3 or flt(row.qty_rm_3) <= 0:
					frappe.throw(_("Row {0}: Raw Material 3 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["4 to 1", "4 to 2", "4 to 3", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_4 or flt(row.qty_rm_4) <= 0:
					frappe.throw(_("Row {0}: Raw Material 4 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_5 or flt(row.qty_rm_5) <= 0:
					frappe.throw(_("Row {0}: Raw Material 5 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["6 to 1", "7 to 1"]:
				if not row.raw_material_6 or flt(row.qty_rm_6) <= 0:
					frappe.throw(_("Row {0}: Raw Material 6 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type == "7 to 1":
				if not row.raw_material_7 or flt(row.qty_rm_7) <= 0:
					frappe.throw(_("Row {0}: Raw Material 7 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["1 to 2", "2 to 2", "1 to 3", "3 to 2", "3 to 3", "4 to 2", "4 to 3"]:
				if not row.finished_good_2 or flt(row.qty_fg_2) <= 0:
					frappe.throw(_("Row {0}: Finished Good 2 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["1 to 3", "3 to 3", "4 to 3"]:
				if not row.finished_good_3 or flt(row.qty_fg_3) <= 0:
					frappe.throw(_("Row {0}: Finished Good 3 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

	def _populate_item_groups(self):
		for row in self.items:
			for item_field, group_field in _RM_FIELDS + _FG_FIELDS:
				item = row.get(item_field)
				grp = frappe.db.get_value("Item", item, "item_group") if item else ""
				row.set(group_field, grp or "")

	def _validate_item_groups(self):
		for idx, row in enumerate(self.items, 1):
			fg_groups = [row.get(gf) for _, gf in _FG_FIELDS if row.get(gf)]
			if not any(g in VAPE_ITEM_GROUPS for g in fg_groups):
				continue

			has_hardware = any(
				row.get(gf) == "Hardware Inventory"
				for item_f, gf in _RM_FIELDS
				if row.get(item_f)
			)
			if not has_hardware:
				frappe.throw(
					_(
						"Row {0}: Finished Good belongs to a Vape / Rosin / Packaged Goods item group. "
						"At least one Raw Material must belong to <b>Hardware Inventory</b>."
					).format(idx)
				)

	# ── Submit ─────────────────────────────────────────────────────────────────

	def on_submit(self):
		self._create_repack_stock_entry()

	def _create_repack_stock_entry(self):
		cost_map = _ce_cost_map(self)
		n_rows   = len(self.items) or 1
		created  = []
		failed   = []

		for idx, row in enumerate(self.items, 1):
			try:
				se = self._build_se_for_row(row, cost_map, n_rows)
				if se is None:
					frappe.msgprint(_("Row {0}: No valid items found — Stock Entry skipped.").format(idx), alert=True)
					continue
				se.insert(ignore_permissions=True)
				created.append(f'<a href="/app/stock-entry/{se.name}">{se.name}</a>')
			except Exception:
				frappe.log_error(
					message=frappe.get_traceback(),
					title=_("Conversion Entry {0}: Row {1} — Stock Entry Failed").format(self.name, idx),
				)
				failed.append(idx)

		if created:
			frappe.msgprint(
				_("{0} draft Stock Entr{1} created: {2}").format(
					len(created), "ies" if len(created) != 1 else "y", ", ".join(created)
				),
				indicator="green",
			)
		if failed:
			frappe.msgprint(
				_("Stock Entry creation failed for row(s): {0}. Check the Error Log.").format(
					", ".join(str(i) for i in failed)
				),
				indicator="orange",
			)

	def _build_se_for_row(self, row, cost_map=None, n_ses=1):
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Repack"
		se.company = self.company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
		if self.posting_date:
			se.posting_date     = self.posting_date
			se.set_posting_time = 1
		se.custom_conversion_entry_reference = self.name
		if self.sales_order:
			se.custom_sales_order = self.sales_order

		has_items = False

		# ── Source (outgoing) items ───────────────────────────────────────────
		total_source_value = 0.0
		# Each Raw Material N carries its own Source Tag N (rm_N_tag); it maps to
		# the outgoing Stock Entry line's "tags" field, which is the Metric Tag
		# inventory dimension's source column on Stock Entry Detail.
		for item_code, qty, tag in [
			(row.raw_material_1, row.qty_rm_1, row.rm_1_tag),
			(row.raw_material_2, row.qty_rm_2, row.rm_2_tag),
			(row.raw_material_3, row.qty_rm_3, row.rm_3_tag),
			(row.raw_material_4, row.qty_rm_4, row.rm_4_tag),
			(row.raw_material_5, row.qty_rm_5, row.rm_5_tag),
			(row.raw_material_6, row.qty_rm_6, row.rm_6_tag),
			(row.raw_material_7, row.qty_rm_7, row.rm_7_tag),
		]:
			if item_code and flt(qty) > 0:
				val_rate = flt(frappe.db.get_value(
					"Bin", {"item_code": item_code, "warehouse": row.source_warehouse}, "valuation_rate"
				) or 0)
				total_source_value += val_rate * flt(qty)
				se_item = {
					"item_code": item_code, "qty": flt(qty),
					"s_warehouse": row.source_warehouse,
					"is_finished_item": 0, "allow_zero_valuation_rate": 1,
				}
				if tag:
					se_item["tags"] = tag
				se.append("items", se_item)
				has_items = True

		# ── Finished (incoming) items — distribute source value by qty ratio ──
		# Each Finished Good N carries its own Target Tag N (fg_N_tag); it maps to
		# the incoming line's "to_tags" field -- the dimension's target column.
		fg_pairs = [
			(row.finished_good_1, row.qty_fg_1, row.fg_1_tag),
			(row.finished_good_2, row.qty_fg_2, row.fg_2_tag),
			(row.finished_good_3, row.qty_fg_3, row.fg_3_tag),
		]
		total_fg_qty = sum(flt(qty) for _, qty, _tag in fg_pairs if qty and flt(qty) > 0)

		for item_code, qty, tag in fg_pairs:
			if item_code and flt(qty) > 0:
				qty = flt(qty)
				proportion   = qty / total_fg_qty if total_fg_qty else 0
				basic_amount = total_source_value * proportion
				basic_rate   = basic_amount / qty if qty else 0
				se_item = {
					"item_code": item_code, "qty": qty,
					"t_warehouse": row.target_warehouse, "is_finished_item": 1,
					"basic_rate": basic_rate, "basic_amount": basic_amount,
				}
				if tag:
					se_item["to_tags"] = tag
				se.append("items", se_item)
				has_items = True

		if cost_map:
			for expense_account, info in cost_map.items():
				if info["amount"] > 0:
					se.append("additional_costs", {
						"expense_account": expense_account,
						"description":     info["label"],
						"amount":          info["amount"] / n_ses,
					})

		return se if has_items else None


# ── Whitelisted API ────────────────────────────────────────────────────────────

CONVERSION_TARGET_WAREHOUSE  = "Conversion - MTM"
CONVERSION_COMPANY           = "Master Touch Manufacturing"
CONVERSION_DEFAULT_WAREHOUSE = "Master Touch Manufacturing Toll - MTM"


@frappe.whitelist()
def make_conversion_entry(source_name):
	"""Build a draft Conversion Entry from a Sales Order.

	For the "Master Touch Manufacturing" company, each SO line's shortage
	(ordered qty − qty available in the SO's Set Warehouse, or
	"Master Touch Manufacturing Toll - MTM" if none is set) becomes a Conversion
	Entry row: the SO item is set as Finished Good 1 with the missing qty, and
	the target warehouse is fixed to "Conversion - MTM". Lines that have enough
	stock are skipped. For any other company a blank Conversion Entry is returned
	(header only — no finished-good rows). The returned doc is unsaved — opened
	directly in the form for the user to fill in the rest before saving.
	"""
	so = frappe.get_doc("Sales Order", source_name)

	ce = frappe.new_doc("Conversion Entry")
	ce.company       = so.company
	ce.customer      = so.customer
	ce.sales_order   = so.name
	ce.posting_date  = frappe.utils.nowdate()

	# Pre-fill shortage rows for MTM only; other companies get a blank entry.
	if so.company != CONVERSION_COMPANY:
		return ce.as_dict()

	warehouse = so.set_warehouse or CONVERSION_DEFAULT_WAREHOUSE

	for so_item in so.items:
		required  = flt(so_item.stock_qty) or flt(so_item.qty)

		available = flt(frappe.db.get_value(
			"Bin",
			{"item_code": so_item.item_code, "warehouse": warehouse},
			"actual_qty",
		) or 0)

		shortage = required - available
		if shortage <= 0:
			continue

		ce.append("items", {
			"target_warehouse": CONVERSION_TARGET_WAREHOUSE,
			"source_warehouse": warehouse,
			"finished_good_1":  so_item.item_code,
			"qty_fg_1":         shortage,
		})

	if not ce.items:
		frappe.msgprint(
			_("All Sales Order items have sufficient stock in {0} — no Conversion Entry needed.").format(
				frappe.bold(warehouse)
			),
			indicator="green",
		)

	return ce.as_dict()



@frappe.whitelist()
def make_ce_time_log(args):
	if isinstance(args, str):
		args = json.loads(args)
	args = frappe._dict(args)
	doc = frappe.get_doc("Conversion Entry", args.conversion_entry)
	doc.add_time_log(args)


# ── Operating cost map ─────────────────────────────────────────────────────────

def _ce_cost_map(ce_doc):
	"""
	Break operating cost into per-component rows, each using the expense_account
	configured on the Operating Component for this company.
	Falls back to a single row on company.expenses_included_in_valuation if no
	component-account mappings exist.
	"""
	if not ce_doc.workstation or not flt(ce_doc.total_time_in_minutes):
		return {}

	company      = ce_doc.company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
	time_mins    = flt(ce_doc.total_time_in_minutes)
	cost_map     = {}

	components = frappe.get_all(
		"Workstation Operating Cost",
		filters={"parent": ce_doc.workstation, "parenttype": "Workstation"},
		fields=["operating_component", "operating_cost"],
	)

	for comp in components:
		if not comp.operating_component or not flt(comp.operating_cost):
			continue

		expense_account = frappe.db.get_value(
			"Operating Component Account",
			{"parent": comp.operating_component, "parenttype": "Operating Component", "company": company},
			"expense_account",
		)
		if not expense_account:
			continue

		amount = flt(comp.operating_cost) / 60.0 * time_mins
		if expense_account in cost_map:
			cost_map[expense_account]["amount"] += amount
		else:
			cost_map[expense_account] = {
				"amount": amount,
				"label":  f"{comp.operating_component} ({ce_doc.workstation})",
			}

	if not cost_map:
		# Fallback: lump sum on company default account
		hourly_rate = flt(frappe.db.get_value(
			"Workstation", ce_doc.workstation, "custom_total_operating_cost"
		))
		if not hourly_rate:
			return {}

		expense_account = frappe.db.get_value(
			"Company", company, "expenses_included_in_valuation"
		)
		if not expense_account:
			return {}

		cost_map[expense_account] = {
			"amount": hourly_rate / 60.0 * time_mins,
			"label":  f"Operating Cost ({ce_doc.workstation})",
		}

	return cost_map


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def raw_material_stock_query(doctype, txt, searchfield, start, page_len, filters):
	"""Raw Material picker, showing what is actually on hand in the row's Source
	Warehouse.

	Item sets show_title_field_in_link, so Frappe uses column 2 as the bold
	label and joins the rest into the grey line beneath it (see
	frappe.desk.search.build_for_autosuggest). Returning
	(name, item_name, qty_label) therefore reads as:

	    Trop Cherry Banana - 1g O2 Vapes
	    1-O200005, 1,797.00 g in Main Storage - MTM

	Results are ordered by quantity descending so the items that can actually
	be converted surface first; an item with no stock still appears, at 0, so a
	planned row can be entered before the stock lands.

	With no Source Warehouse chosen yet the field falls back to a plain item
	search — a quantity with no warehouse behind it would be a guess.
	"""
	warehouse = (filters or {}).get("warehouse")
	values = {
		"txt": f"%{txt}%",
		"start": start,
		"page_len": page_len,
		"warehouse": warehouse,
	}

	if warehouse:
		qty_column = (
			"concat(format(ifnull(b.actual_qty, 0), 2), ' ', ifnull(i.stock_uom, ''), "
			"' in ', %(warehouse)s)"
		)
		join = "left join `tabBin` b on b.item_code = i.name and b.warehouse = %(warehouse)s"
		order = "ifnull(b.actual_qty, 0) desc, i.name"
	else:
		qty_column = "''"
		join = ""
		order = "i.name"

	return frappe.db.sql(
		f"""
		select i.name, i.item_name, {qty_column} as stock_label
		from `tabItem` i
		{join}
		where i.disabled = 0
		  and ifnull(i.has_variants, 0) = 0
		  and i.is_stock_item = 1
		  and (i.name like %(txt)s or i.item_name like %(txt)s)
		order by {order}
		limit %(start)s, %(page_len)s
		""",  # nosemgrep
		values,
	)


@frappe.whitelist()
def grams_per_unit(uom):
	"""Grams in one `uom`, or 0 when there is no sensible conversion.

	The pullable items are stocked in LBS while the tolling floor works in
	grams, so the gram figure is shown everywhere a quantity is — but it is
	only ever a display: stock moves in the item's own UOM.
	"""
	if not uom:
		return 0.0
	if uom in ("Gram", "Gm", "g"):
		return 1.0
	return flt(frappe.db.get_value(
		"UOM Conversion Factor", {"from_uom": uom, "to_uom": "Gram"}, "value"
	))


@frappe.whitelist()
def get_project_items(project, warehouse, company=None):
	"""Items that went out to a project through a given warehouse.

	Reads the invoice lines rather than the ledger: both Sales Invoice Item and
	Purchase Invoice Item carry project and warehouse already, so the answer is
	"what was billed against this project, out of this warehouse" — which is
	what the person pulling materials into a conversion is actually asking.

	Quantities from both sides are summed per item, so an item that arrived on a
	purchase invoice and left on a sales invoice shows one line, not two.
	"""
	if not (project and warehouse):
		frappe.throw(_("Pick a Project and a Warehouse."))

	# A warehouse belongs to exactly one company, so take it from there rather
	# than from the caller. The caller used to pass the form's company, which on
	# a new Conversion Entry is always Master Touch Manufacturing and silently
	# hid every invoice raised by any other company.
	if not company:
		company = frappe.db.get_value("Warehouse", warehouse, "company")

	rows = []
	for parent_dt, child_dt in (("Sales Invoice", "Sales Invoice Item"),
	                            ("Purchase Invoice", "Purchase Invoice Item")):
		conds = ["p.docstatus = 1", "c.project = %(project)s", "c.warehouse = %(warehouse)s"]
		values = {"project": project, "warehouse": warehouse}
		if company:
			conds.append("p.company = %(company)s")
			values["company"] = company

		rows += frappe.db.sql(
			"""
			select c.item_code, i.item_name, i.stock_uom as uom, i.item_group,
			       sum(ifnull(c.qty, 0)) as qty, %(source)s as source
			from `tab{child}` c
			inner join `tab{parent}` p on p.name = c.parent
			left join `tabItem` i on i.name = c.item_code
			where {conds}
			group by c.item_code, i.item_name, i.stock_uom, i.item_group
			""".format(child=child_dt, parent=parent_dt, conds=" and ".join(conds)),
			dict(values, source=parent_dt), as_dict=True,
		)

	merged = {}
	for r in rows:
		row = merged.setdefault(r.item_code, {
			"item_code": r.item_code,
			"item_name": r.item_name or r.item_code,
			"uom": r.uom,
			"item_group": r.item_group,
			"qty": 0.0,
			"sources": set(),
		})
		row["qty"] += flt(r.qty)
		row["sources"].add(r.source)

	factors = {}
	out = []
	for row in merged.values():
		row["sources"] = ", ".join(sorted(row.pop("sources")))
		row["qty"] = flt(row["qty"], 3)
		uom = row.get("uom")
		if uom not in factors:
			factors[uom] = grams_per_unit(uom)
		row["grams"] = flt(row["qty"] * factors[uom], 2)
		out.append(row)

	out.sort(key=lambda r: (-r["qty"], r["item_code"]))
	return out
