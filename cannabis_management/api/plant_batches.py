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

	return frappe.get_list(
		"Plant Batch",
		filters=batch_filters,
		fields=[
			"name", "batch_name", "strain", "location", "room_row", "batch_type", "status",
			"plant_count", "plants_live", "plants_promoted", "plants_destroyed",
			"plants_packaged", "age_days", "planting_date", "total_input_cost",
			"source_type", "source_plant", "source_batch_no",
		],
		order_by="creation desc",
		limit_page_length=0,
	)


@frappe.whitelist()
def create_plant_batches(data):
	"""'Create Plant Batch' dialog — one or more New Plant Batch rows sharing
	the same source/strain/type/location/date, mirroring the source video."""
	if isinstance(data, str):
		data = frappe.parse_json(data)

	rows = data.get("new_batches") or []
	if not rows:
		frappe.throw(_("Add at least one plant batch row."))

	created = []
	for row in rows:
		doc = frappe.new_doc("Plant Batch")
		doc.batch_name = row.get("batch_name")
		doc.plant_count = cint(row.get("plant_count"))
		doc.strain = data.get("strain")
		doc.batch_type = data.get("batch_type")
		doc.planting_date = data.get("planting_date")
		doc.location = data.get("location")
		doc.source_type = data.get("source_type")
		doc.source_plant = data.get("source_plant")
		doc.source_batch_no = data.get("source_batch_no")
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
def package_plant_batch(plant_batch, qty, package_date=None, metrc_package_tag=None, note=None):
	"""'Package Plant Batch' — appends to the existing packaging_log child
	table (allow_on_submit); calculate_totals() recomputes plants_packaged."""
	doc = frappe.get_doc("Plant Batch", plant_batch)
	doc.append("packaging_log", {
		"package_date": package_date or nowdate(),
		"qty": cint(qty),
		"metrc_package_tag": metrc_package_tag,
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
def promote_growth_phase(plant_batch, tag_allocation, qty_to_promote, output_location, change_date=None):
	"""'Change Growth Phase' — creates + submits the existing 'Growth Phase
	Change' doctype (change_type = Promote Batch to Plants). Its own on_submit
	logic creates the Plant records and logs the promotion on this batch —
	nothing here duplicates that, it only drives the real doctype."""
	doc = frappe.new_doc("Growth Phase Change")
	doc.change_type = "Promote Batch to Plants"
	doc.source_plant_batch = plant_batch
	doc.qty_to_promote = cint(qty_to_promote)
	doc.tag_allocation = tag_allocation
	doc.output_location = output_location
	doc.change_date = change_date or nowdate()
	doc.tag_sequence_verified = 1
	doc.insert()
	doc.submit()
	return {"ok": True, "name": doc.name}


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
