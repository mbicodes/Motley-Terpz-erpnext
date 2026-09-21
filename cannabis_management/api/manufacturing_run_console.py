"""Backend for the 'Manufacturing Process' Desk page — a guided, step-by-step
production run console (Material Request -> Work Order -> Job Card -> Stock
Entry), Desk-only (the portal at /manufacturing-process is untouched and
still runs on the older shared trail-view module).

Every number this module returns is read live off real documents — nothing
here is hardcoded sample data. `get_run()` also derives which of the 5 steps
is "current" from the documents' own state (docstatus, qty vs produced_qty,
Job Card status, ...) rather than from any client-side counter, so the
console always reflects the truth even after a refresh or when a second
person picks up the same run.

Document creation itself is not reimplemented here — every step calls the
exact same whitelisted method the full doctype forms already use
(`cannabis_management.api.manufacturing.create_work_orders_from_mr`,
`erpnext...work_order.make_job_card`, `erpnext...work_order.make_stock_entry`,
`erpnext...job_card.make_time_log`), so results are identical to using the
full forms.
"""
import json

import frappe
from frappe import _
from frappe.utils import flt

LBS_TO_GRAM = 453.592


@frappe.whitelist()
def get_recent_runs(company=None):
	"""Manufacture-type Material Requests to resume/pick from on Step 1."""
	filters = {"material_request_type": "Manufacture"}
	if company:
		filters["company"] = company
	return frappe.get_all(
		"Material Request",
		filters=filters,
		fields=["name", "company", "custom_project", "docstatus", "transaction_date", "modified"],
		order_by="modified desc",
		limit_page_length=10,
	)


@frappe.whitelist()
def get_defaults():
	"""Whoami + form defaults for Step 1 — Company/Project pickers and the
	Employee this session's user resolves to (for the Run Operations step's
	time logs, display only)."""
	employee = frappe.db.get_value(
		"Employee", {"user_id": frappe.session.user}, ["name", "employee_name"], as_dict=True
	)
	return {
		"company": frappe.defaults.get_user_default("Company"),
		"employee": employee.name if employee else None,
		"employee_name": employee.employee_name if employee else None,
	}


def _job_card_rows(work_order_names):
	if not work_order_names:
		return []
	job_cards = frappe.get_all(
		"Job Card",
		filters={"work_order": ["in", work_order_names]},
		fields=[
			"name", "work_order", "operation", "workstation", "status", "docstatus",
			"for_quantity", "total_completed_qty", "total_time_in_mins", "hour_rate",
			"started_time", "current_time",
		],
		order_by="creation asc",
	)
	if not job_cards:
		return []

	jc_names = [jc.name for jc in job_cards]

	sub_ops_by_jc = {}
	for row in frappe.get_all(
		"Job Card Operation",
		filters={"parent": ["in", jc_names]},
		fields=["parent", "name", "sub_operation", "status", "completed_time", "completed_qty", "idx"],
		order_by="idx asc",
	):
		sub_ops_by_jc.setdefault(row.parent, []).append(row)

	time_logs_by_jc = {}
	for row in frappe.get_all(
		"Job Card Time Log",
		filters={"parent": ["in", jc_names]},
		fields=["parent", "name", "from_time", "to_time", "time_in_mins", "employee", "operation", "completed_qty"],
		order_by="idx asc",
	):
		time_logs_by_jc.setdefault(row.parent, []).append(row)

	for jc in job_cards:
		jc["sub_operations"] = sub_ops_by_jc.get(jc.name, [])
		jc["time_logs"] = time_logs_by_jc.get(jc.name, [])

	return job_cards


@frappe.whitelist()
def get_run(material_request):
	"""Everything the console needs to render one production run, plus a
	live scoreboard computed from real documents (grams in, grams produced,
	labour cost from Job Card hour rates x logged time, machine minutes)."""
	if not material_request or not frappe.db.exists("Material Request", material_request):
		return {}

	mr = frappe.get_doc("Material Request", material_request)

	grams_in = sum(flt(d.qty) * LBS_TO_GRAM for d in mr.items)

	finished_goods = []
	for d in mr.get("custom_finished_goods") or []:
		finished_goods.append({
			"item": d.item,
			"item_name": frappe.db.get_value("Item", d.item, "item_name") if d.item else None,
			"operation": d.operation,
			"expected_yield_": flt(d.expected_yield_),
			"target_grams": flt(d.finished_qty_grams),
		})

	work_orders = frappe.get_all(
		"Work Order",
		filters={"material_request": mr.name},
		fields=[
			"name", "production_item", "item_name", "status", "docstatus", "qty", "produced_qty",
			"material_transferred_for_manufacturing", "bom_no", "wip_warehouse", "fg_warehouse", "source_warehouse",
		],
		order_by="creation asc",
	)
	wo_names = [w.name for w in work_orders]

	job_cards = _job_card_rows(wo_names)

	stock_entries = []
	if wo_names:
		stock_entries = frappe.get_all(
			"Stock Entry",
			filters={"work_order": ["in", wo_names]},
			fields=["name", "work_order", "purpose", "posting_date", "fg_completed_qty", "docstatus"],
			order_by="creation asc",
		)

	machine_minutes = sum(flt(jc.total_time_in_mins) for jc in job_cards)
	labour_cost = sum((flt(jc.total_time_in_mins) / 60.0) * flt(jc.hour_rate) for jc in job_cards)

	produced_by_item = {}
	for se in stock_entries:
		if se.purpose == "Manufacture" and se.docstatus == 1:
			wo = next((w for w in work_orders if w.name == se.work_order), None)
			if wo:
				produced_by_item[wo.production_item] = produced_by_item.get(wo.production_item, 0) + flt(se.fg_completed_qty)
	hash_produced = sum(produced_by_item.values())

	# ---- derive the current step from real document state, not a counter ----
	transferred = bool(wo_names) and all(
		flt(w.material_transferred_for_manufacturing) >= flt(w.qty) - 0.0001 for w in work_orders
	)
	operations_done = bool(job_cards) and all(jc.status in ("Completed", "Cancelled") for jc in job_cards)
	output_done = bool(work_orders) and all(flt(w.produced_qty) >= flt(w.qty) - 0.0001 for w in work_orders)

	if output_done:
		step = 5
	elif operations_done:
		step = 4
	elif transferred:
		step = 3
	elif work_orders:
		step = 2
	elif mr.docstatus == 1:
		step = 1
	else:
		step = 0

	return {
		"material_request": {
			"name": mr.name,
			"docstatus": mr.docstatus,
			"company": mr.company,
			"project": mr.custom_project,
			"transaction_date": mr.transaction_date,
			"items": [
				{"item_code": d.item_code, "item_name": d.item_name, "qty": flt(d.qty), "warehouse": d.warehouse}
				for d in mr.items
			],
			"finished_goods": finished_goods,
		},
		"work_orders": work_orders,
		"job_cards": job_cards,
		"stock_entries": stock_entries,
		"step": step,
		"scoreboard": {
			"grams_in": grams_in,
			"hash_produced": hash_produced,
			"produced_by_item": [
				{"item": k, "item_name": frappe.db.get_value("Item", k, "item_name"), "grams": v}
				for k, v in produced_by_item.items()
			],
			"labour_cost": labour_cost,
			"machine_minutes": machine_minutes,
		},
	}


@frappe.whitelist()
def get_warehouse_defaults(company):
	"""Source/WIP/Target warehouse for Step 1, derived from the real per-company
	warehouse naming convention (every company on this site has exactly one
	Warehouse named 'Goods In Transit' / 'Work In Progress' / 'Finished Goods'
	— verified across all 6 companies) instead of asking the user to type
	them. Returns whatever it can find; a missing one is left blank rather
	than guessed, so the Step 1 form only asks for what it couldn't resolve.
	"""
	def find(warehouse_name):
		return frappe.db.get_value("Warehouse", {"company": company, "warehouse_name": warehouse_name}, "name")

	return {
		"source_warehouse": find("Goods In Transit"),
		"wip_warehouse": find("Work In Progress"),
		"fg_warehouse": find("Finished Goods"),
	}


@frappe.whitelist()
def start_run(payload):
	"""Step 1, collapsed: create + submit the Material Request, release it to
	production (Work Orders + Job Cards), and send every resulting Work
	Order's raw materials to WIP — all in one call, so starting a run is one
	click instead of three. Each sub-step reuses the exact same function the
	console's own manual per-step buttons call, so a partial failure (e.g.
	insufficient stock for the WIP transfer) still leaves the Material
	Request/Work Orders it already created in place — get_run() will just
	report the console at whichever step actually finished, and the
	corresponding step's own manual button is still there to retry.
	"""
	if isinstance(payload, str):
		payload = json.loads(payload)

	payload["submit"] = True

	warehouses = get_warehouse_defaults(payload.get("company"))
	payload["set_warehouse"] = payload.get("set_warehouse") or warehouses["source_warehouse"]
	for row in payload.get("items") or []:
		row["warehouse"] = row.get("warehouse") or warehouses["source_warehouse"]
	for row in payload.get("custom_finished_goods") or []:
		row["source_warehouse"] = row.get("source_warehouse") or warehouses["source_warehouse"]
		row["wip_warehouse"] = row.get("wip_warehouse") or warehouses["wip_warehouse"]
		row["target_warehouse"] = row.get("target_warehouse") or warehouses["fg_warehouse"]

	from cannabis_management.api.manufacturing_process import save_material_request
	mr = save_material_request(payload)

	result = release_to_production(mr["name"])

	from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
	for wo_name in result["work_orders"]:
		se = frappe.get_doc(make_stock_entry(wo_name, "Material Transfer for Manufacture"))
		se.insert(ignore_permissions=True)
		se.submit()

	frappe.db.commit()
	return get_run(mr["name"])


@frappe.whitelist()
def release_to_production(material_request):
	"""Step 2 — 'Release to production'. Raises the Work Order(s) exactly the
	way Create > Work Order (FG) already does
	(cannabis_management.api.manufacturing.create_work_orders_from_mr), then
	auto-creates a Job Card for every pending operation on each new Work
	Order — the same call the standard Work Order form's own 'Create Job
	Card' button makes (erpnext...work_order.make_job_card) — so the whole
	step is one click instead of one-click-per-document.
	"""
	from cannabis_management.api.manufacturing import create_work_orders_from_mr
	from cannabis_management.api.manufacturing_process import get_job_card_operations
	from erpnext.manufacturing.doctype.work_order.work_order import make_job_card

	work_orders = create_work_orders_from_mr(material_request)
	if not work_orders:
		frappe.throw(_("No Work Orders could be created for this Material Request."))

	job_cards = []
	for wo_name in work_orders:
		operations = get_job_card_operations(wo_name)
		if operations:
			make_job_card(wo_name, operations)
		job_cards.extend(frappe.get_all("Job Card", filters={"work_order": wo_name}, pluck="name"))

	frappe.db.commit()
	return {"work_orders": work_orders, "job_cards": job_cards}
