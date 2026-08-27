# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, nowdate

PROMOTE = "Promote Batch to Plants"
PHASE = "Change Plant Phase"


class GrowthPhaseChange(Document):
	def validate(self):
		if not self.change_date:
			self.change_date = nowdate()
		if self.change_type == PROMOTE:
			self.validate_promotion()
			self.compute_tag_range()
		elif self.change_type == PHASE:
			self.validate_phase_change()

	def before_submit(self):
		if self.change_type == PROMOTE and not self.tag_sequence_verified:
			frappe.throw(_("Tag Sequence Verified must be checked to submit a promotion."))

	def on_submit(self):
		if self.change_type == PROMOTE:
			self.do_promotion()
		elif self.change_type == PHASE:
			self.do_phase_change()

	# ── validation ───────────────────────────────────────────────────────────
	def validate_promotion(self):
		if not (self.source_plant_batch and self.qty_to_promote and self.tag_allocation):
			return  # mandatory_depends_on handles the reqd messaging

		qty = cint(self.qty_to_promote)
		if qty <= 0:
			frappe.throw(_("Qty to Promote must be greater than 0."))

		plants_live = cint(frappe.db.get_value("Plant Batch", self.source_plant_batch, "plants_live"))
		if plants_live <= 0:
			frappe.throw(_("Source batch {0} has no live plants to promote.").format(self.source_plant_batch))
		if qty > plants_live:
			frappe.throw(
				_("Qty to Promote ({0}) exceeds the source batch's live plants ({1}).").format(qty, plants_live)
			)

		batch_licence = frappe.db.get_value("Plant Batch", self.source_plant_batch, "licence")
		alloc = frappe.db.get_value(
			"METRC Tag Allocation", self.tag_allocation, ["tag_type", "status", "licence"], as_dict=True
		)
		if alloc.tag_type != "Plant":
			frappe.throw(_("Tag Allocation must have Tag Type = Plant."))
		if alloc.status != "Active":
			frappe.throw(_("Tag Allocation must be Active."))
		if batch_licence and alloc.licence and batch_licence != alloc.licence:
			frappe.throw(_("Tag Allocation licence must match the source batch licence."))

		available = self.get_available_tags()
		if len(available) < qty:
			frappe.throw(
				_("Tag Allocation has only {0} available tags, need {1}.").format(len(available), qty)
			)

	def validate_phase_change(self):
		if not self.target_phase:
			return
		if not self.plants:
			frappe.throw(_("Add at least one plant to change phase."))

	# ── tag helpers ──────────────────────────────────────────────────────────
	def get_available_tags(self):
		"""Ordered list of Available tag_ids in the chosen allocation."""
		if not self.tag_allocation:
			return []
		rows = frappe.get_all(
			"METRC Tag",
			filters={
				"parent": self.tag_allocation,
				"parenttype": "METRC Tag Allocation",
				"tag_status": "Available",
			},
			fields=["tag_id"],
			order_by="idx asc",
		)
		return [r.tag_id for r in rows]

	def compute_tag_range(self):
		tags = self.get_available_tags()
		qty = cint(self.qty_to_promote)
		self.starting_tag = tags[0] if tags else None
		if tags and qty and len(tags) >= qty:
			self.ending_tag = tags[qty - 1]
		else:
			self.ending_tag = tags[-1] if tags else None

	# ── on submit actions ────────────────────────────────────────────────────
	def do_promotion(self):
		qty = cint(self.qty_to_promote)
		alloc = frappe.get_doc("METRC Tag Allocation", self.tag_allocation)
		available_rows = [r for r in alloc.tags if r.tag_status == "Available"]
		if len(available_rows) < qty:
			frappe.throw(_("Only {0} available tags remain, need {1}.").format(len(available_rows), qty))

		chosen = available_rows[:qty]
		created = []
		for row in chosen:
			plant = frappe.get_doc(
				{
					"doctype": "Plant",
					"plant_tag": row.tag_id,
					"source_plant_batch": self.source_plant_batch,
					"location": self.output_location,
					"growth_phase": "Vegetative",
					"promoted_on": self.change_date,
				}
			)
			plant.flags.from_promotion = True
			plant.insert(ignore_permissions=True)
			created.append(plant.name)

			# reserve the tag against the new plant
			row.tag_status = "Assigned"
			row.assigned_to_doctype = "Plant"
			row.assigned_to_name = plant.name
			row.assigned_on = self.change_date

		# recompute allocation counters (Available / next_available_tag / status)
		alloc.save(ignore_permissions=True)

		# log the promotion on the source batch (feeds plants_promoted -> plants_live)
		batch = frappe.get_doc("Plant Batch", self.source_plant_batch)
		batch.append(
			"growth_phase_log",
			{
				"change_date": self.change_date,
				"from_phase": "Immature",
				"to_phase": "Vegetative",
				"qty": qty,
				"note": _("Promoted via {0}").format(self.name),
			},
		)
		batch.save(ignore_permissions=True)

		# record the created plants back on this document
		for i, name in enumerate(created, start=1):
			frappe.get_doc(
				{
					"doctype": "Growth Phase Change Plant",
					"parenttype": "Growth Phase Change",
					"parent": self.name,
					"parentfield": "plants",
					"idx": i,
					"plant": name,
				}
			).insert(ignore_permissions=True)

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
