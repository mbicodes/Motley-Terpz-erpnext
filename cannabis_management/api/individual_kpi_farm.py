import frappe
from frappe.utils import add_months, today


@frappe.whitelist()
def get_employee_options():
	"""Employees that have an Individual KPI profile configured."""
	return frappe.db.sql(
		"""
		SELECT p.employee AS employee, e.employee_name AS label
		FROM `tabFarm Employee KPI Profile` p
		INNER JOIN `tabEmployee` e ON e.name = p.employee
		ORDER BY e.employee_name ASC
		""",
		as_dict=True,
	)


@frappe.whitelist()
def get_profile(employee):
	"""Static job-description content (responsibilities, KPI/target/how-measured,
	note, reports-to) — maintained via the Farm Employee KPI Profile doctype
	rather than hardcoded in the page, so Matt/ops can edit it without a
	code change."""
	if not frappe.db.exists("Farm Employee KPI Profile", employee):
		return None

	doc = frappe.get_doc("Farm Employee KPI Profile", employee)
	return {
		"employee": doc.employee,
		"employee_name": frappe.db.get_value("Employee", doc.employee, "employee_name"),
		"role_title": doc.role_title,
		"reports_to": doc.reports_to,
		"employment_type": doc.employment_type,
		"note": doc.note,
		"responsibilities": [r.responsibility for r in doc.responsibilities],
		"kpi_targets": [
			{
				"kpi_label": row.kpi_label,
				"target": row.target,
				"backend_key": row.backend_key,
				"suffix": row.suffix,
				"how_measured": row.how_measured,
			}
			for row in doc.kpi_targets
		],
		"performance_review_cadence": doc.performance_review_cadence,
	}


@frappe.whitelist()
def get_actuals(employee, from_date=None, to_date=None):
	"""Every KPI value this system can currently calculate for one employee,
	over a date range (default: last 30 days). The page matches these
	against each profile's kpi_targets.backend_key to fill in "Actual"."""
	from_date = from_date or add_months(today(), -1)
	to_date = to_date or today()

	# --- Farm Daily Log based KPIs ---
	logs = frappe.get_all(
		"Farm Daily Log",
		filters={
			"logged_by": employee,
			"log_date": ["between", [from_date, to_date]],
		},
		fields=["scouting_completed", "dcc_ready_status", "issue_reported"],
	)
	total_logs = len(logs) or 1

	scouting_pct = sum(1 for l in logs if l.scouting_completed) / total_logs * 100
	dcc_pct = sum(1 for l in logs if l.dcc_ready_status == "Pass") / total_logs * 100
	issues_same_day = sum(1 for l in logs if l.issue_reported)

	# --- Farm-wide DCC status (shared compliance status, not employee specific) ---
	all_logs = frappe.get_all(
		"Farm Daily Log",
		filters={"log_date": ["between", [from_date, to_date]]},
		fields=["dcc_ready_status", "metrc_open_corrections"],
	)
	total_all_logs = len(all_logs) or 1
	farmwide_dcc_pct = sum(1 for l in all_logs if l.dcc_ready_status == "Pass") / total_all_logs * 100
	farmwide_open_corrections = sum(l.metrc_open_corrections or 0 for l in all_logs)

	# --- Farm Labor Session based KPIs ---
	mix_ups = frappe.db.count(
		"Farm Labor Session",
		{
			"employee": employee,
			"task_type": "Planting",
			"mix_up_flag": 1,
			"session_date": ["between", [from_date, to_date]],
		},
	)

	def task_rate(task_type):
		return (
			frappe.db.sql(
				"""
				SELECT AVG(rate_per_hour)
				FROM `tabFarm Labor Session`
				WHERE employee = %s AND task_type = %s
				AND session_date BETWEEN %s AND %s
				AND docstatus = 1
				""",
				(employee, task_type, from_date, to_date),
			)[0][0]
			or 0
		)

	deleaf_rate = task_rate("Deleaf")
	bucking_rate = task_rate("Bucking")
	planting_rate = task_rate("Planting")

	# --- Cloning Batch based KPIs ---
	clones_rate = (
		frappe.db.sql(
			"""
			SELECT AVG(clones_per_hour)
			FROM `tabCloning Batch`
			WHERE performed_by = %s
			AND session_date BETWEEN %s AND %s
			AND docstatus = 1
			""",
			(employee, from_date, to_date),
		)[0][0]
		or 0
	)

	# "Nursery tray log completion" — % of this employee's Cloning Batch
	# entries that were actually submitted rather than left in Draft.
	# Cloning Batch has no dedicated "log completed" field, so submission
	# status is used as the proxy for a completed tray log.
	tray_logs = frappe.get_all(
		"Cloning Batch",
		filters={
			"performed_by": employee,
			"session_date": ["between", [from_date, to_date]],
			"docstatus": ["in", [0, 1]],
		},
		fields=["docstatus"],
	)
	total_tray_logs = len(tray_logs) or 1
	tray_log_completion_pct = sum(1 for t in tray_logs if t.docstatus == 1) / total_tray_logs * 100

	return {
		"scouting_pct": round(scouting_pct, 1),
		"dcc_pct": round(dcc_pct, 1),
		"issues_same_day": issues_same_day,
		"mix_ups": mix_ups,
		"deleaf_rate": round(deleaf_rate, 2),
		"bucking_rate": round(bucking_rate, 2),
		"planting_rate": round(planting_rate, 2),
		"clones_rate": round(clones_rate, 2),
		"tray_log_completion_pct": round(tray_log_completion_pct, 1),
		"farmwide_dcc_pct": round(farmwide_dcc_pct, 1),
		"farmwide_open_corrections": farmwide_open_corrections,
		"total_logs": len(logs),
	}
