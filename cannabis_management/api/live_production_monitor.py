import json

import frappe
from frappe.utils import getdate, nowdate


@frappe.whitelist()
def get_live_production_data(filters=None):
	if not frappe.has_permission("Job Card", "read"):
		frappe.throw(frappe._("Not permitted to read Job Card"), frappe.PermissionError)

	filters = frappe._dict(json.loads(filters) if isinstance(filters, str) else (filters or {}))
	today = nowdate()

	# Active job cards (Open / Work In Progress) always show regardless of the
	# date window — a live monitor's job is to surface what's running right now,
	# even if it was scheduled outside the selected range. The date filter still
	# bounds everything else (e.g. Completed history).
	conditions = [
		"jc.docstatus != 2",
		"(jc.status IN ('Open', 'Work In Progress') OR DATE(jc.expected_start_date) BETWEEN %(from_date)s AND %(to_date)s)",
	]
	params = {
		"from_date": filters.get("from_date") or today,
		"to_date": filters.get("to_date") or today,
	}

	if filters.get("status") and filters.status != "All Status":
		conditions.append("jc.status = %(status)s")
		params["status"] = filters.status
	if filters.get("work_order"):
		conditions.append("jc.work_order = %(work_order)s")
		params["work_order"] = filters.work_order
	if filters.get("job_card"):
		conditions.append("jc.name = %(job_card)s")
		params["job_card"] = filters.job_card
	if filters.get("company"):
		conditions.append("jc.company = %(company)s")
		params["company"] = filters.company
	if filters.get("workstation"):
		conditions.append("jc.workstation = %(workstation)s")
		params["workstation"] = filters.workstation
	if filters.get("operation"):
		conditions.append("jc.operation = %(operation)s")
		params["operation"] = filters.operation

	job_cards = frappe.db.sql(
		"""
		SELECT
			jc.name, jc.operation, jc.production_item, jc.item_name,
			jc.work_order, jc.workstation, jc.company, jc.status,
			jc.for_quantity, jc.total_completed_qty,
			jc.expected_start_date, jc.expected_end_date,
			jc.actual_start_date, jc.actual_end_date,
			jc.time_required, jc.total_time_in_mins, jc.modified
		FROM `tabJob Card` jc
		WHERE {conditions}
		ORDER BY jc.modified DESC
	""".format(conditions=" AND ".join(conditions)),
		params,
		as_dict=True,
	)

	total_active, wip, open_pending, completed_today = 0, 0, 0, 0
	work_orders = set()

	for jc in job_cards:
		if jc.status in ("Open", "Work In Progress"):
			total_active += 1
		if jc.status == "Work In Progress":
			wip += 1
		if jc.status == "Open":
			open_pending += 1
		if jc.status == "Completed" and jc.actual_end_date and getdate(jc.actual_end_date) == getdate(today):
			completed_today += 1
		if jc.work_order:
			work_orders.add(jc.work_order)

	kpis = {
		"total_active": total_active,
		"work_in_progress": wip,
		"open_pending": open_pending,
		"completed_today": completed_today,
		"total_work_order": len(work_orders),
		"total_job_card": len(job_cards),
	}

	operations = frappe.get_all("Job Card", filters={"operation": ["is", "set"]}, pluck="operation")
	workstations = frappe.get_all("Job Card", filters={"workstation": ["is", "set"]}, pluck="workstation")
	companies = frappe.get_all("Company", pluck="name")

	return {
		"job_cards": job_cards,
		"kpis": kpis,
		"filter_options": {
			"operations": sorted(set(operations)),
			"workstations": sorted(set(workstations)),
			"companies": sorted(set(companies)),
		},
	}
