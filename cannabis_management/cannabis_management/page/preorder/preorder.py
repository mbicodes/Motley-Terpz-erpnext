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
def get_preorder(name):
	"""Return one Preorder Entry shaped the way the form expects it.

	Used to load an existing entry back into the page for editing. Permission
	is checked explicitly -- frappe.get_doc does not do it on its own.
	"""
	doc = frappe.get_doc("Preorder Entry", name)
	doc.check_permission("read")

	return {
		"name": doc.name,
		"docstatus": doc.docstatus,
		"rep_name": doc.rep_name,
		"rep_email": doc.rep_email,
		"rep_phone": doc.rep_phone,
		"brand_name": doc.brand_name,
		"license_name": doc.license_name,
		"license_number": doc.license_number,
		"primary_address": doc.primary_address,
		"region": doc.region,
		"order_date": doc.order_date,
		"requested_delivery_date": doc.requested_delivery_date,
		"company": doc.company,
		"notes": doc.notes,
		"items": [
			{
				"item_code": r.item_code,
				"item_name": r.item_name,
				"item_group": r.item_group,
				"qty": r.qty,
				"uom": r.uom,
				"rate": r.rate,
				"amount": r.amount,
				"notes": r.notes,
				# A row with no item_code was typed as free text; the form
				# needs to know so it renders the "Custom item" badge again.
				"is_custom": not r.item_code,
			}
			for r in doc.items
		],
	}


@frappe.whitelist()
def save_preorder(data, name=None):
	"""Create a Preorder Entry from page form data, or update an existing one.

	Passing `name` edits that entry in place instead of creating another. Only
	drafts can be edited -- a submitted document is immutable in Frappe, so
	say so plainly rather than letting doc.save() fail further down.
	"""
	import json

	if isinstance(data, str):
		data = json.loads(data)

	if name:
		doc = frappe.get_doc("Preorder Entry", name)
		if doc.docstatus != 0:
			frappe.throw(
				frappe._("{0} is already submitted and can no longer be edited.").format(name)
			)
		# Rebuild the table from what the form sent rather than merging: the
		# form owns the full row set, including deletions.
		doc.set("items", [])
	else:
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

		# Amount is derived here rather than trusted from the client:
		# Preorder Item.amount is read_only, so the form only ever previews it.
		qty = frappe.utils.cint(row.get("qty"))
		rate = frappe.utils.flt(row.get("rate"))

		doc.append("items", {
			"item_code": item_code or None,
			"item_name": item_name or None,
			"item_group": row.get("item_group"),
			"qty": qty,
			"uom": uom or None,
			"rate": rate,
			"amount": qty * rate,
			"notes": row.get("notes"),
		})

	doc.save()
	return {"name": doc.name, "doctype": "Preorder Entry", "updated": bool(name)}


@frappe.whitelist()
def submit_preorder(name):
	"""Submit a draft Preorder Entry.

	Submitting is the point of no return for editing -- a submitted document
	cannot be changed, only cancelled -- so refuse anything that is not still
	a draft rather than letting doc.submit() raise something less readable.
	"""
	doc = frappe.get_doc("Preorder Entry", name)
	if doc.docstatus != 0:
		frappe.throw(
			frappe._("{0} is not a draft, so it cannot be submitted.").format(name)
		)

	doc.submit()
	return {"name": doc.name, "docstatus": doc.docstatus}


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
