"""Item-wise Sales Register, with the item's cost on the invoice line.

Takes over the report of the same name. A Report's name is its primary key,
so there is only ever one record called "Item-wise Sales Register" -- this
app claims it by owning the module, and the record is re-pointed here after
every migrate (see reports.install). ERPNext's own version still exists on
disk but nothing loads it.

Everything except the Cost column is core's: `_execute` is called with an
extra table column rather than the query being reimplemented, so filters,
tax columns, grouping and totals keep working and keep pace with upstream.

Cost is Sales Invoice Item.incoming_rate -- the per-unit valuation recorded
against the line when it was sold, not multiplied by quantity. It is blank
on lines ERPNext never costed.
"""

import frappe
from frappe import _

from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import _execute

REPORT_NAME = "Item-wise Sales Register"
MODULE = "Cannabis Management"


def execute(filters=None):
	# `_doctype` makes get_items() select the field off Sales Invoice Item
	# instead of Sales Invoice, and get_values_for_columns() then copies it
	# onto every row by fieldname.
	cost_column = {
		"label": _("Cost"),
		"fieldname": "incoming_rate",
		"fieldtype": "Currency",
		"options": "currency",
		"width": 110,
		"_doctype": "Sales Invoice Item",
	}
	return _execute(filters, additional_table_columns=[cost_column])
