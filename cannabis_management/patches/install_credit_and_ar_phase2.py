import frappe

from cannabis_management.credit_and_ar.custom_fields import install_phase_2_fields
from cannabis_management.credit_and_ar.workflow import install_workflow


def execute():
	if not frappe.db.exists("DocType", "Credit Application"):
		frappe.logger("credit_and_ar").warning(
			"Credit Application DocType not found — phase 2 patch skipped."
		)
		return

	install_phase_2_fields()
	install_workflow()
