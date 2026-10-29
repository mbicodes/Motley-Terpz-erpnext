import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class AllLabTollingData(Document):
	pass


@frappe.whitelist()
def get_stock_balance_items(project, warehouse):
	if not project or not warehouse:
		return []

	from erpnext.stock.report.stock_balance.stock_balance import execute

	filters = frappe._dict({
		"from_date": "2000-01-01",
		"to_date": frappe.utils.today(),
		"warehouse": [warehouse],
		"project": [project],
		"company": frappe.defaults.get_user_default("Company"),
	})

	_columns, data = execute(filters)

	return [
		{
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name") or frappe.db.get_value("Item", row.get("item_code"), "item_name") or row.get("item_code"),
			"bal_qty": flt(row.get("bal_qty")),
		}
		for row in (data or [])
		if flt(row.get("bal_qty")) > 0
	]
