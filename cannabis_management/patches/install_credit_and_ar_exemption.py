import frappe

from cannabis_management.credit_and_ar.custom_fields import install_exemption_fields


def execute():
	install_exemption_fields()

	frappe.db.sql(
		"""
		UPDATE `tabCustomer`
		SET custom_credit_policy_exempt = 0
		WHERE custom_credit_policy_exempt IS NULL
		"""
	)
