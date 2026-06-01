import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ConversionEntry(Document):
	def validate(self):
		self._validate_items()

	def _validate_items(self):
		"""Ensure required fields are filled based on conversion type."""
		for idx, row in enumerate(self.items, 1):
			# Raw Material 1 + Qty is always required
			if not row.raw_material_1 or flt(row.qty_rm_1) <= 0:
				frappe.throw(
					_("Row {0}: Raw Material 1 and its Qty are required.").format(idx)
				)

			# Finished Good 1 + Qty is always required
			if not row.finished_good_1 or flt(row.qty_fg_1) <= 0:
				frappe.throw(
					_("Row {0}: Finished Good 1 and its Qty are required.").format(idx)
				)

			# 2 to 1 requires RM 2
			if row.conversion_type in ["2 to 1", "3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_2 or flt(row.qty_rm_2) <= 0:
					frappe.throw(
						_("Row {0}: Raw Material 2 and its Qty are required for {1} conversion.").format(idx, row.conversion_type)
					)

			# 3 to 1 requires RM 3
			if row.conversion_type in ["3 to 1", "4 to 1", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_3 or flt(row.qty_rm_3) <= 0:
					frappe.throw(
						_("Row {0}: Raw Material 3 and its Qty are required for {1} conversion.").format(idx, row.conversion_type)
					)

			# 4 to 1 requires RM 4
			if row.conversion_type in ["4 to 1", "5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_4 or flt(row.qty_rm_4) <= 0:
					frappe.throw(
						_("Row {0}: Raw Material 4 and its Qty are required for {1} conversion.").format(idx, row.conversion_type)
					)

			# 5 to 1 requires RM 5
			if row.conversion_type in ["5 to 1", "6 to 1", "7 to 1"]:
				if not row.raw_material_5 or flt(row.qty_rm_5) <= 0:
					frappe.throw(
						_("Row {0}: Raw Material 5 and its Qty are required for {1} conversion.").format(idx, row.conversion_type)
					)

			# 6 to 1 requires RM 6
			if row.conversion_type in ["6 to 1", "7 to 1"]:
				if not row.raw_material_6 or flt(row.qty_rm_6) <= 0:
					frappe.throw(
						_("Row {0}: Raw Material 6 and its Qty are required for {1} conversion.").format(idx, row.conversion_type)
					)

			# 7 to 1 requires RM 7
			if row.conversion_type == "7 to 1":
				if not row.raw_material_7 or flt(row.qty_rm_7) <= 0:
					frappe.throw(
						_("Row {0}: Raw Material 7 and its Qty are required for {1} conversion.").format(idx, row.conversion_type)
					)

			# 1 to 2 requires FG 2
			if row.conversion_type == "1 to 2":
				if not row.finished_good_2 or flt(row.qty_fg_2) <= 0:
					frappe.throw(
						_("Row {0}: Finished Good 2 and its Qty are required for 1 to 2 conversion.").format(idx)
					)

	def on_submit(self):
		self._create_repack_stock_entry()

	def _create_repack_stock_entry(self):
		"""Create one draft Repack Stock Entry per row in the items table.

		Each row is handled independently so a failure on one row never
		prevents the remaining rows from being processed.
		"""
		created = []
		failed = []

		for idx, row in enumerate(self.items, 1):
			try:
				se = self._build_se_for_row(row)
				if se is None:
					frappe.msgprint(
						_("Row {0}: No valid items found — Stock Entry skipped.").format(idx),
						alert=True,
					)
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
					len(created),
					"ies" if len(created) != 1 else "y",
					", ".join(created),
				),
				indicator="green",
			)
		if failed:
			frappe.msgprint(
				_("Stock Entry creation failed for row(s): {0}. Check the Error Log for details.").format(
					", ".join(str(i) for i in failed)
				),
				indicator="orange",
			)

	def _build_se_for_row(self, row):
		"""Build (but do not insert) a Repack Stock Entry for a single items row."""
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Repack"
		se.company = self.company or "Motley Terpz"
		if self.posting_date:
			se.posting_date = self.posting_date
			se.set_posting_time = 1
		se.custom_conversion_entry_reference = self.name
		if self.sales_order:
			se.custom_sales_order = self.sales_order

		has_items = False

		rm_pairs = [
			(row.raw_material_1, row.qty_rm_1),
			(row.raw_material_2, row.qty_rm_2),
			(row.raw_material_3, row.qty_rm_3),
			(row.raw_material_4, row.qty_rm_4),
			(row.raw_material_5, row.qty_rm_5),
			(row.raw_material_6, row.qty_rm_6),
			(row.raw_material_7, row.qty_rm_7),
		]
		for item_code, qty in rm_pairs:
			if item_code and flt(qty) > 0:
				se.append("items", {
					"item_code": item_code,
					"qty": flt(qty),
					"s_warehouse": row.source_warehouse,
					"is_finished_item": 0,
					"allow_zero_valuation_rate": 1,
				})
				has_items = True

		fg_pairs = [
			(row.finished_good_1, row.qty_fg_1),
			(row.finished_good_2, row.qty_fg_2),
		]
		for item_code, qty in fg_pairs:
			if item_code and flt(qty) > 0:
				se.append("items", {
					"item_code": item_code,
					"qty": flt(qty),
					"t_warehouse": row.target_warehouse,
					"is_finished_item": 1,
				})
				has_items = True

		return se if has_items else None
