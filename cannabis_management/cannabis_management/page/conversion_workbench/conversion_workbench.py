# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Conversion Workbench — pick raw materials from live stock and convert in one click.

Implements the "Conversion Workbench - Page Mapping (Developer Spec)" of
7 Oct 2026. The page posts no stock itself: it builds and submits an ordinary
Conversion Entry, so all existing stock, valuation and accounting logic -- and
the Repack Stock Entry the entry creates on submit -- stay exactly as they are.

Shape of one run: N raw materials in, M finished items out, written into the
numbered slots of a single Conversion Entry Item row. That is how entries are
already stored, so nothing downstream has to learn a new shape.

The validation rules below are the spec's section 7, repeated here because the
browser's copy is a convenience: the whitelisted methods are reachable over
/api/method whatever the page does.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

MAX_RAW = 7
MAX_FINISHED = 3
PAGE_LENGTH = 200

# Quantities below this are treated as zero; Bin balances are floats and a
# conversion should not fail on a rounding tail.
QTY_EPSILON = 0.0001


def _conversion_type_options():
	"""Allowed combinations, read from the doctype meta rather than hardcoded,
	so adding an option later needs no change here (spec section 7)."""
	field = frappe.get_meta("Conversion Entry Item").get_field("conversion_type")
	return [o.strip() for o in (field.options or "").split("\n") if o.strip()]


@frappe.whitelist()
def get_conversion_types():
	return _conversion_type_options()


def _company_filter(company):
	if not company:
		frappe.throw(_("Company is required."))
	return company


@frappe.whitelist()
def get_item_groups(company):
	"""Item Groups that currently have stock for the company, with their counts.

	Same query shape as the item list, so a group's count can never disagree
	with the number of rows clicking it produces.
	"""
	company = _company_filter(company)
	rows = frappe.db.sql(
		"""
		-- aliased item_count, not items: on frappe._dict `.items` is dict's own
		-- method, so `row.items` would return the bound method, not the number.
		SELECT i.item_group AS item_group, COUNT(DISTINCT b.item_code) AS item_count
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE w.company = %(company)s
		  AND b.actual_qty > 0
		  AND i.disabled = 0
		GROUP BY i.item_group
		ORDER BY i.item_group
		""",
		{"company": company}, as_dict=True,
	)
	return {
		"groups": rows,
		"total": sum(r.item_count for r in rows),
	}


@frappe.whitelist()
def get_stock_items(company, item_group=None, warehouse=None, search=None,
                    start=0, page_length=PAGE_LENGTH):
	"""In-stock rows for the list. One row per item and warehouse.

	Searching and paging are done here rather than in the browser so a group
	with thousands of items still answers in one screenful (spec section 9).
	"""
	company = _company_filter(company)
	conds = ["w.company = %(company)s", "b.actual_qty > 0", "i.disabled = 0"]
	values = {"company": company,
	          "start": cint(start),
	          "page_length": cint(page_length) or PAGE_LENGTH}

	if item_group:
		conds.append("i.item_group = %(item_group)s")
		values["item_group"] = item_group
	if warehouse:
		conds.append("b.warehouse = %(warehouse)s")
		values["warehouse"] = warehouse
	if search:
		conds.append("(b.item_code LIKE %(search)s OR i.item_name LIKE %(search)s)")
		values["search"] = "%{0}%".format(search)

	rows = frappe.db.sql(
		"""
		SELECT b.item_code, i.item_name, i.item_group, b.warehouse,
		       i.stock_uom, b.actual_qty, b.valuation_rate
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE {conds}
		ORDER BY i.item_name, b.warehouse
		LIMIT %(start)s, %(page_length)s
		""".format(conds=" AND ".join(conds)),
		values, as_dict=True,
	)
	return {"items": rows, "page_length": values["page_length"]}


# ── validation (spec section 7) ──────────────────────────────────────────────

def _validate(payload, raws, finished):
	"""Every blocking rule, in the spec's order. Stops on the first failure."""
	if not raws or not finished:
		frappe.throw(_("Select at least one raw material and one finished item."))

	if len(raws) > MAX_RAW or len(finished) > MAX_FINISHED:
		frappe.throw(_("A Conversion Entry supports up to 7 raw materials and 3 finished items."))

	conversion_type = "{0} to {1}".format(len(raws), len(finished))
	if conversion_type not in _conversion_type_options():
		frappe.throw(_("A conversion of {0} to {1} is not available. Choose a supported combination.")
		             .format(len(raws), len(finished)))

	source = payload.get("source_warehouse")
	target = payload.get("target_warehouse")
	if not source or not target:
		frappe.throw(_("Source Warehouse and Target Warehouse are required."))

	# Rule 4 is about the entry's shape, not the picker's: the row carries one
	# Source Warehouse, so raw materials drawn from two of them cannot be stored.
	for r in raws:
		if r.get("warehouse") and r["warehouse"] != source:
			frappe.throw(_("All raw materials must come from the same Source Warehouse."))

	for r in raws:
		qty = flt(r.get("qty"))
		item = r.get("item_code")
		if qty <= QTY_EPSILON:
			frappe.throw(_("Enter a quantity for {0}.").format(item))
		available = _available(item, source)
		if qty - available > QTY_EPSILON:
			frappe.throw(_("Quantity for {0} cannot exceed the available {1} {2}.")
			             .format(item, flt(available, 2), _stock_uom(item)))

	raw_codes = {r.get("item_code") for r in raws}
	for f in finished:
		item = f.get("item_code")
		if flt(f.get("qty")) <= QTY_EPSILON:
			frappe.throw(_("Enter a quantity for {0}.").format(item))

		detail = frappe.db.get_value("Item", item, ["is_stock_item", "disabled"], as_dict=True)
		if not detail or not detail.is_stock_item or detail.disabled:
			frappe.throw(_("{0} cannot be used as a finished item.").format(item))

		if item in raw_codes and source == target:
			frappe.throw(_("{0} cannot be converted into itself in the same warehouse.").format(item))

	return conversion_type


def _available(item_code, warehouse):
	return flt(frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0)


def _stock_uom(item_code):
	return frappe.db.get_value("Item", item_code, "stock_uom") or ""


# ── the Convert button (spec section 8) ──────────────────────────────────────

@frappe.whitelist()
def create_conversion(payload):
	"""Build one Conversion Entry, insert it and submit it, in one transaction.

	Permissions are checked explicitly and ignore_permissions is never used, so
	a user who cannot submit a Conversion Entry cannot submit one from here.

	Live balances are re-read at this moment rather than trusted from the page:
	between picking an item and pressing Convert someone else may have moved the
	same stock, and the entry must not be the thing that discovers it.
	"""
	payload = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})

	if not frappe.has_permission("Conversion Entry", "create"):
		frappe.throw(_("You are not permitted to create a Conversion Entry."),
		             frappe.PermissionError)
	if not frappe.has_permission("Conversion Entry", "submit"):
		frappe.throw(_("You are not permitted to submit a Conversion Entry."),
		             frappe.PermissionError)

	raws = [r for r in (payload.get("raw_materials") or []) if r.get("item_code")]
	finished = [f for f in (payload.get("finished_items") or []) if f.get("item_code")]
	conversion_type = _validate(payload, raws, finished)

	row = {
		"conversion_type": conversion_type,
		"source_warehouse": payload.get("source_warehouse"),
		"target_warehouse": payload.get("target_warehouse"),
	}
	if payload.get("expense_account"):
		row["expense_account"] = payload["expense_account"]

	for n, r in enumerate(raws, start=1):
		row["raw_material_%d" % n] = r["item_code"]
		row["qty_rm_%d" % n] = flt(r.get("qty"))
		if r.get("tag"):
			row["rm_%d_tag" % n] = r["tag"]

	for n, f in enumerate(finished, start=1):
		row["finished_good_%d" % n] = f["item_code"]
		row["qty_fg_%d" % n] = flt(f.get("qty"))
		if f.get("tag"):
			row["fg_%d_tag" % n] = f["tag"]

	doc = frappe.new_doc("Conversion Entry")
	doc.posting_date = payload.get("posting_date") or nowdate()
	doc.company = payload.get("company")
	for field in ("reasons", "partners", "conversion_status", "customer", "supplier",
	              "sales_order", "project", "workstation", "notes"):
		if payload.get(field):
			doc.set(field, payload[field])
	doc.append("items", row)

	# The balance check sits as close to the insert as it can: anything earlier
	# is a guess about what will still be true when the stock actually moves.
	for r in raws:
		available = _available(r["item_code"], payload.get("source_warehouse"))
		if flt(r.get("qty")) - available > QTY_EPSILON:
			frappe.throw(_("Quantity for {0} cannot exceed the available {1} {2}.")
			             .format(r["item_code"], flt(available, 2), _stock_uom(r["item_code"])))

	doc.insert()
	doc.submit()

	stock_entry = frappe.db.get_value(
		"Stock Entry", {"custom_conversion_entry_reference": doc.name, "docstatus": 0}, "name")

	return {
		"conversion_entry": doc.name,
		"conversion_type": conversion_type,
		"stock_entry": stock_entry,
	}
