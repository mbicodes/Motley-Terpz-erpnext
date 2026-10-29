import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt

RECONCILE_EPSILON = 0.01


class HarvestBatch(Document):
	def validate(self):
		self.set_name_default()
		self.compute()

	def set_name_default(self):
		if not self.harvest_batch_name and self.strain:
			self.harvest_batch_name = " ".join(
				str(p) for p in [self.strain, self.harvest_date] if p
			)

	def compute(self):
		wet = flt(self.wet_weight)
		dry = flt(self.dry_weight)

		self.moisture_loss_pct = ((wet - dry) / wet * 100) if (dry and wet) else None

		self.unaccounted_weight = dry - flt(self.packaged_weight) - flt(self.waste_weight)

		self.yield_per_plant = (dry / cint(self.plant_count)) if cint(self.plant_count) else 0

		self.status = self._derive_status(dry)

	def _derive_status(self, dry):
		if not dry:
			return "Drying"
		if abs(flt(self.unaccounted_weight)) <= RECONCILE_EPSILON:
			return "Finished"
		if flt(self.packaged_weight) > 0:
			return "Partially Packaged"
		return "Dried"
