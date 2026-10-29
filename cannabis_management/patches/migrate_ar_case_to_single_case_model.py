import frappe


def execute():
	if not frappe.db.table_exists("AR Case"):
		return
	if not frappe.db.has_column("AR Case", "case_type"):
		return

	from cannabis_management.credit_and_ar import utils

	if not frappe.db.has_column("AR Case", "resolution"):
		frappe.db.sql_ddl("ALTER TABLE `tabAR Case` ADD COLUMN `resolution` varchar(140) DEFAULT ''")

	rows = frappe.db.sql(
		"""
		SELECT name, case_type, status, trigger_reason, release_basis, released_by
		FROM `tabAR Case`
		""",
		as_dict=True,
	)

	closed_statuses = {"Cured", "Released", "Defaulted", "Closed"}

	for row in rows:
		new_status = "Closed" if row.status in closed_statuses else "Active"

		resolution = ""
		if row.case_type == "Warning":
			new_status = "Closed"
		elif new_status == "Active" and row.case_type == "Payment Plan":
			resolution = "Payment Plan"
		elif new_status == "Active" and row.case_type == "Workout":
			resolution = "Workout"
		elif new_status == "Closed" and (row.release_basis or row.released_by):
			resolution = "Release"

		trigger_reason = utils.HOLD_REASON_BY_TRIGGER.get(row.trigger_reason, "")

		frappe.db.sql(
			"""
			UPDATE `tabAR Case`
			SET status = %(status)s, resolution = %(resolution)s, trigger_reason = %(reason)s
			WHERE name = %(name)s
			""",
			{
				"status": new_status,
				"resolution": resolution,
				"reason": trigger_reason,
				"name": row.name,
			},
		)

	frappe.db.commit()
