"""Per-customer exemption from the Credit & AR policy.

Adds `custom_credit_policy_exempt` (+ reason) to Customer at permlevel 1, so the
carve-out is a Credit Finance / Managing Director decision rather than something
Sales can grant itself, and widens the credit-status options to carry
`Policy Exempt`.

Idempotent.
"""

import frappe

from cannabis_management.credit_and_ar.custom_fields import install_exemption_fields


def execute():
	install_exemption_fields()

	# Nothing is exempt by default — the policy applies until someone says
	# otherwise, in writing, on the record.
	frappe.db.sql(
		"""
		UPDATE `tabCustomer`
		SET custom_credit_policy_exempt = 0
		WHERE custom_credit_policy_exempt IS NULL
		"""
	)
