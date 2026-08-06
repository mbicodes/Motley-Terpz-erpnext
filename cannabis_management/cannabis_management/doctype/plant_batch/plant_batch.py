# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt

from cannabis_management.cannabis_management.doctype.farm_production_batch.farm_production_batch import (
	update_linked_harvest,
)


class PlantBatch(Document):

	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		"""Auto-sum the Loss Log / Input Log child tables and refresh every
		Section 6 analytics field, same pattern as Cloning Batch's
		total_clones_taken / rooting_success_rate."""

		# --- Loss Log -> Plants Lost / Plants Harvested ---
		plants_lost = 0
		for row in self.loss_log or []:
			plants_lost += cint(row.qty_lost)

		self.plants_lost = plants_lost
		self.plants_harvested = cint(self.plant_count) - plants_lost

		# --- Input / Additive Log -> Total Input Cost ---
		total_input_cost = 0
		for row in self.input_log or []:
			total_input_cost += flt(row.cost)

		self.total_input_cost = total_input_cost

		# --- Moisture Loss % ---
		if flt(self.wet_weight) > 0:
			self.moisture_loss_pct = (
				(flt(self.wet_weight) - flt(self.dry_weight)) / flt(self.wet_weight) * 100
			)
		else:
			self.moisture_loss_pct = 0

		# --- Waste % ---
		if cint(self.plant_count) > 0:
			self.waste_pct = plants_lost / cint(self.plant_count) * 100
		else:
			self.waste_pct = 0

		# --- Days to Flower ---
		if self.date_transplanted and self.date_flowering_start:
			self.days_to_flower = date_diff(self.date_flowering_start, self.date_transplanted)
		else:
			self.days_to_flower = 0

		# --- Yield per Plant ---
		if self.plants_harvested and self.plants_harvested > 0:
			self.yield_per_plant = flt(self.dry_weight) / self.plants_harvested
		else:
			self.yield_per_plant = 0

	def on_submit(self):
		update_linked_harvest(self)
