# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

# Plant Batch Input Log only allows these three input types — map the wider
# Additive Template genetics set onto them.
INPUT_TYPE_MAP = {
	"Nutrient": "Nutrient",
	"Fertilizer": "Fertilizer",
	"Pesticide": "Pesticide",
	"Fungicide": "Pesticide",
	"Growth Regulator": "Nutrient",
	"Other": "Nutrient",
}


class AdditiveApplication(Document):
	def validate(self):
		if not self.additive_date:
			self.additive_date = nowdate()
		self.set_target_doctypes()
		self.validate_tables()
		self.calculate_costs()

	def before_submit(self):
		self.calculate_costs()

	def on_submit(self):
		self.create_material_issue()
		self.apply_cost_to_targets()

	def on_cancel(self):
		self.cancel_material_issue()

	# ── validation / compute ─────────────────────────────────────────────────
	def set_target_doctypes(self):
		"""Every target row is scoped to the chosen Applied To Type."""
		for row in self.targets or []:
			row.target_doctype = self.applied_to_type
			if row.target_doctype and row.target_name:
				title_field = frappe.get_meta(row.target_doctype).get_title_field()
				if title_field and title_field != "name":
					row.target_title = frappe.db.get_value(
						row.target_doctype, row.target_name, title_field
					) or row.target_name
				else:
					row.target_title = row.target_name

	def validate_tables(self):
		if not self.targets:
			frappe.throw(_("Add at least one Target."))
		if not self.additive_lines:
			frappe.throw(_("Add at least one Additive Line."))

	def calculate_costs(self):
		total = 0.0
		for line in self.additive_lines or []:
			rate = self.get_valuation_rate(line.item, line.source_warehouse, line.source_batch)
			line.amount = flt(line.qty_applied) * flt(rate)
			total += flt(line.amount)
		self.total_cost = total

	def get_valuation_rate(self, item, warehouse, batch=None):
		if not (item and warehouse):
			return 0.0
		rate = frappe.db.get_value(
			"Bin", {"item_code": item, "warehouse": warehouse}, "valuation_rate"
		)
		return flt(rate)

	# ── on submit actions ────────────────────────────────────────────────────
	def create_material_issue(self):
		company = frappe.db.get_value(
			"Warehouse", self.additive_lines[0].source_warehouse, "company"
		) if self.additive_lines else None
		if not company:
			frappe.throw(_("Could not resolve a Company from the source warehouse."))

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.purpose = "Material Issue"
		se.company = company
		se.posting_date = self.additive_date
		for line in self.additive_lines:
			stock_uom = frappe.db.get_value("Item", line.item, "stock_uom")
			se.append(
				"items",
				{
					"item_code": line.item,
					"qty": line.qty_applied,
					"uom": stock_uom,
					"s_warehouse": line.source_warehouse,
					"batch_no": line.source_batch,
				},
			)
		se.insert(ignore_permissions=True)
		se.submit()
		self.db_set("stock_entry", se.name)

	def cancel_material_issue(self):
		if self.stock_entry:
			se = frappe.get_doc("Stock Entry", self.stock_entry)
			if se.docstatus == 1:
				se.cancel()

	def apply_cost_to_targets(self):
		"""Split cost + quantity evenly across every target and attribute it —
		Plant Batches get a per-line Input Log row, Plants get accumulated_cost."""
		n = len(self.targets)
		if not n:
			return
		for t in self.targets:
			if not (t.target_doctype and t.target_name):
				continue
			if t.target_doctype == "Plant Batch":
				batch = frappe.get_doc("Plant Batch", t.target_name)
				for line in self.additive_lines:
					additive_type = frappe.db.get_value(
						"Additive Template", line.additive_template, "additive_type"
					)
					batch.append(
						"input_log",
						{
							"input_type": INPUT_TYPE_MAP.get(additive_type, "Nutrient"),
							"product_name": line.item,
							"quantity": flt(line.qty_applied) / n,
							"cost": flt(line.amount) / n,
							"date_applied": self.additive_date,
						},
					)
				batch.save(ignore_permissions=True)
			elif t.target_doctype == "Plant":
				plant = frappe.get_doc("Plant", t.target_name)
				plant.accumulated_cost = flt(plant.accumulated_cost) + flt(self.total_cost) / n
				plant.save(ignore_permissions=True)
