import frappe
from frappe import _
from frappe.utils import cint, nowdate


@frappe.whitelist()
def get_list(filters=None):
	"""Rows for the Plant Batches list — existing 'Plant Batch' doctype only."""
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	filters = filters or {}

	batch_filters = {}
	for key in ("status", "strain", "location", "batch_type"):
		if filters.get(key):
			batch_filters[key] = filters[key]

	rows = frappe.get_list(
		"Plant Batch",
		filters=batch_filters,
		fields=[
			"name", "batch_name", "strain", "location", "room_row", "batch_type", "status",
			"plant_count", "plants_live", "plants_promoted", "plants_destroyed",
			"plants_packaged", "age_days", "planting_date", "total_input_cost",
			"source_type", "source_plant",
		],
		order_by="creation desc",
		limit_page_length=0,
	)

	return rows


@frappe.whitelist()
def create_plant_batches(data):
	"""'Create Plant Batch' dialog — one or more New Plant Batch rows sharing
	the same source/strain/type/location/date, mirroring the source video."""
	if isinstance(data, str):
		data = frappe.parse_json(data)

	rows = data.get("new_batches") or []
	if not rows:
		frappe.throw(_("Add at least one plant batch row."))

	# Each row carries its own source/strain/type/location/date (staged one by
	# one in the dialog); top-level values remain as a fallback.
	fields = ("strain", "batch_type", "planting_date", "location",
		"source_type", "source_plant")
	created = []
	for row in rows:
		doc = frappe.new_doc("Plant Batch")
		doc.batch_name = row.get("batch_name")
		doc.plant_count = cint(row.get("plant_count"))
		for f in fields:
			doc.set(f, row.get(f) or data.get(f))
		doc.insert()
		doc.submit()
		created.append(doc.name)

	return {"ok": True, "names": created}


@frappe.whitelist()
def move_plant_batch(plant_batch, location, move_date=None):
	"""'Move Plant Batch' — updates the existing location field directly and
	notes the move date on the document's existing comment timeline (no new
	doctype/field needed to record when the move happened)."""
	old_location = frappe.db.get_value("Plant Batch", plant_batch, "location")
	frappe.db.set_value("Plant Batch", plant_batch, "location", location)
	doc = frappe.get_doc("Plant Batch", plant_batch)
	doc.add_comment(
		"Info",
		_("Moved from {0} to {1} on {2}").format(
			old_location or "-", location, frappe.utils.formatdate(move_date or nowdate())
		),
	)
	return {"ok": True}


@frappe.whitelist()
def rename_plant_batch(plant_batch, batch_name):
	"""'Rename Plant Batch' — edits the batch_name field (autoname stays PB-####)."""
	frappe.db.set_value("Plant Batch", plant_batch, "batch_name", batch_name)
	return {"ok": True}


@frappe.whitelist()
def change_strain(plant_batch, strain):
	"""'Change Strain' action."""
	frappe.db.set_value("Plant Batch", plant_batch, "strain", strain)
	return {"ok": True}


@frappe.whitelist()
def package_plant_batch(plant_batch, qty, package_date=None, note=None):
	"""'Package Plant Batch' — appends to the existing packaging_log child
	table (allow_on_submit); calculate_totals() recomputes plants_packaged."""
	doc = frappe.get_doc("Plant Batch", plant_batch)
	doc.append("packaging_log", {
		"package_date": package_date or nowdate(),
		"qty": cint(qty),
		"note": note,
	})
	doc.save()
	return {"ok": True}


@frappe.whitelist()
def record_waste(plant_batch, qty_lost, reason=None, loss_date=None, logged_by=None):
	"""'Record Waste' — appends to the existing loss_log child table."""
	doc = frappe.get_doc("Plant Batch", plant_batch)
	doc.append("loss_log", {
		"loss_date": loss_date or nowdate(),
		"qty_lost": cint(qty_lost),
		"reason": reason or "Other",
		"logged_by": logged_by,
	})
	doc.save()
	return {"ok": True}


@frappe.whitelist()
def destroy_plant_batch(plant_batch, reason=None):
	"""'Destroy Plant Batch' — logs the full remaining live count as a loss."""
	doc = frappe.get_doc("Plant Batch", plant_batch)
	qty = cint(doc.plants_live)
	if qty <= 0:
		frappe.throw(_("This plant batch has no live plants left to destroy."))
	doc.append("loss_log", {
		"loss_date": nowdate(),
		"qty_lost": qty,
		"reason": reason or "Other",
	})
	doc.save()
	return {"ok": True}


@frappe.whitelist()
def record_additive(plant_batch, item, additive_template, qty_applied, uom, source_warehouse,
                     rate, volume, source_batch=None, additive_date=None):
	"""'Add Cost' / 'Record Additive' — creates + submits the existing
	'Additive Application' doctype targeted at this Plant Batch. Its own
	on_submit logic issues the stock entry and appends the Input Log /
	total_input_cost on the batch — reused as-is, not reimplemented."""
	doc = frappe.new_doc("Additive Application")
	doc.applied_to_type = "Plant Batch"
	doc.additive_date = additive_date or nowdate()
	doc.append("targets", {
		"target_doctype": "Plant Batch",
		"target_name": plant_batch,
	})
	doc.append("additive_lines", {
		"item": item,
		"additive_template": additive_template,
		"qty_applied": qty_applied,
		"uom": uom,
		"source_warehouse": source_warehouse,
		"source_batch": source_batch,
		"rate": rate,
		"volume": volume,
	})
	doc.insert()
	doc.submit()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def available_plant_tags(start_from=None, limit=50):
	"""Available plant tags in issue order, for the Starting Plant Tag picker."""
	filters = {"tag_category": "Plant", "status": "Available"}
	if start_from:
		filters["tag_code"] = (">=", start_from)
	return frappe.get_all("Metrc Tag", filters=filters,
	                      fields=["name", "tag_code"],
	                      order_by="tag_code asc", limit_page_length=cint(limit))


@frappe.whitelist()
def preview_tag_run(starting_tag, qty):
	"""The ending tag for a run, so the dialog can show it before submitting.

	Read-only: it allocates nothing. The same run is re-checked on submit,
	because tags are a shared pool and another promotion may take them first.
	"""
	qty = cint(qty)
	if not starting_tag or qty <= 0:
		return {"ending_tag": None, "count": 0}

	start_code = frappe.db.get_value("Metrc Tag", starting_tag, "tag_code")
	run = frappe.get_all(
		"Metrc Tag",
		filters={"tag_category": "Plant", "status": "Available",
		         "tag_code": (">=", start_code)},
		fields=["name", "tag_code"], order_by="tag_code asc", limit_page_length=qty)
	return {
		"starting_tag": start_code,
		"ending_tag": run[-1].tag_code if len(run) == qty else None,
		"count": len(run),
		"short_by": max(0, qty - len(run)),
	}


@frappe.whitelist()
def change_growth_phase(plant_batch, qty, output_location, starting_tag,
                        change_date=None):
	"""'Change Growth Phase' — promote immatures to tagged vegetative plants.

	The work itself lives on Growth Phase Change, so a promotion made from the
	Desk form behaves identically to one made from this page. Insert and submit
	run in one call: a half-made promotion would consume tags without plants.
	"""
	doc = frappe.get_doc({
		"doctype": "Growth Phase Change",
		"change_type": "Promote Batch to Plants",
		"change_date": change_date or nowdate(),
		"output_location": output_location,
		"source_plant_batch": plant_batch,
		"qty_to_promote": cint(qty),
		"starting_plant_tag": starting_tag,
	})
	doc.insert()
	doc.submit()
	return {
		"ok": True,
		"growth_phase_change": doc.name,
		"starting_tag": frappe.db.get_value("Metrc Tag", starting_tag, "tag_code"),
		"ending_tag": doc.ending_plant_tag,
		"plants_created": len(doc.plants),
	}
