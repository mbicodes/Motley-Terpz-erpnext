import frappe


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
def get_packaged_inventory(search_term=""):
	"""Return packaged goods items with current stock levels."""
	filters = {"item_group": ["in", PACKAGED_ITEM_GROUPS], "disabled": 0}
	or_filters = {}
	if search_term:
		or_filters = {
			"item_code": ["like", f"%{search_term}%"],
			"item_name": ["like", f"%{search_term}%"],
		}

	items = frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "item_name", "item_group", "stock_uom"],
		order_by="item_name asc",
		limit_page_length=200,
	)

	item_codes = [i.name for i in items]
	if not item_codes:
		return []

	stock = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", item_codes]},
		fields=["item_code", "actual_qty"],
	)

	stock_map = {}
	for s in stock:
		stock_map.setdefault(s.item_code, 0)
		stock_map[s.item_code] += s.actual_qty

	for item in items:
		item["available_qty"] = stock_map.get(item.name, 0)

	return items


@frappe.whitelist()
def save_preorder(data):
	"""Create a Preorder Entry document from page form data."""
	import json

	if isinstance(data, str):
		data = json.loads(data)

	doc = frappe.new_doc("Preorder Entry")
	doc.rep_name = data.get("rep_name")
	doc.rep_email = data.get("rep_email")
	doc.rep_phone = data.get("rep_phone")
	doc.brand_name = data.get("brand_name")
	doc.license_name = data.get("license_name")
	doc.license_number = data.get("license_number")
	doc.primary_address = data.get("primary_address")
	doc.region = data.get("region")
	doc.order_date = data.get("order_date")
	doc.requested_delivery_date = data.get("requested_delivery_date")
	doc.company = data.get("company")
	doc.notes = data.get("notes")

	for row in data.get("items", []):
		item_code = (row.get("item_code") or "").strip()
		item_name = (row.get("item_name") or "").strip()
		uom = (row.get("uom") or "").strip()

		# A preorder row is allowed to name something we do not stock yet --
		# reps regularly ask for a product before it exists as an Item. Both
		# item_code and uom are Link fields, so anything that is not a real
		# record has to be dropped or carried as free text, or doc.insert()
		# fails link validation and the whole preorder is lost.
		if item_code and not frappe.db.exists("Item", item_code):
			item_name = item_name or item_code
			item_code = None
		if uom and not frappe.db.exists("UOM", uom):
			uom = None

		# Nothing identifying the row at all -- skip it rather than storing a
		# blank line that no one can act on.
		if not item_code and not item_name:
			continue

		doc.append("items", {
			"item_code": item_code or None,
			"item_name": item_name or None,
			"item_group": row.get("item_group"),
			"qty": row.get("qty"),
			"uom": uom or None,
			"notes": row.get("notes"),
		})

	doc.insert()
	return {"name": doc.name, "doctype": "Preorder Entry"}


@frappe.whitelist()
def get_recent_preorders(limit=20):
	"""Return recent preorder entries for the listing panel."""
	return frappe.get_all(
		"Preorder Entry",
		fields=[
			"name", "rep_name", "brand_name", "region",
			"order_date", "docstatus", "creation",
		],
		order_by="creation desc",
		limit_page_length=limit,
	)
