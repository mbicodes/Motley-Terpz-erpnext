import frappe

from cannabis_management.credit_and_ar.dashboard import install_number_cards
from cannabis_management.credit_and_ar.notifications import install_notifications


def execute():
	if not frappe.db.exists("DocType", "AR Case"):
		frappe.logger("credit_and_ar").warning(
			"AR Case DocType not found — phase 7 patch skipped."
		)
		return

	install_number_cards()
	install_notifications()
