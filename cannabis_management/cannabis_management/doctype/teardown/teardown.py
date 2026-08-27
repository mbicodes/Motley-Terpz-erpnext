# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Teardown — harvest cut, review and finalize (rewired to the Plant model).

Regular teardown harvests the plant: its accumulated cost is fully transferred
into the harvest and the plant becomes Harvested (cost reset to 0). Manicure
keeps the plant alive (stays Flowering) and moves only a percentage of its
accumulated cost. While a Teardown is in Preparing it claims each plant's
`open_teardown` (one open teardown per plant); finalizing clears the claim.
On submit a draft Repack Stock Entry receives the combined wet weight into the
Dry Room, and the linked Farm Production Batch rollup is refreshed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Teardown(Document):
	def validate(self):
		self._backfill_strains()
		self._reject_non_flowering()
		self._claim_open_teardown()

	def _backfill_strains(self):
		"""Show the strain per row for the review summary."""
		for row in self.get("teardown_tags") or []:
			if row.plant and not row.strain:
				row.strain = frappe.db.get_value("Plant", row.plant, "strain") or ""

	def _reject_non_flowering(self):
		"""A plant may only be torn down from the Flowering phase."""
		for row in self.get("teardown_tags") or []:
			if not row.plant:
				continue
			phase = frappe.db.get_value("Plant", row.plant, "growth_phase")
			if phase != "Flowering":
				frappe.throw(
					_("Row {0}: Plant {1} is '{2}', not Flowering — it cannot be torn down.").format(
						row.idx, frappe.bold(row.plant), phase or _("unset")
					)
				)

	def _claim_open_teardown(self):
		"""Enforce one open teardown per plant, and claim it while Preparing."""
		if self.docstatus != 0:
			return
		for row in self.get("teardown_tags") or []:
			if not row.plant:
				continue
			current = frappe.db.get_value("Plant", row.plant, "open_teardown")
			if current and current != self.name:
				frappe.throw(
					_("Plant {0} already has an open teardown ({1}).").format(
						frappe.bold(row.plant), current
					)
				)
			if current != self.name:
				frappe.db.set_value("Plant", row.plant, "open_teardown", self.name, update_modified=False)

	def on_submit(self):
		if not self.get("teardown_tags"):
			frappe.throw(_("Nothing to finalize — add plants first."))
		if not self.dry_room:
			frappe.throw(_("Set a Dry Room before finalizing."))
		if not self.output_item:
			frappe.throw(_("Set an Output Item before finalizing."))

		total_transferred = 0.0
		for row in self.teardown_tags:
			plant = frappe.get_doc("Plant", row.plant)

			if self.teardown_type == "Regular":
				transferred = flt(plant.accumulated_cost)
				plant.status = "Harvested"
				plant.accumulated_cost = 0
			else:  # Manicure — plant stays alive and Flowering
				pct = flt(row.cost_pct_transferred) / 100.0
				transferred = flt(plant.accumulated_cost) * pct
				plant.accumulated_cost = flt(plant.accumulated_cost) - transferred

			plant.harvested_weight = flt(plant.harvested_weight) + flt(row.weight)
			plant.open_teardown = None  # cleared on finalization
			plant.save(ignore_permissions=True)
			total_transferred += transferred

		# on_submit runs after the doc is written — persist header fields explicitly.
		self.db_set("total_cost_transferred", total_transferred)
		self.db_set("status", "Completed")

		self._create_repack_stock_entry()
		self._refresh_linked_harvest()

	def on_cancel(self):
		self.db_set("status", "Preparing")
		self._refresh_linked_harvest()

	def on_trash(self):
		# Release the open-teardown claim if a draft is deleted.
		for row in self.get("teardown_tags") or []:
			if row.plant and frappe.db.get_value("Plant", row.plant, "open_teardown") == self.name:
				frappe.db.set_value("Plant", row.plant, "open_teardown", None, update_modified=False)

	# ── stock / rollup ───────────────────────────────────────────────────────
	def _create_repack_stock_entry(self):
		"""Draft Repack SE receiving combined wet weight into the Dry Room.
		Left in draft — same pattern as elsewhere in this system."""
		total_weight = sum(flt(r.weight) for r in self.teardown_tags)
		if total_weight <= 0:
			return

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Repack"
		se.append("items", {
			"item_code": self.output_item,
			"qty": total_weight,
			"uom": self._repack_uom(),
			"t_warehouse": self.dry_room,
			"is_finished_item": 1,
		})
		se.flags.ignore_permissions = True
		try:
			se.insert(ignore_permissions=True, ignore_mandatory=True)
			frappe.msgprint(_("Draft Repack Stock Entry {0} created into {1}.").format(
				frappe.get_desk_link("Stock Entry", se.name), self.dry_room))
		except Exception:
			frappe.log_error(frappe.get_traceback(), "[farm] Teardown Repack SE creation failed")
			frappe.msgprint(
				_("Teardown finalized, but the draft Repack Stock Entry could not be "
				  "auto-created — create it manually into {0}.").format(self.dry_room),
				indicator="orange", alert=True)

	def _repack_uom(self):
		"""Use the output item's stock UOM for the Repack row (conversion factor 1)."""
		return frappe.db.get_value("Item", self.output_item, "stock_uom")

	def _refresh_linked_harvest(self):
		if self.linked_harvest and frappe.db.exists("Farm Production Batch", self.linked_harvest):
			frappe.get_doc("Farm Production Batch", self.linked_harvest).recalculate_rollups()


@frappe.whitelist()
def distribute_total_weight(teardown_json, strain, total_weight):
	"""Split one combined weight evenly across every Teardown Tag row of the given
	strain. Returns the per-row weight; the client applies it. Pure helper."""
	import json

	rows = json.loads(teardown_json) if isinstance(teardown_json, str) else teardown_json
	matching = [r for r in rows if (r.get("strain") or "") == strain]
	if not matching:
		frappe.throw(_("No Teardown rows found for strain {0}.").format(strain))
	return flt(total_weight) / len(matching)
