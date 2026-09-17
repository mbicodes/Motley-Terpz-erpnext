"""Workout paydown rework — Sales Order gains a running balance snapshot.

Required Paydown is now measured against Net Total (not Grand Total), and
"paydown made" is the drop in the AR Case's live Current Balance since the
customer's last submitted workout order, rather than a sum of Payment Entries
tagged to this specific order. "Workout Balance at Order" is the new field
that carries that baseline forward from one order to the next.
"""

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

	# Re-apply phase 3 too: custom_workout_paydown_required/received picked up
	# new labels and descriptions for the Net-Total-based rework, and phase 3
	# already ran on every existing site so create_custom_fields would not
	# otherwise revisit them.
	install_phase_3_fields()
	install_workout_balance_field()
