"""Backend for the 'Manufacturing Process' page — a single-page trail view of
one Work Order and every document that hangs off it (BOM, Job Cards, Stock
Entries), plus quick-create helpers that reuse ERPNext's own mapped-doc logic
so items/warehouses come pre-filled exactly like the standard Work Order form.
"""
import json

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def save_material_request(payload):
	"""Create, or update an existing Draft, Manufacture-type Material Request
	from the popup form on the Manufacturing Process page — instead of the
	full Material Request doctype form.

	This only assembles the document — it deliberately does not duplicate any
	business logic. Submitting still runs the exact same
	`cannabis_management.doc_hooks.material_request.on_submit` hook (auto BOM
	creation) that a normal Desk save/submit would run, so the backend result
	is identical either way.
	"""
	if isinstance(payload, str):
		payload = json.loads(payload)

	name = payload.get("name")
	company = payload.get("company")
	project = payload.get("custom_project")
	items = payload.get("items") or []
	fg_rows = payload.get("custom_finished_goods") or []

	if not company:
		frappe.throw(_("Company is required."))
	if not project:
		frappe.throw(_("Project is required."))
	if not items:
		frappe.throw(_("At least one Raw Material item is required."))

	set_warehouse = payload.get("set_warehouse")
	transaction_date = payload.get("transaction_date") or frappe.utils.today()

	if name:
		mr = frappe.get_doc("Material Request", name)
		if mr.docstatus != 0:
			frappe.throw(_("Only Draft Material Requests can be edited from this popup."))
		mr.set("items", [])
		mr.set("custom_finished_goods", [])
	else:
		mr = frappe.new_doc("Material Request")
		mr.material_request_type = "Manufacture"

	mr.company = company
	mr.custom_project = project
	mr.custom_routing = payload.get("custom_routing")
	mr.set_warehouse = set_warehouse
	mr.transaction_date = transaction_date

	for row in items:
		item_code = row.get("item_code")
		if not item_code:
			continue
		stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
		mr.append("items", {
			"item_code": item_code,
			"qty": flt(row.get("qty")) or 1,
			"uom": stock_uom,
			"stock_uom": stock_uom,
			"conversion_factor": 1,
			"warehouse": row.get("warehouse") or set_warehouse,
			"schedule_date": transaction_date,
		})

	for row in fg_rows:
		if not row.get("operation"):
			continue
		mr.append("custom_finished_goods", {
			"item": row.get("item"),
			"operation": row.get("operation"),
			"expected_yield_": flt(row.get("expected_yield_")),
			"finished_qty_grams": flt(row.get("finished_qty_grams")),
			"finished_qty_pounds": flt(row.get("finished_qty_pounds")),
			"source_warehouse": row.get("source_warehouse"),
			"wip_warehouse": row.get("wip_warehouse"),
			"target_warehouse": row.get("target_warehouse"),
		})

	if name:
		mr.save()
	else:
		mr.insert()

	if payload.get("submit"):
		mr.submit()

	frappe.db.commit()
	return {"name": mr.name, "docstatus": mr.docstatus}


@frappe.whitelist()
def create_work_order(payload):
	"""Create (and optionally submit) a Work Order from the popup on the
	Manufacturing Process page, instead of the full Work Order doctype form.

	`get_items_and_operations_from_bom()` is the exact same Document method
	the standard Work Order form's JS calls when you pick a BOM — so the
	items/operations that land on the Work Order are identical either way.
	"""
	if isinstance(payload, str):
		payload = json.loads(payload)

	item = payload.get("production_item")
	if not item:
		frappe.throw(_("Item to Manufacture is required."))

	bom_no = payload.get("bom_no")
	if not bom_no:
		bom_no = frappe.db.get_value(
			"BOM", {"item": item, "is_active": 1, "is_default": 1, "docstatus": 1}, "name"
		)
	if not bom_no:
		frappe.throw(_("No default BOM found for {0}. Please select a BOM.").format(item))

	wo = frappe.new_doc("Work Order")
	wo.production_item = item
	wo.bom_no = bom_no
	wo.qty = flt(payload.get("qty")) or 1
	wo.company = payload.get("company") or frappe.defaults.get_user_default("Company")
	wo.source_warehouse = payload.get("source_warehouse")
	wo.wip_warehouse = payload.get("wip_warehouse")
	wo.fg_warehouse = payload.get("fg_warehouse")
	wo.get_items_and_operations_from_bom()
	wo.insert()

	if payload.get("submit"):
		wo.submit()

	frappe.db.commit()
	return {"name": wo.name, "docstatus": wo.docstatus}


@frappe.whitelist()
def get_job_card_operations(work_order):
	"""Pending operation rows for a Work Order, shaped exactly for the core
	`erpnext...work_order.make_job_card` whitelisted method — the same one
	the standard Work Order form's own "Create Job Card" button calls.
	"""
	wo = frappe.get_doc("Work Order", work_order)
	rows = []
	for d in wo.operations:
		pending_qty = flt(wo.qty) - flt(d.completed_qty)
		if pending_qty <= 0:
			continue
		rows.append({
			"name": d.name,
			"operation": d.operation,
			"workstation": d.workstation,
			"workstation_type": d.workstation_type,
			"bom": d.bom,
			"sequence_id": d.sequence_id,
			"batch_size": d.batch_size,
			"pending_qty": pending_qty,
			"qty": pending_qty,
		})
	return rows


@frappe.whitelist()
def get_work_order_options(txt=None, company=None):
	"""Recent/matching Work Orders for the picker + quick-pick chips."""
	filters = {}
	if company:
		filters["company"] = company
	or_filters = None
	if txt:
		or_filters = [
			["name", "like", f"%{txt}%"],
			["production_item", "like", f"%{txt}%"],
			["item_name", "like", f"%{txt}%"],
		]

	return frappe.get_all(
		"Work Order",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "production_item", "item_name", "status", "qty", "produced_qty", "company"],
		order_by="modified desc",
		limit_page_length=20,
	)


@frappe.whitelist()
def get_trail(work_order):
	"""Everything needed to render the single-page trail for one Work Order."""
	if not work_order or not frappe.db.exists("Work Order", work_order):
		return {}

	wo = frappe.get_doc("Work Order", work_order)

	data = {
		"work_order": {
			"name": wo.name,
			"status": wo.status,
			"docstatus": wo.docstatus,
			"production_item": wo.production_item,
			"item_name": wo.item_name,
			"image": wo.image,
			"qty": flt(wo.qty),
			"produced_qty": flt(wo.produced_qty),
			"material_transferred_for_manufacturing": flt(wo.material_transferred_for_manufacturing),
			"process_loss_qty": flt(wo.process_loss_qty),
			"stock_uom": wo.stock_uom,
			"company": wo.company,
			"bom_no": wo.bom_no,
			"sales_order": wo.sales_order,
			"production_plan": wo.production_plan,
			"material_request": wo.material_request,
			"project": wo.project,
			"planned_start_date": wo.planned_start_date,
			"planned_end_date": wo.planned_end_date,
			"actual_start_date": wo.actual_start_date,
			"actual_end_date": wo.actual_end_date,
			"expected_delivery_date": wo.expected_delivery_date,
			"wip_warehouse": wo.wip_warehouse,
			"fg_warehouse": wo.fg_warehouse,
			"source_warehouse": wo.source_warehouse,
			"scrap_warehouse": wo.scrap_warehouse,
			"skip_transfer": wo.skip_transfer,
			"transfer_material_against": wo.transfer_material_against,
		},
		"required_items": [
			{
				"item_code": d.item_code,
				"item_name": d.item_name,
				"source_warehouse": d.source_warehouse,
				"required_qty": flt(d.required_qty),
				"transferred_qty": flt(d.transferred_qty),
				"consumed_qty": flt(d.consumed_qty),
				"returned_qty": flt(d.returned_qty),
				"available_qty_at_source_warehouse": flt(d.available_qty_at_source_warehouse),
				"rate": flt(d.rate),
				"amount": flt(d.amount),
			}
			for d in wo.required_items
		],
		"operations": [
			{
				"operation": d.operation,
				"workstation": d.workstation,
				"status": d.status,
				"completed_qty": flt(d.completed_qty),
				"time_in_mins": flt(d.time_in_mins),
			}
			for d in wo.operations
		],
		"bom": None,
		"job_cards": [],
		"stock_entries": [],
	}

	if wo.bom_no and frappe.db.exists("BOM", wo.bom_no):
		data["bom"] = frappe.db.get_value(
			"BOM",
			wo.bom_no,
			["name", "item", "item_name", "quantity", "uom", "is_active", "is_default", "with_operations", "total_cost"],
			as_dict=True,
		)

	job_cards = frappe.get_all(
		"Job Card",
		filters={"work_order": work_order},
		fields=[
			"name", "operation", "workstation", "status", "for_quantity", "total_completed_qty",
			"total_time_in_mins", "posting_date", "actual_start_date", "actual_end_date", "docstatus",
		],
		order_by="creation asc",
	)
	if job_cards:
		employees_by_jc = {}
		for row in frappe.get_all(
			"Job Card Time Log",
			filters={"parent": ["in", [jc.name for jc in job_cards]]},
			fields=["parent", "employee"],
		):
			if row.employee:
				employees_by_jc.setdefault(row.parent, set()).add(row.employee)
		for jc in job_cards:
			jc["employees"] = sorted(employees_by_jc.get(jc.name, []))
	data["job_cards"] = job_cards

	stock_entries = frappe.get_all(
		"Stock Entry",
		filters={"work_order": work_order},
		fields=["name", "purpose", "stock_entry_type", "posting_date", "fg_completed_qty", "docstatus"],
		order_by="creation asc",
	)
	if stock_entries:
		item_counts = {
			row.parent: row.cnt
			for row in frappe.get_all(
				"Stock Entry Detail",
				filters={"parent": ["in", [se.name for se in stock_entries]]},
				fields=["parent", "count(name) as cnt"],
				group_by="parent",
			)
		}
		for se in stock_entries:
			se["item_count"] = item_counts.get(se.name, 0)
	data["stock_entries"] = stock_entries

	return data


@frappe.whitelist()
def get_material_request_options(txt=None, company=None):
	"""Recent/matching Manufacture-type Material Requests for the picker +
	quick-pick chips — the process now starts here, not at Work Order."""
	filters = {"material_request_type": "Manufacture"}
	if company:
		filters["company"] = company
	or_filters = None
	if txt:
		or_filters = [
			["name", "like", f"%{txt}%"],
			["custom_project", "like", f"%{txt}%"],
		]

	return frappe.get_all(
		"Material Request",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "company", "custom_project", "docstatus", "transaction_date"],
		order_by="modified desc",
		limit_page_length=20,
	)


@frappe.whitelist()
def get_mr_trail(material_request):
	"""Everything needed to render the single-page trail for one Material
	Request: the MR itself, the BOM(s) it produced, every Work Order raised
	against it (there can be more than one — one per BOM/Finished Good), and
	every Job Card / Stock Entry hanging off those Work Orders.
	"""
	if not material_request or not frappe.db.exists("Material Request", material_request):
		return {}

	mr = frappe.get_doc("Material Request", material_request)

	data = {
		"material_request": {
			"name": mr.name,
			"docstatus": mr.docstatus,
			"company": mr.company,
			"custom_project": mr.custom_project,
			"custom_routing": mr.custom_routing,
			"set_warehouse": mr.set_warehouse,
			"transaction_date": mr.transaction_date,
			"material_request_type": mr.material_request_type,
			"items": [
				{"item_code": d.item_code, "item_name": d.item_name, "qty": flt(d.qty), "warehouse": d.warehouse}
				for d in mr.items
			],
			"custom_finished_goods": [
				{
					"item": d.item,
					"operation": d.operation,
					"expected_yield_": flt(d.expected_yield_),
					"finished_qty_grams": flt(d.finished_qty_grams),
					"source_warehouse": d.get("source_warehouse"),
					"wip_warehouse": d.get("wip_warehouse"),
					"target_warehouse": d.get("target_warehouse"),
				}
				for d in mr.get("custom_finished_goods") or []
			],
		},
		"boms": [],
		"work_orders": [],
		"job_cards": [],
		"stock_entries": [],
	}

	data["boms"] = frappe.get_all(
		"BOM",
		filters={"custom_material_request": mr.name},
		fields=["name", "item", "item_name", "quantity", "uom", "docstatus", "is_active"],
		order_by="creation asc",
	)

	work_orders = frappe.get_all(
		"Work Order",
		filters={"material_request": mr.name},
		fields=[
			"name", "production_item", "item_name", "image", "status", "docstatus",
			"qty", "produced_qty", "material_transferred_for_manufacturing", "process_loss_qty",
			"stock_uom", "company", "bom_no", "sales_order", "production_plan", "project",
			"planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date",
			"wip_warehouse", "fg_warehouse", "source_warehouse",
		],
		order_by="creation asc",
	)
	for wo in work_orders:
		wo["qty"] = flt(wo["qty"])
		wo["produced_qty"] = flt(wo["produced_qty"])
		wo["material_transferred_for_manufacturing"] = flt(wo["material_transferred_for_manufacturing"])
		wo["process_loss_qty"] = flt(wo["process_loss_qty"])
	data["work_orders"] = work_orders

	wo_names = [wo["name"] for wo in work_orders]
	if not wo_names:
		return data

	job_cards = frappe.get_all(
		"Job Card",
		filters={"work_order": ["in", wo_names]},
		fields=[
			"name", "work_order", "operation", "workstation", "status", "for_quantity",
			"total_completed_qty", "total_time_in_mins", "posting_date",
			"actual_start_date", "actual_end_date", "docstatus",
		],
		order_by="creation asc",
	)
	if job_cards:
		employees_by_jc = {}
		for row in frappe.get_all(
			"Job Card Time Log",
			filters={"parent": ["in", [jc.name for jc in job_cards]]},
			fields=["parent", "employee"],
		):
			if row.employee:
				employees_by_jc.setdefault(row.parent, set()).add(row.employee)
		for jc in job_cards:
			jc["employees"] = sorted(employees_by_jc.get(jc.name, []))
	data["job_cards"] = job_cards

	stock_entries = frappe.get_all(
		"Stock Entry",
		filters={"work_order": ["in", wo_names]},
		fields=["name", "work_order", "purpose", "stock_entry_type", "posting_date", "fg_completed_qty", "docstatus"],
		order_by="creation asc",
	)
	if stock_entries:
		item_counts = {
			row.parent: row.cnt
			for row in frappe.get_all(
				"Stock Entry Detail",
				filters={"parent": ["in", [se.name for se in stock_entries]]},
				fields=["parent", "count(name) as cnt"],
				group_by="parent",
			)
		}
		for se in stock_entries:
			se["item_count"] = item_counts.get(se.name, 0)
	data["stock_entries"] = stock_entries

	return data
