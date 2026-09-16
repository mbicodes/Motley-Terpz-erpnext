import frappe
from frappe.model.document import Document


class PreorderEntry(Document):
	pass


PACKAGED_ITEM_GROUPS = [
	"Packaged goods",
	"0.5g O2 Vape",
	"0.5G Vapes (Packaged)",
	"1g Jarred Rosin",
	"1g O2 Vapes",
	"1G Vapes (Packaged)",
	"3g Jarred Rosin",
]


@frappe.whitelist()
def get_packaged_goods_items(search_term="", limit=40):
	filters = {"item_group": ["in", PACKAGED_ITEM_GROUPS], "disabled": 0}
	or_filters = {}
	if search_term:
		or_filters = {
			"item_code": ["like", f"%{search_term}%"],
			"item_name": ["like", f"%{search_term}%"],
		}

	return frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "item_name", "item_group", "stock_uom"],
		order_by="item_name asc",
		limit_page_length=limit,
	)


@frappe.whitelist()
def get_packaged_goods_stock():
	"""Return current stock for all packaged goods items."""
	items = frappe.get_all(
		"Item",
		filters={"item_group": ["in", PACKAGED_ITEM_GROUPS], "disabled": 0},
		fields=["name", "item_name", "item_group", "stock_uom"],
		order_by="item_name asc",
	)

	item_codes = [i.name for i in items]
	if not item_codes:
		return []

	stock = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", item_codes], "actual_qty": [">", 0]},
		fields=["item_code", "warehouse", "actual_qty"],
	)

	stock_map = {}
	for s in stock:
		stock_map.setdefault(s.item_code, 0)
		stock_map[s.item_code] += s.actual_qty

	for item in items:
		item["available_qty"] = stock_map.get(item.name, 0)

	return items
