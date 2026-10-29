import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, nowdate


class Plant(Document):
	def before_insert(self):
		if not self.flags.from_promotion:
			frappe.throw(
				_("Plants are created only by promoting a Plant Batch (Growth Phase Change), not by hand.")
			)

	def validate(self):
		self.stamp_flowering()
		self.compute_ages()

	def stamp_flowering(self):
		if self.growth_phase == "Flowering":
			if not self.flowering_date:
				self.flowering_date = nowdate()
		else:
			self.flowering_date = None

	def compute_ages(self):
		self.days_in_flower = date_diff(nowdate(), self.flowering_date) if self.flowering_date else 0

		planting_date = (
			frappe.db.get_value("Plant Batch", self.source_plant_batch, "planting_date")
			if self.source_plant_batch
			else None
		)
		self.total_age_days = date_diff(nowdate(), planting_date) if planting_date else 0
