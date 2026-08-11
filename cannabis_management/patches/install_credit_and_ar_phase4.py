"""Phase 4 of the Credit & AR Control module — the stop-work engine.

Adds the AR Case link fields (they need the DocType to exist first) and
back-fills the hold flags on every customer from whatever cases are live, so the
Customer roll-up is correct on the first run.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "AR Case"):
		frappe.logger("credit_and_ar").warning(
			"AR Case DocType not found — phase 4 patch skipped."
		)
		return

	from cannabis_management.credit_and_ar.custom_fields import install_phase_4_fields
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import sync_customer_from_cases

	install_phase_4_fields()

	for customer in frappe.get_all("AR Case", pluck="customer", distinct=True):
		try:
			sync_customer_from_cases(customer)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"AR Case sync failed for {customer}")
