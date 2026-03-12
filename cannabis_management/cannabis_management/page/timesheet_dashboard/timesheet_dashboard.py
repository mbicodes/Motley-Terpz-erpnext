import frappe


@frappe.whitelist()
def get_employee_timesheet_details(employee):
	"""
	Returns all Timesheet Detail rows for a given employee,
	joined with parent Timesheet status.
	"""
	if not employee:
		frappe.throw("Employee is required")

	if not frappe.has_permission("Timesheet", "read"):
		frappe.throw("Not permitted", frappe.PermissionError)

	rows = frappe.db.sql(
		"""
		SELECT
			td.name            AS detail_name,
			td.parent          AS timesheet,
			td.from_time,
			td.to_time,
			td.hours,
			td.billing_hours,
			td.billing_amount,
			td.activity_type,
			td.project,
			td.task,
			ts.status          AS ts_status,
			ts.employee_name   AS employee_name
		FROM
			`tabTimesheet Detail` td
			INNER JOIN `tabTimesheet` ts ON ts.name = td.parent
		WHERE
			ts.employee = %(employee)s
		ORDER BY
			td.from_time DESC
		""",
		{"employee": employee},
		as_dict=True,
	)

	return rows


@frappe.whitelist()
def get_active_employees():
	"""
	Returns all active employees for the sidebar list.
	"""
	return frappe.db.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name"],
		order_by="employee_name asc",
		limit=200,
	)