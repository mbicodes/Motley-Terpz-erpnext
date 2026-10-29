import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class Teardown(Document):
	def validate(self):
		self._reject_non_flowering()
		self._claim_open_teardown()

	def _reject_non_flowering(self):
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
			else:
				pct = flt(row.cost_pct_transferred) / 100.0
				transferred = flt(plant.accumulated_cost) * pct
				plant.accumulated_cost = flt(plant.accumulated_cost) - transferred

			plant.harvested_weight = flt(plant.harvested_weight) + flt(row.weight)
			plant.open_teardown = None
			plant.save(ignore_permissions=True)
			total_transferred += transferred

		self.db_set("total_cost_transferred", total_transferred)
		self.db_set("status", "Completed")

		self._create_repack_stock_entry()
		self._refresh_linked_harvest()

	def on_cancel(self):
		self.db_set("status", "Preparing")
		self._refresh_linked_harvest()

	def on_trash(self):
		for row in self.get("teardown_tags") or []:
			if row.plant and frappe.db.get_value("Plant", row.plant, "open_teardown") == self.name:
				frappe.db.set_value("Plant", row.plant, "open_teardown", None, update_modified=False)

	def _create_repack_stock_entry(self):
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
		return frappe.db.get_value("Item", self.output_item, "stock_uom")

	def _refresh_linked_harvest(self):
		if self.linked_harvest and frappe.db.exists("Farm Production Batch", self.linked_harvest):
			frappe.get_doc("Farm Production Batch", self.linked_harvest).recalculate_rollups()


@frappe.whitelist()
def distribute_total_weight(teardown_json, strain, total_weight):
	import json

	rows = json.loads(teardown_json) if isinstance(teardown_json, str) else teardown_json
	matching = [r for r in rows if (r.get("strain") or "") == strain]
	if not matching:
		frappe.throw(_("No Teardown rows found for strain {0}.").format(strain))
	return flt(total_weight) / len(matching)
