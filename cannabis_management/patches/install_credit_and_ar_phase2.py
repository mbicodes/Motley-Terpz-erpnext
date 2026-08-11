"""Phase 2 of the Credit & AR Control module.

The Credit Application workflow and the Customer link field that points at the
live application. Idempotent.
"""

import frappe

from cannabis_management.credit_and_ar.custom_fields import install_phase_2_fields
from cannabis_management.credit_and_ar.workflow import install_workflow


def execute():
	if not frappe.db.exists("DocType", "Credit Application"):
		# The DocType syncs before post_model_sync patches; if it is missing the
		# app is mid-deploy and this will run on the next migrate.
		frappe.logger("credit_and_ar").warning(
			"Credit Application DocType not found — phase 2 patch skipped."
		)
		return

	install_phase_2_fields()
	install_workflow()
