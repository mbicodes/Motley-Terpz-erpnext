"""Backend for the 'Manufacturing Process' page — a single-page trail view of
one Work Order and every document that hangs off it (BOM, Job Cards, Stock
Entries), plus quick-create helpers that reuse ERPNext's own mapped-doc logic
so items/warehouses come pre-filled exactly like the standard Work Order form.
"""
import frappe
from frappe.utils import flt


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
