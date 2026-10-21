# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, nowdate

PROMOTE = "Promote Batch to Plants"
PHASE = "Change Plant Phase"

# Plant tags live in the metrc_customizations app. Promotion was switched off
# when the old in-app tag pool was removed; it now draws from there instead.
TAG_DOCTYPE = "Metrc Tag"
TAG_CATEGORY = "Plant"
TAG_AVAILABLE = "Available"
TAG_USED = "Used"


class GrowthPhaseChange(Document):
	def validate(self):
		if not self.change_date:
			self.change_date = nowdate()
		if self.change_type == PROMOTE:
			self.validate_promotion()
		elif self.change_type == PHASE:
			self.validate_phase_change()

	def on_submit(self):
		if self.change_type == PROMOTE:
			self.do_promotion()
		elif self.change_type == PHASE:
			self.do_phase_change()

	# ── promotion ────────────────────────────────────────────────────────────

	def validate_promotion(self):
		"""Check the batch and the tag run before anything is written.

		Everything here is re-checked at submit against live data: tags are a
		shared pool and a run that was free when the dialog opened may not be
		by the time it is sent.
		"""
		if not self.source_plant_batch:
			frappe.throw(_("Pick the Plant Batch being promoted."))
		if not self.output_location:
			frappe.throw(_("Output Location is required."))

		qty = cint(self.qty_to_promote)
		if qty <= 0:
			frappe.throw(_("Enter how many plants are changing phase."))

		available = self.plants_available()
		if qty > available:
			frappe.throw(_("{0} has {1} plants left; cannot promote {2}.")
			             .format(self.source_plant_batch, available, qty))

		tags = self.tag_run(qty)
		self.ending_plant_tag = tags[-1].tag_code if tags else None

	def plants_available(self):
		"""Plants still in the batch: started, less those already moved on."""
		b = frappe.db.get_value(
			"Plant Batch", self.source_plant_batch,
			["plant_count", "plants_promoted", "plants_destroyed", "plants_packaged"],
			as_dict=True) or {}
		return (cint(b.get("plant_count")) - cint(b.get("plants_promoted"))
		        - cint(b.get("plants_destroyed")) - cint(b.get("plants_packaged")))

	def tag_run(self, qty):
		"""`qty` consecutive available plant tags, starting at the chosen one.

		Consecutive in tag_code order, which is the order Metrc issues them.
		A gap -- a tag in the middle already used -- stops the run rather than
		silently skipping it, because a skipped tag means the physical sequence
		on the bench no longer matches what was recorded.
		"""
		if not self.starting_plant_tag:
			frappe.throw(_("Pick the Starting Plant Tag."))

		start_code = frappe.db.get_value(TAG_DOCTYPE, self.starting_plant_tag, "tag_code")
		if not start_code:
			frappe.throw(_("{0} has no tag code.").format(self.starting_plant_tag))

		run = frappe.get_all(
			TAG_DOCTYPE,
			filters={"tag_category": TAG_CATEGORY, "status": TAG_AVAILABLE,
			         "tag_code": (">=", start_code)},
			fields=["name", "tag_code"], order_by="tag_code asc", limit_page_length=qty)

		if len(run) < qty:
			frappe.throw(_("Only {0} available plant tags from {1}; {2} are needed.")
			             .format(len(run), start_code, qty))
		if run[0].tag_code != start_code:
			frappe.throw(_("{0} is not available.").format(start_code))
		return run

	def do_promotion(self):
		qty = cint(self.qty_to_promote)
		batch = frappe.get_doc("Plant Batch", self.source_plant_batch)
		tags = self.tag_run(qty)

		for tag in tags:
			plant = frappe.get_doc({
				"doctype": "Plant",
				"plant_tag": tag.tag_code,
				"source_plant_batch": batch.name,
				"strain": batch.strain,
				"licence": batch.licence,
				"location": self.output_location,
				"growth_phase": "Vegetative",
				"status": "Active",
			})
			# Plant.before_insert refuses anything without this: a plant may only
			# come from a promotion, never from someone opening a blank form.
			plant.flags.from_promotion = True
			plant.insert(ignore_permissions=True)

			# The tag is spent the moment it is on a plant.
			frappe.db.set_value(TAG_DOCTYPE, tag.name, "status", TAG_USED)

			self.append("plants", {
				"plant": plant.name,
				"plant_strain": batch.strain,
				"plant_phase": "Vegetative",
			})

		self.ending_plant_tag = tags[-1].tag_code
		self.db_set("ending_plant_tag", self.ending_plant_tag)
		# The child rows were added after insert, so they are written directly.
		for row in self.plants:
			row.db_insert() if not row.name else row.db_update()

		batch.plants_promoted = cint(batch.plants_promoted) + qty
		batch.append("growth_phase_log", {
			"change_date": self.change_date,
			"from_phase": "Immature",
			"to_phase": "Vegetative",
			"qty": qty,
			"note": self.name,
		})
		batch.save(ignore_permissions=True)

	# ── phase change (unchanged) ─────────────────────────────────────────────

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
