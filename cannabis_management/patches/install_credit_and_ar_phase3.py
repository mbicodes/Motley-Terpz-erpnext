import frappe

from cannabis_management.credit_and_ar import masters, utils
from cannabis_management.credit_and_ar.custom_fields import install_phase_3_fields
from cannabis_management.credit_and_ar.property_setters import install_property_setters


def execute():
	install_phase_3_fields()
	install_property_setters()
	masters.install_permlevel_access(doctype="Sales Order", permlevel=1)

	_backfill_invoice_ledger()
	_default_existing_sales_orders()


def _backfill_invoice_ledger():
	effective_date = utils.policy_effective_date()
	if not effective_date:
		frappe.logger("credit_and_ar").info(
			"policy_effective_date not set — Sales Invoice ledger backfill skipped."
		)
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice`
		SET custom_ledger = %s
		WHERE posting_date < %s
		  AND (custom_ledger IS NULL OR custom_ledger = '')
		""",
		(utils.LEDGER_LEGACY, effective_date),
	)
	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice`
		SET custom_ledger = %s
		WHERE posting_date >= %s
		  AND (custom_ledger IS NULL OR custom_ledger = '')
		""",
		(utils.LEDGER_NEW_BOOK, effective_date),
	)


def _default_existing_sales_orders():
	frappe.db.sql(
		"""
		UPDATE `tabSales Order`
		SET custom_mode_of_payment = %s
		WHERE custom_mode_of_payment IS NULL OR custom_mode_of_payment = ''
		""",
		(utils.MODE_COD,),
	)
	frappe.db.sql(
		"""
		UPDATE `tabSales Order`
		SET custom_approval_status = %s
		WHERE (custom_approval_status IS NULL OR custom_approval_status = '')
		  AND custom_mode_of_payment != %s
		""",
		(utils.APPROVAL_NOT_REQUIRED, utils.MODE_TERMS),
	)
