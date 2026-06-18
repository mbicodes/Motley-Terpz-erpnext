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
]


class ConversionEntry(Document):
	def validate(self):
		self._populate_item_groups()
		self._validate_items()
		self._validate_item_groups()
		self._calculate_total_time()

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

			if row.conversion_type in ["2 to 1", "2 to 2", "3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_2 or flt(row.qty_rm_2) <= 0:
					frappe.throw(_("Row {0}: Raw Material 2 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_3 or flt(row.qty_rm_3) <= 0:
					frappe.throw(_("Row {0}: Raw Material 3 and its Qty are required for {1} conversion.").format(idx, row.conversion_type))

			if row.conversion_type in ["4 to 1", "5 to 1", "6 to 1", "7 to 1"]:
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

			if row.conversion_type in ["1 to 2", "2 to 2"]:
				if not row.finished_good_2 or flt(row.qty_fg_2) <= 0:
					frappe.throw(_("Row {0}: Finished Good 2 and its Qty are required for 1 to 2 conversion.").format(idx))

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
		se.company = self.company or "Motley Terpz"
		if self.posting_date:
			se.posting_date     = self.posting_date
			se.set_posting_time = 1
		se.custom_conversion_entry_reference = self.name
		if self.sales_order:
			se.custom_sales_order = self.sales_order

		has_items = False

		# ── Source (outgoing) items ───────────────────────────────────────────
		total_source_value = 0.0
		for item_code, qty in [
			(row.raw_material_1, row.qty_rm_1), (row.raw_material_2, row.qty_rm_2),
			(row.raw_material_3, row.qty_rm_3), (row.raw_material_4, row.qty_rm_4),
			(row.raw_material_5, row.qty_rm_5), (row.raw_material_6, row.qty_rm_6),
			(row.raw_material_7, row.qty_rm_7),
		]:
			if item_code and flt(qty) > 0:
				val_rate = flt(frappe.db.get_value(
					"Bin", {"item_code": item_code, "warehouse": row.source_warehouse}, "valuation_rate"
				) or 0)
				total_source_value += val_rate * flt(qty)
				se.append("items", {
					"item_code": item_code, "qty": flt(qty),
					"s_warehouse": row.source_warehouse,
					"is_finished_item": 0, "allow_zero_valuation_rate": 1,
				})
				has_items = True

		# ── Finished (incoming) items — distribute source value by qty ratio ──
		fg_pairs = [(row.finished_good_1, row.qty_fg_1), (row.finished_good_2, row.qty_fg_2)]
		total_fg_qty = sum(flt(qty) for _, qty in fg_pairs if qty and flt(qty) > 0)

		for item_code, qty in fg_pairs:
			if item_code and flt(qty) > 0:
				qty = flt(qty)
				proportion   = qty / total_fg_qty if total_fg_qty else 0
				basic_amount = total_source_value * proportion
				basic_rate   = basic_amount / qty if qty else 0
				se.append("items", {
					"item_code": item_code, "qty": qty,
					"t_warehouse": row.target_warehouse, "is_finished_item": 1,
					"basic_rate": basic_rate, "basic_amount": basic_amount,
				})
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

	company      = ce_doc.company or "Motley Terpz"
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
