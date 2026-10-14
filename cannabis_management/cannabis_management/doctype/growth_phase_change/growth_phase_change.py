# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

PROMOTE = "Promote Batch to Plants"
PHASE = "Change Plant Phase"


class GrowthPhaseChange(Document):
	def validate(self):
		if not self.change_date:
			self.change_date = nowdate()
		if self.change_type == PROMOTE:
			self.throw_promotion_unavailable()
		elif self.change_type == PHASE:
			self.validate_phase_change()

	def on_submit(self):
		if self.change_type == PROMOTE:
			self.throw_promotion_unavailable()
		elif self.change_type == PHASE:
			self.do_phase_change()

	def throw_promotion_unavailable(self):
		frappe.throw(_("Promoting a batch to Plants is unavailable: it relied on the tag pool, which has been removed."))

	def validate_phase_change(self):
		if not self.target_phase:
			return
		if not self.plants:
			frappe.throw(_("Add at least one plant to change phase."))

	def do_phase_change(self):
		for row in self.plants:
			if not row.plant:
				continue
			plant = frappe.get_doc("Plant", row.plant)
			if self.target_phase == "Flowering":
				plant.growth_phase = "Flowering"
			elif self.target_phase == "Mother":
				# a mother plant is a flag on a still-vegetative plant
				plant.is_mother = 1
				plant.growth_phase = "Vegetative"
			plant.save(ignore_permissions=True)
