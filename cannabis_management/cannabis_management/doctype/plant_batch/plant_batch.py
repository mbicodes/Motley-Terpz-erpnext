import frappe
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, nowdate

from cannabis_management.cannabis_management.doctype.farm_production_batch.farm_production_batch import (
	update_linked_harvest,
)


class PlantBatch(Document):
	def validate(self):
		self.set_batch_name()
		self.keep_deleted_phase_rows()
		self.calculate_totals()

	def before_update_after_submit(self):
		self.keep_deleted_phase_rows()

	def on_submit(self):
		update_linked_harvest(self)

	def on_update_after_submit(self):
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

	def set_batch_name(self):
		if not self.batch_name and self.strain:
			self.batch_name = " ".join(str(p) for p in [self.strain, self.planting_date] if p)

	def keep_deleted_phase_rows(self):
		before = self.get_doc_before_save()
		if not before:
			return
		current = {r.name for r in (self.growth_phase_log or [])}
		for old in before.get("growth_phase_log") or []:
			if old.name not in current:
				row = old.as_dict(no_default_fields=True, no_nulls=True)
				row.pop("name", None)
				row["is_deleted"] = 1
				self.append("growth_phase_log", row)

	def calculate_totals(self):
		initial = cint(self.plant_count)

		self.plants_promoted = sum(
			cint(r.qty) for r in (self.growth_phase_log or []) if not r.is_deleted
		)
		self.plants_destroyed = sum(cint(r.qty_lost) for r in (self.loss_log or []))
		self.plants_packaged = sum(cint(r.qty) for r in (self.packaging_log or []))

		self.plants_live = max(
			0, initial - self.plants_promoted - self.plants_destroyed - self.plants_packaged
		)

		self.status = "Inactive" if (initial and self.plants_live == 0) else "Active"

		self.age_days = date_diff(nowdate(), self.planting_date) if self.planting_date else 0

		self.total_input_cost = sum(flt(r.cost) for r in (self.input_log or []))
