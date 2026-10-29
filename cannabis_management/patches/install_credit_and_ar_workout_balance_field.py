import frappe


def execute():
	if not frappe.db.exists("DocType", "AR Case"):
		frappe.logger("credit_and_ar").warning(
			"AR Case DocType not found — workout balance field patch skipped."
		)
		return

	from cannabis_management.credit_and_ar.custom_fields import (
		install_phase_3_fields,
		install_workout_balance_field,
	)

	install_phase_3_fields()
	install_workout_balance_field()
