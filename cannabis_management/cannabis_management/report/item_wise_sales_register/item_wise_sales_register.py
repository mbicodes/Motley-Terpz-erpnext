import frappe
from frappe import _

from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import _execute

REPORT_NAME = "Item-wise Sales Register"
MODULE = "Cannabis Management"


def execute(filters=None):
	cost_column = {
		"label": _("Cost"),
		"fieldname": "incoming_rate",
		"fieldtype": "Currency",
		"options": "currency",
		"width": 110,
		"_doctype": "Sales Invoice Item",
	}
	return _execute(filters, additional_table_columns=[cost_column])
