# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CloningBatch(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		total_mom_plants = sum(flt(row.cuttings_taken) for row in self.mom_plant_details or [])
		total_material_quantity = sum(flt(row.quantity) for row in self.material_details or [])
		total_material_cost = sum(flt(row.amount) for row in self.material_details or [])
		total_clone_quantity = sum(flt(row.quantity) for row in self.clone_details or [])

		self.total_mom_plants = total_mom_plants
		self.total_material_quantity = total_material_quantity
		self.total_material_cost = total_material_cost
		self.total_clone_quantity = total_clone_quantity
		self.total_quantity = total_clone_quantity

		# Labour and session cost
		self.total_labor_cost = flt(self.labour_hours) * flt(self.labour_rate)
		self.total_session_material_cost = total_material_cost
		self.total_clones_produced = int(total_clone_quantity)
		self.total_session_cost = flt(self.total_labor_cost) + flt(self.total_session_material_cost)
		self.cost_per_clone = (self.total_session_cost / self.total_clones_produced) if self.total_clones_produced else 0

	def on_submit(self):
		self._create_repack_stock_entry()

	def _create_repack_stock_entry(self):
		"""Create a draft Stock Entry for clone transfer using Clone Details."""
		if not self.source_warehouse or not self.target_warehouse:
			frappe.throw(_("Source Warehouse and Target Warehouse are required to create a Stock Entry."))

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Repack"
		se.company = "Motley Terpz"
		se.posting_date = self.session_date or frappe.utils.today()
		se.project = self.batchproject
		se.custom_cloning_batch_reference = self.name
		se.from_warehouse = self.source_warehouse
		se.to_warehouse = self.target_warehouse

		has_items = False
		for row in self.clone_details or []:
			qty = flt(row.quantity)
			if qty <= 0 or not row.clone_item:
				continue

			se.append("items", {
				"item_code": row.clone_item,
				"qty": qty,
				"s_warehouse": self.source_warehouse,
				"t_warehouse": self.target_warehouse,
				"is_finished_item": 0,
			})
			has_items = True

		if not has_items:
			frappe.throw(_("No valid clone details found to create Stock Entry."))

		# Add labour cost as an additional_costs row if present
		if flt(self.total_labor_cost) > 0:
			se.append("additional_costs", {
				"expense_account": frappe.db.get_value("Company", se.company, "default_expense_account"),
				"description": "Cloning Labour Cost",
				"amount": flt(self.total_labor_cost),
			})

		se.insert(ignore_permissions=True)
		# Link the created Stock Entry back to this Cloning Batch
		try:
			self.db_set("stock_entry", se.name)
		except Exception:
			# fallback to direct DB update if db_set fails during submit
			frappe.db.set_value(self.doctype, self.name, "stock_entry", se.name, update_modified=False)

		frappe.msgprint(
			_("Draft Stock Entry {0} created. Stock Entry linked to this Cloning Batch.").format(
				f'<a href="/app/stock-entry/{se.name}">{se.name}</a>'
			),
			alert=True,
		)