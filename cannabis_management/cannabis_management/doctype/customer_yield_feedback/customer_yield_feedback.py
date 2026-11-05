import frappe
from frappe.model.document import Document
from frappe.utils import flt

GRAMS_PER_LB = 453.59237


class CustomerYieldFeedback(Document):
	def validate(self):
		self.sync_entry_to_table()
		if not self.item_yield:
			frappe.throw("Enter the Item and its yield, or add lines in the Yields table.")
		if not self.customer and any((row.yield_source or "Customer") == "Customer" for row in self.item_yield):
			frappe.throw("Customer is required when a line's Source is Customer (use Source = Our Lab for our own yields).")
		if self.sales_order:
			so_customer = frappe.db.get_value("Sales Order", self.sales_order, "customer")
			if so_customer != self.customer:
				frappe.throw(f"Sales Order {self.sales_order} belongs to {so_customer}, not {self.customer}")
		for row in self.item_yield:
			calculate_row(row)
		self.copy_entry_back()

	def sync_entry_to_table(self):
		"""Item filled on the form = a one-item feedback: that entry is the only Yields line."""
		if not self.get("item_code"):
			return
		values = {f: self.get(f) for f in ENTRY_FIELDS}
		row = self.item_yield[0] if len(self.item_yield) == 1 and self.item_yield[0].item_code == self.item_code else None
		if row is None:
			self.set("item_yield", [])
			row = self.append("item_yield", {})
		row.update(values)

	def copy_entry_back(self):
		"""Show the calculated % on the form fields too."""
		if self.get("item_code") and self.item_yield:
			for f in ENTRY_FIELDS:
				self.set(f, self.item_yield[0].get(f))


SHO_FIELDS = ("hash_qty", "yield_percentage", "rosin_qty", "hash_to_rosin", "rosin_yield")
# form-level yield entry (same field names as the Item Yield line it fills)
ENTRY_FIELDS = ("item_code", "run_to", "yield_source", "quantity", "hash_qty", "yield_percentage",
                "rosin_qty", "hash_to_rosin", "bho_qty", "bho_yield")
BHO_FIELDS = ("bho_qty", "bho_yield")


def calculate_row(row):
	"""Run To SHO keeps the wash fields (Yield to Hash, Hash to Rosin); Run To BHO keeps only the BHO
	fields, so a line never counts in both Run to SHO and Run to BHO on the Inventory Dashboard."""
	run_to = row.get("run_to") or "SHO"
	for f in (SHO_FIELDS if run_to == "BHO" else BHO_FIELDS):
		if row.meta.has_field(f):
			row.set(f, 0)
	raw_g = flt(row.quantity) * GRAMS_PER_LB
	if raw_g and flt(row.hash_qty):
		row.yield_percentage = flt(row.hash_qty) / raw_g * 100
	if flt(row.hash_qty) and flt(row.rosin_qty):
		row.hash_to_rosin = flt(row.rosin_qty) / flt(row.hash_qty) * 100
	if raw_g and flt(row.rosin_qty):
		row.rosin_yield = flt(row.rosin_qty) / raw_g * 100
	elif flt(row.yield_percentage) and flt(row.hash_to_rosin):
		row.rosin_yield = flt(row.yield_percentage) * flt(row.hash_to_rosin) / 100
	elif run_to != "BHO":
		row.rosin_yield = 0
	if raw_g and flt(row.get("bho_qty")):
		row.bho_yield = flt(row.bho_qty) / raw_g * 100


@frappe.whitelist()
def get_sales_order_items(sales_order):
	frappe.has_permission("Sales Order", "read", sales_order, throw=True)
	return frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order},
		fields=["name as sales_order_item", "item_code", "item_name", "stock_qty as quantity", "project"],
		order_by="idx",
	)
