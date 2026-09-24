"""Manufacturing Runs dashboard — every number here is a live query.

"Run" = one Job Card. There is no dedicated Run/Batch doctype in this app;
Job Card is the real per-operation-step execution unit (status has
Open/Work In Progress/.../Completed, matching the dashboard's 3-way split).
A single production batch (Project) can carry several Job Cards, one per
processing step — Job Card.operation is often itself a *sub*-operation
(e.g. "Bubble Sifting"), not always the top-level process family, so
"Processing Type" below resolves each Job Card's operation up to its family
(Hash Processing / Rosin Pressing / ...) via the Operation doctype's own
Sub Operation table, while "Main Operation" keeps the literal operation.
"""

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, get_fullname, add_days

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

GRAMS_PER_POUND = 453.592

# The sub-operation whose completion means the material has been washed.
WASH_SUB_OPERATION = "Wash Cycle"

# The two operations a run passes through. The second is "Rosin Pressing" --
# that is the Operation's real name, not "Rosin Processing".
HASH_OPERATION = "Hash Processing"
ROSIN_OPERATION = "Rosin Pressing"

# Micron sizes as stored on Micron Collection Detail, in report order.
MICRON_SIZES = ["150u", "120u - 73u", "45u"]

# Job Card statuses bucketed into the dashboard's 3-way split. Cancelled Job
# Cards are dropped everywhere below.
STATUS_BUCKETS = {
	"Open": "Open",
	"Completed": "Completed",
	"Work In Progress": "In Progress",
	"Material Transferred": "In Progress",
	"On Hold": "In Progress",
	"Submitted": "In Progress",
}

SUBOP_STATUS_BUCKETS = {
	"Complete": "Completed",
	"Work In Progress": "In Progress",
	"Pending": "Pending",
	"Pause": "Pending",
}

# Job Card.batch (really a Project link) is often left blank in practice, so
# every query that needs the Project falls back to the Job Card's own Work
# Order's project. `wo` is available wherever this FROM clause is used.
JC_FROM = "FROM `tabJob Card` jc LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order"

# Every non-cancelled Job Card of the outer query's run (wo.material_request),
# for filters that have to look at the whole run.
RUN_CARDS_FROM = "FROM `tabJob Card` r_jc INNER JOIN `tabWork Order` r_wo ON r_wo.name = r_jc.work_order"
RUN_CARDS_WHERE = "r_wo.material_request = wo.material_request AND r_jc.status != 'Cancelled'"


def _date_bounds(from_date=None, to_date=None):
	"""Resolve the active date range. A caller-supplied from_date/to_date is
	used verbatim (any custom range, not necessarily a week); with neither
	given, defaults to the current week (Monday-Sunday)."""
	if from_date and to_date:
		start, end = getdate(from_date), getdate(to_date)
		if start > end:
			start, end = end, start
		return start, end
	today = getdate()
	start = add_days(today, -today.weekday())
	end = add_days(start, 6)
	return start, end


def _operation_family_map():
	"""sub-operation name -> its parent (main) operation name. A main
	operation (one that owns rows in Sub Operation) maps to itself."""
	rows = frappe.db.sql(
		"SELECT parent AS main_op, operation AS sub_op FROM `tabSub Operation`", as_dict=True
	)
	family = {}
	for r in rows:
		family[r.sub_op] = r.main_op
		family.setdefault(r.main_op, r.main_op)
	return family


def _family_case_sql(family_map, column="jc.operation"):
	"""A SQL CASE expression that resolves `column` to its process family,
	built from the live sub-op -> main-op map (small, fixed set of real
	Operation names — safe to inline, never user input)."""
	if not family_map:
		return column
	whens = " ".join(
		f"WHEN {frappe.db.escape(sub_op)} THEN {frappe.db.escape(main_op)}"
		for sub_op, main_op in family_map.items()
	)
	return f"CASE {column} {whens} ELSE {column} END"


def _run_conditions(start, end, company=None, project=None, item=None, date_column=None):
	"""Shared WHERE conditions + params for any query that has `jc` (Job
	Card) and, via JC_FROM, `wo` (Work Order) available. `date_column`
	defaults to the Job Card's own effective start date; callers scoping by
	a different date (e.g. a time log's from_time) pass their own column."""
	date_column = date_column or "COALESCE(jc.actual_start_date, jc.creation)"
	conditions = [
		"jc.status != 'Cancelled'",
		f"DATE({date_column}) BETWEEN %(start)s AND %(end)s",
	]
	params = {"start": start, "end": end}
	if company:
		conditions.append("jc.company = %(company)s")
		params["company"] = company
	if project:
		conditions.append("COALESCE(jc.batch, wo.project) = %(project)s")
		params["project"] = project
	if item:
		conditions.append("jc.production_item = %(item)s")
		params["item"] = item
	return conditions, params


@frappe.whitelist()
def get_filter_options():
	"""Distinct real values for the Company/Project/Item filter dropdowns —
	always derived from what actually exists on Job Card, never hardcoded."""
	companies = frappe.db.sql(
		"SELECT DISTINCT company FROM `tabJob Card` WHERE company IS NOT NULL ORDER BY company",
		as_dict=True,
	)
	projects = frappe.db.sql(
		f"""
		SELECT DISTINCT COALESCE(jc.batch, wo.project) AS project
		{JC_FROM}
		WHERE COALESCE(jc.batch, wo.project) IS NOT NULL
		ORDER BY project
		""",
		as_dict=True,
	)
	items = frappe.db.sql(
		"SELECT DISTINCT production_item, item_name FROM `tabJob Card` "
		"WHERE production_item IS NOT NULL ORDER BY item_name",
		as_dict=True,
	)
	project_names = {}
	if projects:
		project_names = dict(
			frappe.db.sql(
				"SELECT name, project_name FROM `tabProject` WHERE name IN %(names)s",
				{"names": tuple(r.project for r in projects)},
			)
		)
	return {
		"companies": [r.company for r in companies],
		"projects": [
			{"value": r.project, "label": project_names.get(r.project) or r.project} for r in projects
		],
		"items": [{"value": r.production_item, "label": r.item_name or r.production_item} for r in items],
	}


@frappe.whitelist()
def get_dashboard_data(from_date=None, to_date=None, company=None, project=None, item=None):
	start, end = _date_bounds(from_date, to_date)
	period_days = (end - start).days + 1
	prev_start, prev_end = add_days(start, -period_days), add_days(start, -1)

	family_map = _operation_family_map()
	family_case = _family_case_sql(family_map)
	f = {"company": company, "project": project, "item": item}

	return {
		"from_date": str(start),
		"to_date": str(end),
		"stat_cards": _get_stat_cards(start, end, prev_start, prev_end, **f),
		"run_status_overview": _get_run_status_overview(start, end, **f),
		"processing_type": _get_processing_type_breakdown(start, end, family_case, **f),
		"operation_breakdown": _get_operation_breakdown(start, end, **f),
		"yield_by_type": _get_yield_by_type(start, end, family_case, **f),
		"suboperation_status": _get_suboperation_status(start, end, **f),
		"employee_hours": _get_employee_hours(start, end, **f),
		"started_vs_completed": _get_started_vs_completed(start, end, **f),
		"processing_types": sorted({v for v in family_map.values()}) or _distinct_operations(),
	}


def _distinct_operations():
	rows = frappe.db.sql(
		"SELECT DISTINCT operation FROM `tabJob Card` WHERE operation IS NOT NULL ORDER BY operation",
		as_dict=True,
	)
	return [r.operation for r in rows]


def _planned_runs_count(start, end, company=None):
	"""Material Requests raised in the window -- one per planned run.

	Counted on creation rather than transaction_date, because the ask is
	"new material requests created in the selected period".
	"""
	conditions = ["mr.docstatus < 2", "DATE(mr.creation) BETWEEN %(start)s AND %(end)s"]
	params = {"start": start, "end": end}
	if company:
		conditions.append("mr.company = %(company)s")
		params["company"] = company
	return cint(
		frappe.db.sql(
			f"SELECT COUNT(*) AS cnt FROM `tabMaterial Request` mr WHERE {' AND '.join(conditions)}",
			params,
			as_dict=True,
		)[0].cnt
	)


def _washed_totals(start, end, company=None, project=None, item=None):
	"""Job Cards whose Wash Cycle sub-operation is complete, and their output.

	Quantity is the Job Card's own total_completed_qty, reported in grams (as
	stored) and pounds. The inner GROUP BY keeps a Job Card counted once even
	if it carries more than one matching sub-operation row.
	"""
	conditions, params = _run_conditions(start, end, company, project, item)
	params["wash_op"] = WASH_SUB_OPERATION
	row = frappe.db.sql(
		f"""
		SELECT COUNT(*) AS cnt, COALESCE(SUM(qty), 0) AS grams
		FROM (
			SELECT jc.name, MAX(jc.total_completed_qty) AS qty
			{JC_FROM}
			INNER JOIN `tabJob Card Operation` jco
			        ON jco.parent = jc.name
			       AND jco.sub_operation = %(wash_op)s
			       AND jco.status = 'Complete'
			WHERE {' AND '.join(conditions)}
			GROUP BY jc.name
		) washed
		""",
		params,
		as_dict=True,
	)[0]
	grams = flt(row.grams)
	return {
		"count": cint(row.cnt),
		"grams": round(grams, 2),
		"pounds": round(grams / GRAMS_PER_POUND, 2),
	}


def _get_stat_cards(start, end, prev_start, prev_end, company=None, project=None, item=None):
	planned = _planned_runs_count(start, end, company)
	prev_planned = _planned_runs_count(prev_start, prev_end, company)
	washed = _washed_totals(start, end, company, project, item)

	def pct_change(cur, prev):
		if not prev:
			return None
		return round((cur - prev) / prev * 100, 2)

	return {
		"runs_planned": planned,
		"runs_planned_change_pct": pct_change(planned, prev_planned),
		"washed_count": washed["count"],
		"washed_grams": washed["grams"],
		"washed_pounds": washed["pounds"],
	}


def _get_run_status_overview(start, end, company=None, project=None, item=None):
	conditions, params = _run_conditions(start, end, company, project, item)
	rows = frappe.db.sql(
		f"SELECT jc.status, COUNT(*) AS cnt {JC_FROM} "
		f"WHERE {' AND '.join(conditions)} GROUP BY jc.status",
		params,
		as_dict=True,
	)
	buckets = {"Completed": 0, "Open": 0, "In Progress": 0}
	for r in rows:
		bucket = STATUS_BUCKETS.get(r.status)
		if bucket:
			buckets[bucket] += cint(r.cnt)
	return {"total": sum(buckets.values()), "buckets": buckets}


def _get_processing_type_breakdown(start, end, family_case, company=None, project=None, item=None):
	conditions, params = _run_conditions(start, end, company, project, item)
	conditions.append("jc.operation IS NOT NULL")
	rows = frappe.db.sql(
		f"SELECT {family_case} AS family, COUNT(*) AS cnt {JC_FROM} "
		f"WHERE {' AND '.join(conditions)} GROUP BY family ORDER BY cnt DESC",
		params,
		as_dict=True,
	)
	total = sum(cint(r.cnt) for r in rows)
	return {
		"total": total,
		"rows": [
			{
				"label": r.family,
				"count": cint(r.cnt),
				"pct": round(cint(r.cnt) / total * 100, 2) if total else 0,
			}
			for r in rows
		],
	}


def _get_operation_breakdown(start, end, company=None, project=None, item=None):
	"""Runs by Operation: the Processing Type donut one level down -- runs
	per sub-operation (Wash Cycle, Press Run, ...). Same source and window as
	Suboperation Status: a run counts once for each sub-operation its Job
	Card carries."""
	conditions, params = _run_conditions(start, end, company, project, item)
	conditions.append("IFNULL(jco.sub_operation, '') != ''")
	rows = frappe.db.sql(
		f"""
		SELECT jco.sub_operation AS label, COUNT(DISTINCT jc.name) AS cnt
		FROM `tabJob Card Operation` jco
		INNER JOIN `tabJob Card` jc ON jc.name = jco.parent
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {' AND '.join(conditions)}
		GROUP BY jco.sub_operation
		ORDER BY cnt DESC, label
		""",
		params,
		as_dict=True,
	)
	work = _employee_work_by_operation(start, end, company, project, item)

	# A run carries several sub-operations, so the slices add up to more than
	# the runs: the total is the runs themselves, each slice's % its share.
	slices = sum(cint(r.cnt) for r in rows)
	runs = cint(frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT jc.name)
		FROM `tabJob Card Operation` jco
		INNER JOIN `tabJob Card` jc ON jc.name = jco.parent
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {' AND '.join(conditions)}
		""",
		params,
	)[0][0])
	return {
		"total": runs,
		"employee_yield": _employee_yield(start, end, company, project, item),
		"rows": [
			{
				"label": r.label,
				"count": cint(r.cnt),
				"pct": round(cint(r.cnt) / slices * 100, 2) if slices else 0,
				"employees": work.get(r.label, []),
			}
			for r in rows
		],
	}


def _employee_work_by_operation(start, end, company=None, project=None, item=None):
	"""Who did how much on each sub-operation: time logged and runs worked.

	Read from Job Card Time Log, scoped by when the time was logged -- the
	same window Employee Hours uses. A cancelled Job Card (docstatus 2) keeps
	whatever status it had, so it is dropped by docstatus, not by status.
	"""
	conditions, params = _run_conditions(start, end, company, project, item, date_column="tl.from_time")
	conditions += ["jc.docstatus < 2", "IFNULL(tl.operation, '') != ''"]
	rows = frappe.db.sql(
		f"""
		SELECT
			tl.operation,
			COALESCE(NULLIF(emp.employee_name, ''), NULLIF(tl.employee, ''), 'Unassigned') AS employee,
			SUM(tl.time_in_mins) AS mins,
			COUNT(DISTINCT jc.name) AS runs
		FROM `tabJob Card Time Log` tl
		INNER JOIN `tabJob Card` jc ON jc.name = tl.parent
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		LEFT JOIN `tabEmployee` emp ON emp.name = tl.employee
		WHERE {' AND '.join(conditions)}
		GROUP BY tl.operation, employee
		ORDER BY tl.operation, mins DESC
		""",
		params,
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.operation, []).append(
			{"employee": r.employee, "mins": round(flt(r.mins), 2), "runs": cint(r.runs)}
		)
	return out


# The step whose worker a card's yield is credited to, per process.
YIELD_STEPS = ("Wash Cycle", "Press Run")


def _employee_yield(start, end, company=None, project=None, item=None):
	"""Yield per employee on Wash Cycle (Hash) and Press Run (Rosin).

	Each Job Card's yield -- total_completed_qty / for_quantity -- is credited
	to whoever logged time on that card's Wash Cycle / Press Run; two people
	on one card both get it. The average is over their cards, with the same
	formula and the same card set (Job Card start date, filters) as Yield by
	Processing Type, so it is that figure split by person.
	"""
	conditions, params = _run_conditions(start, end, company, project, item)
	params["steps"] = YIELD_STEPS
	rows = frappe.db.sql(
		f"""
		SELECT operation, employee,
		       COUNT(*) AS runs,
		       AVG(CASE WHEN for_qty > 0 THEN out_qty / for_qty * 100 END) AS avg_yield,
		       SUM(out_qty) AS out_g, SUM(for_qty) AS in_g
		FROM (
			SELECT DISTINCT tl.operation,
			       COALESCE(NULLIF(emp.employee_name, ''), NULLIF(tl.employee, ''), 'Unassigned') AS employee,
			       jc.name, jc.total_completed_qty AS out_qty, jc.for_quantity AS for_qty
			FROM `tabJob Card Time Log` tl
			INNER JOIN `tabJob Card` jc ON jc.name = tl.parent
			LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
			LEFT JOIN `tabEmployee` emp ON emp.name = tl.employee
			WHERE {' AND '.join(conditions)} AND tl.operation IN %(steps)s
		) credited
		GROUP BY operation, employee
		""",
		params,
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.employee, {})[r.operation] = {
			"yield_pct": round(flt(r.avg_yield), 2),
			"output_kg": round(flt(r.out_g) / 1000, 2),
			"input_kg": round(flt(r.in_g) / 1000, 2),
			"runs": cint(r.runs),
		}
	return out


def _get_yield_by_type(start, end, family_case, company=None, project=None, item=None):
	conditions, params = _run_conditions(start, end, company, project, item)
	conditions.append("jc.operation IS NOT NULL")
	rows = frappe.db.sql(
		f"""
		SELECT
			{family_case} AS family,
			AVG(CASE WHEN jc.for_quantity > 0
				THEN jc.total_completed_qty / jc.for_quantity * 100 ELSE NULL END) AS avg_yield,
			SUM(jc.total_completed_qty) AS total_output_g,
			SUM(jc.for_quantity) AS total_input_g
		{JC_FROM}
		WHERE {' AND '.join(conditions)}
		GROUP BY family
		ORDER BY family
		""",
		params,
		as_dict=True,
	)
	return [
		{
			"label": r.family,
			"avg_yield_pct": round(flt(r.avg_yield), 2),
			"total_output_kg": round(flt(r.total_output_g) / 1000, 2),
			"total_input_kg": round(flt(r.total_input_g) / 1000, 2),
		}
		for r in rows
	]


def _get_suboperation_status(start, end, company=None, project=None, item=None):
	conditions, params = _run_conditions(start, end, company, project, item)
	rows = frappe.db.sql(
		f"""
		SELECT jco.sub_operation, jco.status, COUNT(*) AS cnt
		FROM `tabJob Card Operation` jco
		INNER JOIN `tabJob Card` jc ON jc.name = jco.parent
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE {' AND '.join(conditions)}
		GROUP BY jco.sub_operation, jco.status
		""",
		params,
		as_dict=True,
	)
	by_subop = {}
	for r in rows:
		bucket = SUBOP_STATUS_BUCKETS.get(r.status, "Pending")
		entry = by_subop.setdefault(
			r.sub_operation, {"name": r.sub_operation, "Completed": 0, "In Progress": 0, "Pending": 0}
		)
		entry[bucket] += cint(r.cnt)

	result = []
	for entry in by_subop.values():
		entry["total"] = entry["Completed"] + entry["In Progress"] + entry["Pending"]
		result.append(entry)
	result.sort(key=lambda e: e["name"])
	return result


def _get_employee_hours(start, end, company=None, project=None, item=None):
	# Scoped by when the time was actually logged (tl.from_time), not by the
	# Job Card's own start-date window, but still respects the same
	# company/project/item scoping and drops Cancelled Job Cards.
	conditions, params = _run_conditions(start, end, company, project, item, date_column="tl.from_time")
	# One slice per person who actually logged time, not per designation --
	# several people share a designation and were being merged into one wedge.
	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(emp.employee_name, ''), NULLIF(tl.employee, ''), 'Unassigned') AS designation,
			SUM(tl.time_in_mins) AS mins
		FROM `tabJob Card Time Log` tl
		INNER JOIN `tabJob Card` jc ON jc.name = tl.parent
		LEFT JOIN `tabWork Order` wo ON wo.name = jc.work_order
		LEFT JOIN `tabEmployee` emp ON emp.name = tl.employee
		WHERE {' AND '.join(conditions)}
		GROUP BY designation
		ORDER BY mins DESC
		""",
		params,
		as_dict=True,
	)
	total_hours = round(sum(flt(r.mins) for r in rows) / 60, 2)
	out = []
	for r in rows:
		hours = round(flt(r.mins) / 60, 2)
		out.append(
			{
				"label": r.designation,
				"hours": hours,
				"pct": round(hours / total_hours * 100, 2) if total_hours else 0,
			}
		)
	return {"total_hours": total_hours, "rows": out}


def _get_started_vs_completed(start, end, company=None, project=None, item=None):
	started_conditions, started_params = _run_conditions(start, end, company, project, item)
	started_rows = frappe.db.sql(
		f"""
		SELECT DAYNAME(COALESCE(jc.actual_start_date, jc.creation)) AS wd, COUNT(*) AS cnt
		{JC_FROM}
		WHERE {' AND '.join(started_conditions)}
		GROUP BY wd
		""",
		started_params,
		as_dict=True,
	)

	completed_conditions, completed_params = _run_conditions(
		start, end, company, project, item, date_column="jc.actual_end_date"
	)
	completed_conditions += ["jc.status = 'Completed'", "jc.actual_end_date IS NOT NULL"]
	completed_rows = frappe.db.sql(
		f"""
		SELECT DAYNAME(jc.actual_end_date) AS wd, COUNT(*) AS cnt
		{JC_FROM}
		WHERE {' AND '.join(completed_conditions)}
		GROUP BY wd
		""",
		completed_params,
		as_dict=True,
	)
	started = {r.wd: cint(r.cnt) for r in started_rows}
	completed = {r.wd: cint(r.cnt) for r in completed_rows}
	return [
		{"day": day[:3], "started": started.get(day, 0), "completed": completed.get(day, 0)}
		for day in WEEKDAYS
	]


@frappe.whitelist()
def get_runs_detail(
	from_date=None,
	to_date=None,
	company=None,
	project=None,
	item=None,
	processing_type=None,
	status=None,
	search=None,
	run=None,
	batch=None,
	run_item=None,
	page=1,
	page_size=8,
):
	"""One row per Material Request -- the run -- not per Job Card.

	A run passes through two operations (Hash Processing, then Rosin
	Pressing), each its own Job Card against the same Work Order. The table
	reports the run as a whole, so both Job Cards are folded into a single
	row: micron weights and completed quantities are read per operation and
	presented side by side.
	"""
	start, end = _date_bounds(from_date, to_date)
	page = cint(page) or 1
	page_size = cint(page_size) or 8

	conditions, params = _run_conditions(start, end, company, project, item)
	conditions.append("wo.material_request IS NOT NULL")

	# Search and Status both work on the run as the table shows it -- every
	# Job Card of the Material Request, not just the one row being grouped --
	# and against what is on screen: Run #, Raw Material, the hash / rosin
	# items, and the Batch by its name as well as its ID.
	if search:
		conditions.append(
			f"""(
				wo.material_request LIKE %(search)s
				OR EXISTS (
					SELECT 1 FROM `tabMaterial Request Item` s_mri
					WHERE s_mri.parent = wo.material_request
					  AND (s_mri.item_name LIKE %(search)s OR s_mri.item_code LIKE %(search)s)
				)
				OR EXISTS (
					SELECT 1 {RUN_CARDS_FROM}
					LEFT JOIN `tabProject` s_p ON s_p.name = COALESCE(r_jc.batch, r_wo.project)
					WHERE {RUN_CARDS_WHERE}
					  AND (r_jc.item_name LIKE %(search)s OR r_jc.production_item LIKE %(search)s
					       OR COALESCE(r_jc.batch, r_wo.project) LIKE %(search)s
					       OR s_p.project_name LIKE %(search)s)
				)
			)"""
		)
		params["search"] = f"%{search.strip()}%"

	# Run # / Batch / Item Link filters above the table. Each is an exact
	# match across the whole run: Batch is a Job Card's batch or its Work
	# Order's project, Item is a raw material or a hash / rosin item.
	if run:
		conditions.append("wo.material_request = %(run)s")
		params["run"] = run
	if batch:
		conditions.append(
			f"EXISTS (SELECT 1 {RUN_CARDS_FROM} WHERE {RUN_CARDS_WHERE} "
			"AND COALESCE(r_jc.batch, r_wo.project) = %(batch)s)"
		)
		params["batch"] = batch
	if run_item:
		conditions.append(
			f"""(EXISTS (SELECT 1 FROM `tabMaterial Request Item` i_mri
			             WHERE i_mri.parent = wo.material_request AND i_mri.item_code = %(run_item)s)
			    OR EXISTS (SELECT 1 {RUN_CARDS_FROM} WHERE {RUN_CARDS_WHERE}
			               AND r_jc.production_item = %(run_item)s))"""
		)
		params["run_item"] = run_item

	# Same rule as _build_run_row: Completed only when every card is; In
	# Progress when any card is; otherwise Open.
	if status in ("Open", "Completed", "In Progress"):
		not_done = f"EXISTS (SELECT 1 {RUN_CARDS_FROM} WHERE {RUN_CARDS_WHERE} AND r_jc.status != 'Completed')"
		in_progress = (
			f"EXISTS (SELECT 1 {RUN_CARDS_FROM} WHERE {RUN_CARDS_WHERE} "
			"AND r_jc.status NOT IN ('Open', 'Completed'))"
		)
		conditions.append({
			"Completed": f"NOT {not_done}",
			"In Progress": in_progress,
			"Open": f"({not_done} AND NOT {in_progress})",
		}[status])

	# The Processing Type column is gone, but the filter above the table is
	# not: a run now spans both operations, so this keeps runs that have a
	# Job Card of the chosen type rather than filtering the row itself.
	if processing_type:
		conditions.append(
			"EXISTS (SELECT 1 FROM `tabJob Card` f "
			"INNER JOIN `tabWork Order` fwo ON fwo.name = f.work_order "
			"WHERE fwo.material_request = wo.material_request "
			"AND f.status != 'Cancelled' AND f.operation = %(processing_type)s)"
		)
		params["processing_type"] = processing_type

	where_sql = " AND ".join(conditions)

	# Group the window's Job Cards up to their Material Request, keeping the
	# earliest start so the list can be ordered by when the run began.
	runs_query = f"""
		SELECT wo.material_request AS run_id,
		       MIN(COALESCE(jc.actual_start_date, jc.creation)) AS first_start
		{JC_FROM}
		WHERE {where_sql}
		GROUP BY wo.material_request
	"""

	total_count = cint(
		frappe.db.sql(f"SELECT COUNT(*) AS cnt FROM ({runs_query}) r", params, as_dict=True)[0].cnt
	)

	params["limit"] = page_size
	params["offset"] = (page - 1) * page_size
	run_rows = frappe.db.sql(
		f"SELECT * FROM ({runs_query}) r ORDER BY first_start DESC LIMIT %(limit)s OFFSET %(offset)s",
		params,
		as_dict=True,
	)

	result = [_build_run_row(r.run_id) for r in run_rows]
	return {"rows": result, "total_count": total_count}


def _job_cards_for_run(material_request):
	"""Every non-cancelled Job Card belonging to this Material Request."""
	return frappe.db.sql(
		"""
		SELECT jc.name, jc.operation, jc.status, jc.batch, jc.item_name,
		       jc.production_item, jc.total_completed_qty, jc.total_time_in_mins,
		       jc.actual_start_date, jc.actual_end_date, jc.creation, jc.owner,
		       wo.project AS wo_project
		FROM `tabJob Card` jc
		INNER JOIN `tabWork Order` wo ON wo.name = jc.work_order
		WHERE wo.material_request = %s AND jc.status != 'Cancelled'
		ORDER BY COALESCE(jc.actual_start_date, jc.creation) ASC, jc.creation ASC
		""",
		material_request,
		as_dict=True,
	)


def _micron_grams(job_card_names):
	"""micron_size -> grams collected, summed across the given Job Cards."""
	if not job_card_names:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT micron_size, SUM(grams_collected) AS grams
		FROM `tabMicron Collection Detail`
		WHERE parent IN %(names)s AND parenttype = 'Job Card'
		GROUP BY micron_size
		""",
		{"names": tuple(job_card_names)},
		as_dict=True,
	)
	return {r.micron_size: flt(r.grams) for r in rows}


GRAM_UOMS = {"gram", "grams", "g", "gm"}
POUND_UOMS = {"lbs", "lb", "pound", "pounds"}


def _input_grams(material_request):
	"""Requested material for a run, expressed in grams.

	Yields are output grams over input grams, and the input is recorded in
	pounds on this site (Fresh Frozen lines carry uom = LBS), so pounds are
	multiplied by 453.592. A line already in grams is taken as-is; anything
	else is treated as pounds, which is what every line here uses.
	"""
	rows = frappe.db.sql(
		"SELECT qty, LOWER(COALESCE(uom, stock_uom, '')) AS uom "
		"FROM `tabMaterial Request Item` WHERE parent = %s",
		material_request,
		as_dict=True,
	)
	total = 0.0
	for r in rows:
		qty = flt(r.qty)
		total += qty if r.uom in GRAM_UOMS else qty * GRAMS_PER_POUND
	return total


def _build_run_row(material_request):
	cards = _job_cards_for_run(material_request)
	hash_cards = [c for c in cards if c.operation == HASH_OPERATION]
	rosin_cards = [c for c in cards if c.operation == ROSIN_OPERATION]

	hash_microns = _micron_grams([c.name for c in hash_cards])
	rosin_microns = _micron_grams([c.name for c in rosin_cards])

	hash_qty = sum(flt(c.total_completed_qty) for c in hash_cards)
	rosin_qty = sum(flt(c.total_completed_qty) for c in rosin_cards)

	# Input material in grams. Yields below are output over input as a
	# percentage, so both sides have to be in the same unit.
	input_grams = _input_grams(material_request)

	raw_material = "-"
	item_row = frappe.db.sql(
		"SELECT item_name FROM `tabMaterial Request Item` WHERE parent = %s LIMIT 1",
		material_request,
		as_dict=True,
	)
	if item_row:
		raw_material = item_row[0].item_name
	elif cards:
		raw_material = cards[0].item_name or cards[0].production_item or "-"

	batch_id = next((c.batch or c.wo_project for c in cards if c.batch or c.wo_project), None)
	batch_name = "-"
	if batch_id:
		batch_name = frappe.db.get_value("Project", batch_id, "project_name") or batch_id

	# The run's status is the least-advanced of its Job Cards: it is only
	# Completed once every operation is.
	buckets = {STATUS_BUCKETS.get(c.status, "In Progress") for c in cards}
	if not buckets:
		run_status = "Open"
	elif buckets == {"Completed"}:
		run_status = "Completed"
	elif "In Progress" in buckets:
		run_status = "In Progress"
	else:
		run_status = "Open"

	# Started on: when the first Job Card began. Completed on: when the
	# second operation began, as requested -- the handover point between the
	# two stages, which is what Production treats as the run finishing.
	started_on = cards[0].actual_start_date or cards[0].creation if cards else None
	second_start = None
	if len(cards) > 1:
		second_start = cards[1].actual_start_date or cards[1].creation

	total_mins = sum(flt(c.total_time_in_mins) for c in cards)
	hours, mins = divmod(int(total_mins), 60)

	started_by = "-"
	if cards:
		first_log = frappe.db.sql(
			"SELECT employee FROM `tabJob Card Time Log` WHERE parent = %s "
			"AND IFNULL(employee, '') != '' ORDER BY from_time ASC LIMIT 1",
			cards[0].name,
			as_dict=True,
		)
		if first_log:
			started_by = (
				frappe.db.get_value("Employee", first_log[0].employee, "employee_name")
				or first_log[0].employee
			)
		else:
			started_by = get_fullname(cards[0].owner) or cards[0].owner or "-"

	def fmt_dt(value):
		return get_datetime(value).strftime("%Y-%m-%d %H:%M") if value else "-"

	def yield_pct(output_grams):
		return round(output_grams / input_grams * 100, 2) if input_grams else 0

	return {
		"run_id": material_request,
		"raw_material": raw_material,
		"batch_name": batch_name,
		"status": run_status,
		"status_bucket": run_status,
		"hash_150u": round(hash_microns.get("150u", 0), 2),
		"hash_120u_73u": round(hash_microns.get("120u - 73u", 0), 2),
		"hash_45u": round(hash_microns.get("45u", 0), 2),
		"rosin_150u": round(rosin_microns.get("150u", 0), 2),
		"rosin_120u_73u": round(rosin_microns.get("120u - 73u", 0), 2),
		"rosin_45u": round(rosin_microns.get("45u", 0), 2),
		"hash_yield": yield_pct(hash_qty),
		"rosin_yield": yield_pct(rosin_qty),
		# Conversion yield: how much rosin came out of the hash pressed.
		"hash_to_rosin_yield": round(rosin_qty / hash_qty * 100, 2) if hash_qty else 0,
		"total_time": f"{hours}h {mins}m",
		"started_by": started_by,
		"started_on": fmt_dt(started_on),
		"completed_on": fmt_dt(second_start),
	}
