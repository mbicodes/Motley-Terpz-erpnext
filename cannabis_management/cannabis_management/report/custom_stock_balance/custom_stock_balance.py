import frappe
from erpnext.stock.report.stock_balance.stock_balance import StockBalanceReport


def execute(filters=None):
	columns, data = StockBalanceReport(filters).run()

	yield_data = frappe.get_all(
		"Item Yield",
		filters={"parenttype": "Customer Yield Feedback", "docstatus": 1},
		fields=["item_code", "yield_percentage"],
	)

	item_yield_map = {}
	for row in yield_data:
		item_yield_map.setdefault(row.item_code, []).append(str(row.yield_percentage))

	for item_code in item_yield_map:
		item_yield_map[item_code] = ", ".join(dict.fromkeys(item_yield_map[item_code]))

	columns.append({
		"label": "Yield Percentage",
		"fieldname": "yield_percentage",
		"fieldtype": "Data",
		"width": 150,
	})

	for row in data:
		row["yield_percentage"] = item_yield_map.get(row.get("item_code"), "")

	return columns, data
