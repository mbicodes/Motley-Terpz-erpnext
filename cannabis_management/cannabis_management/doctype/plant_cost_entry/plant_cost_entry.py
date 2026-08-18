# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Plant Cost Entry — applies an additive/nutrient/pesticide cost across a set
of plants. On submit, total_cost is split evenly across every Metric Tag in
Tags Covered and added to each tag's accumulated_cost (Section 5)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PlantCostEntry(Document):
	def validate(self):
		if not self.get("tags_covered"):
			frappe.throw(_("Add at least one tag under Tags Covered."))

	def on_submit(self):
		self._apply_cost(direction=1)

	def on_cancel(self):
		# Reverse the split so cancelling an entry doesn't leave phantom cost.
		self._apply_cost(direction=-1)

	def _apply_cost(self, direction):
		tags = [r.metric_tag for r in self.tags_covered if r.metric_tag]
		if not tags:
			return
		per_tag = flt(self.total_cost) / len(tags) * direction
		for tag_name in tags:
			current = flt(frappe.db.get_value("Metric Tag", tag_name, "accumulated_cost"))
			new_val = current + per_tag
			# guard against tiny negatives from float noise on cancel
			frappe.db.set_value("Metric Tag", tag_name, "accumulated_cost",
			                    new_val if abs(new_val) > 0.0001 else 0)
