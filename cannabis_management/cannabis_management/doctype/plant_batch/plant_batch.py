# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, nowdate

from cannabis_management.cannabis_management.doctype.farm_production_batch.farm_production_batch import (
	update_linked_harvest,
)


class PlantBatch(Document):

	def validate(self):
		self.set_batch_name()
		self.calculate_totals()

	def on_submit(self):
		update_linked_harvest(self)

	def on_update_after_submit(self):
		# validate() does not run on a submitted-doc save, but events (promotions,
		# destructions, packaging) are logged after submit — recompute and persist.
		self.calculate_totals()
		frappe.db.set_value(
			self.doctype,
			self.name,
			{
				"plants_promoted": self.plants_promoted,
				"plants_destroyed": self.plants_destroyed,
				"plants_packaged": self.plants_packaged,
				"plants_live": self.plants_live,
				"age_days": self.age_days,
				"status": self.status,
				"total_input_cost": self.total_input_cost,
			},
			update_modified=False,
		)

	# ── helpers ──────────────────────────────────────────────────────────────
	def set_batch_name(self):
		"""Auto-suggest {strain} {planting_date} when left blank (editable)."""
		if not self.batch_name and self.strain:
			self.batch_name = " ".join(str(p) for p in [self.strain, self.planting_date] if p)

	def calculate_totals(self):
		"""Recompute the live plant inventory from the event logs."""
		initial = cint(self.plant_count)

		# --- Event sums ---
		self.plants_promoted = sum(cint(r.qty) for r in (self.growth_phase_log or []))
		self.plants_destroyed = sum(cint(r.qty_lost) for r in (self.loss_log or []))
		self.plants_packaged = sum(cint(r.qty) for r in (self.packaging_log or []))

		# --- Live count (never negative) ---
		self.plants_live = max(
			0, initial - self.plants_promoted - self.plants_destroyed - self.plants_packaged
		)

		# --- Status: Inactive once nothing is live (only after there were plants) ---
		self.status = "Inactive" if (initial and self.plants_live == 0) else "Active"

		# --- Age in days ---
		self.age_days = date_diff(nowdate(), self.planting_date) if self.planting_date else 0

		# --- Input / Additive cost ---
		self.total_input_cost = sum(flt(r.cost) for r in (self.input_log or []))
