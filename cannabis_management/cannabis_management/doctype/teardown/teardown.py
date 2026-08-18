# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Teardown — harvest cut, review and finalize (Sections 6, 7, 10).

Regular teardown harvests the plant: the tag's accumulated cost is fully
transferred into the harvest and the tag becomes Harvested (cost reset to 0).
Manicure keeps the plant alive (stays Flowering) and moves only a percentage of
its accumulated cost. On submit a draft Repack Stock Entry receives the combined
wet weight into the Dry Room, and the linked Farm Production Batch rollup is
refreshed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Teardown(Document):
	def validate(self):
		self._backfill_strains()
		self._reject_non_flowering()

	def _backfill_strains(self):
		"""Show the strain per row for the review summary."""
		for row in self.get("teardown_tags") or []:
			if row.metric_tag and not row.strain:
				item = frappe.db.get_value("Metric Tag", row.metric_tag, "item_code")
				row.strain = item or ""

	def _reject_non_flowering(self):
		"""A tag may only be torn down from the Flowering stage (Section 13)."""
		for row in self.get("teardown_tags") or []:
			if not row.metric_tag:
				continue
			stage = frappe.db.get_value("Metric Tag", row.metric_tag, "growth_stage")
			if stage != "Flowering":
				frappe.throw(
					_("Row {0}: Metric Tag {1} is '{2}', not Flowering — it cannot be torn down.").format(
						row.idx, frappe.bold(row.metric_tag), stage or _("unset")
					)
				)

	def on_submit(self):
		if not self.get("teardown_tags"):
			frappe.throw(_("Nothing to finalize — add tags first."))
		if not self.dry_room:
			frappe.throw(_("Set a Dry Room before finalizing."))
		if not self.output_item:
			frappe.throw(_("Set an Output Item before finalizing."))

		total_transferred = 0.0
		for row in self.teardown_tags:
			tag = frappe.get_doc("Metric Tag", row.metric_tag)

			if self.teardown_type == "Regular":
				transferred = flt(tag.accumulated_cost)
				tag.growth_stage = "Harvested"
				tag.accumulated_cost = 0
			else:  # Manicure — plant stays alive
				pct = flt(row.cost_pct_transferred) / 100.0
				transferred = flt(tag.accumulated_cost) * pct
				tag.accumulated_cost = flt(tag.accumulated_cost) - transferred
				# growth_stage stays Flowering

			tag.save(ignore_permissions=True)
			total_transferred += transferred

		# on_submit runs after the doc is already written, so persist the header
		# fields explicitly rather than relying on the in-memory assignment.
		self.db_set("total_cost_transferred", total_transferred)
		self.db_set("status", "Completed")

		self._create_repack_stock_entry()

		# Refresh source-batch counts (Regular harvests may inactivate a batch)
		# and the linked-harvest financial rollup.
		self._refresh_source_batches()
		self._refresh_linked_harvest()

	def on_cancel(self):
		self.db_set("status", "Preparing")
		self._refresh_linked_harvest()

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
			# Left in draft; the operator adds the consumed input row(s) before
			# submitting. A Repack draft with only the produced row can trip
			# ERPNext validation on some configs — don't let that block the
			# teardown finalize.
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
		"""Use the output item's stock UOM for the Repack row (conversion factor
		1, always valid). The Teardown's own weight_unit (g / lb) stays on this
		document as the recorded unit; the operator can re-express the draft SE
		if their process needs a different unit."""
		return frappe.db.get_value("Item", self.output_item, "stock_uom")

	def _refresh_source_batches(self):
		from cannabis_management.farm import _refresh_batch_counts
		batches = {
			frappe.db.get_value("Metric Tag", r.metric_tag, "source_batch")
			for r in self.teardown_tags
		}
		for batch in filter(None, batches):
			_refresh_batch_counts(frappe.get_doc("Batch", batch))

	def _refresh_linked_harvest(self):
		if self.linked_harvest and frappe.db.exists("Farm Production Batch", self.linked_harvest):
			frappe.get_doc("Farm Production Batch", self.linked_harvest).recalculate_rollups()


@frappe.whitelist()
def distribute_total_weight(teardown_json, strain, total_weight):
	"""Section 7 (Total Weights): split one combined weight evenly across every
	Teardown Tag row of the given strain. Returns the per-row weight; the client
	applies it. Pure helper — no DB writes."""
	import json
	rows = json.loads(teardown_json) if isinstance(teardown_json, str) else teardown_json
	matching = [r for r in rows if (r.get("strain") or "") == strain]
	if not matching:
		frappe.throw(_("No Teardown rows found for strain {0}.").format(strain))
	return flt(total_weight) / len(matching)
