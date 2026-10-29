import frappe
from frappe.model.document import Document
from frappe.utils import flt

GRAMS_PER_LB = 453.59237


class CustomerYieldFeedback(Document):
	def validate(self):
		if self.sales_order:
			so_customer = frappe.db.get_value("Sales Order", self.sales_order, "customer")
			if so_customer != self.customer:
				frappe.throw(f"Sales Order {self.sales_order} belongs to {so_customer}, not {self.customer}")
		for row in self.item_yield:
			calculate_row(row)


def calculate_row(row):
	raw_g = flt(row.quantity) * GRAMS_PER_LB
	if raw_g and flt(row.hash_qty):
		row.yield_percentage = flt(row.hash_qty) / raw_g * 100
	if flt(row.hash_qty) and flt(row.rosin_qty):
		row.hash_to_rosin = flt(row.rosin_qty) / flt(row.hash_qty) * 100
	if raw_g and flt(row.rosin_qty):
		row.rosin_yield = flt(row.rosin_qty) / raw_g * 100
	elif flt(row.yield_percentage) and flt(row.hash_to_rosin):
		row.rosin_yield = flt(row.yield_percentage) * flt(row.hash_to_rosin) / 100
	else:
		row.rosin_yield = 0


@frappe.whitelist()
def get_sales_order_items(sales_order):
	frappe.has_permission("Sales Order", "read", sales_order, throw=True)
	return frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order},
		fields=["name as sales_order_item", "item_code", "item_name", "stock_qty as quantity", "project"],
		order_by="idx",
	)
