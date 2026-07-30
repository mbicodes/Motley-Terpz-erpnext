# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class MetricTag(Document):
	def validate(self):
		self.set_muid()
		self.last_updated = now_datetime()

	def set_muid(self):
		self.muid = (self.tag_code or "")[-4:]


# ---------------------------------------------------------------------------
# Status/qty lifecycle sync — the Inventory Dimension framework (dimension
# "Muid", target_fieldname "metric_tag") tracks quantity per tag natively in
# the Stock Ledger, it does not touch this doctype. These hooks, registered in
# hooks.py against Stock Entry / Delivery Note / Purchase Receipt / Stock
# Reconciliation, resync the cached fields here whenever a transaction that
# carries the dimension is submitted or cancelled.
# ---------------------------------------------------------------------------

CHILD_TABLE_FIELDNAME = {
	"Stock Entry": "items",
	"Delivery Note": "items",
	"Purchase Receipt": "items",
	"Stock Reconciliation": "items",
}


def get_metric_tag_dimension_names():
	"""(source_fieldname, target_fieldname) configured on the Muid Inventory Dimension."""

	def _fetch():
		row = frappe.db.get_value(
			"Inventory Dimension",
			{"reference_document": "Metric Tag"},
			["source_fieldname", "target_fieldname"],
			as_dict=True,
		)
		return (row.source_fieldname, row.target_fieldname) if row else ("muid", "metric_tag")

	return frappe.cache.hget("metric_tag_sync", "dimension_names", _fetch)


def get_metric_tag_dimension_fieldname():
	"""Fieldname the Muid Inventory Dimension writes onto Stock Ledger Entry."""
	return get_metric_tag_dimension_names()[1]


def get_row_tag_fieldname(child_doctype):
	"""Fieldname on this child table that links to Metric Tag.

	Normally this is the dimension's source_fieldname ("muid"), but a quirk in
	ERPNext's Inventory Dimension custom-field creation (apply_to_all_doctypes)
	leaves the last-processed doctype using target_fieldname instead — so check
	the doctype's actual meta rather than assume one name works everywhere.
	Child tables also carry unrelated "to_muid"/"from_muid"/"rejected_muid"
	transfer companion fields, so this can't be a fuzzy Custom Field lookup.
	"""

	def _fetch():
		source_fieldname, target_fieldname = get_metric_tag_dimension_names()
		meta = frappe.get_meta(child_doctype)
		if meta.has_field(source_fieldname):
			return source_fieldname
		if meta.has_field(target_fieldname):
			return target_fieldname
		return None

	return frappe.cache.hget("metric_tag_sync", f"row_fieldname:{child_doctype}", _fetch)


def get_stock_balance_for_dimension(item_code, warehouse, dimension_field, dimension_value):
	"""Net quantity for this item+warehouse+dimension-value.

	erpnext.stock.utils.get_stock_balance's inventory_dimensions_dict filter
	only picks *which row* to read qty_after_transaction from — that column
	is the running balance for the whole item+warehouse, not scoped to a
	single dimension value, so two tags in the same warehouse would leak
	into each other's balance. Summing actual_qty across the matching,
	non-cancelled rows gives the correct per-tag balance instead.
	"""
	column = frappe.utils.sanitize_column(dimension_field)
	total = frappe.db.sql(
		f"""
		select sum(actual_qty)
		from `tabStock Ledger Entry`
		where item_code = %(item_code)s
			and warehouse = %(warehouse)s
			and is_cancelled = 0
			and {column} = %(dimension_value)s
		""",  # nosemgrep
		{"item_code": item_code, "warehouse": warehouse, "dimension_value": dimension_value},
	)[0][0]
	return flt(total)


def get_stock_entry_legs():
	"""(tag_fieldname, warehouse_fieldname) pairs for the two legs a Stock Entry
	Detail row can carry. ERPNext's own dimension-copy logic (see
	erpnext.controllers.stock_controller.StockController.update_inventory_dimensions)
	reads the plain source_fieldname ("muid") for the s_warehouse leg and the
	"to_"-prefixed field ("to_muid") for the t_warehouse leg — a row that both
	issues and receives (a transfer) can therefore carry two different tags."""
	source_fieldname, _ = get_metric_tag_dimension_names()
	return [
		(source_fieldname, "s_warehouse"),
		(f"to_{source_fieldname}", "t_warehouse"),
	]


def normalize_stock_entry_tag_fields(doc, method=None):
	"""validate hook for Stock Entry.

	A row with only one warehouse leg (a plain Material Receipt or Material
	Issue) still exposes both the "muid" and "to_muid" fields on the form,
	but ERPNext's SLE-copy logic only ever reads "muid" for the s_warehouse
	leg and "to_muid" for the t_warehouse leg. If a user fills the field that
	matches the row's *only* warehouse into the other one, the Stock Ledger
	Entry ends up with no tag at all and nothing here can sync. Mirror the
	value onto whichever fieldname ERPNext will actually read, so either
	field works for a single-leg row.
	"""
	source_fieldname, _ = get_metric_tag_dimension_names()
	to_fieldname = f"to_{source_fieldname}"

	for row in doc.get("items") or []:
		if not (row.get(source_fieldname) or row.get(to_fieldname)):
			continue

		if row.get("t_warehouse") and not row.get("s_warehouse"):
			# Receipt-only row — ERPNext reads to_fieldname for this leg.
			if row.get(source_fieldname) and not row.get(to_fieldname):
				row.set(to_fieldname, row.get(source_fieldname))
		elif row.get("s_warehouse") and not row.get("t_warehouse"):
			# Issue-only row — ERPNext reads source_fieldname for this leg.
			if row.get(to_fieldname) and not row.get(source_fieldname):
				row.set(source_fieldname, row.get(to_fieldname))


def get_touched_tags(doc):
	"""Distinct (tag_name, item_code, warehouse) tuples referenced by doc's item rows."""
	child_fieldname = CHILD_TABLE_FIELDNAME.get(doc.doctype)
	if not child_fieldname:
		return []

	rows = doc.get(child_fieldname) or []
	if not rows:
		return []

	touched = {}

	if doc.doctype == "Stock Entry":
		for row in rows:
			for tag_fieldname, warehouse_fieldname in get_stock_entry_legs():
				tag_name = row.get(tag_fieldname)
				warehouse = row.get(warehouse_fieldname)
				if tag_name and warehouse:
					touched[tag_name] = (row.item_code, warehouse)
	else:
		row_fieldname = get_row_tag_fieldname(rows[0].doctype)
		if row_fieldname:
			for row in rows:
				tag_name = row.get(row_fieldname)
				warehouse = row.get("warehouse")
				if tag_name and warehouse:
					touched[tag_name] = (row.item_code, warehouse)

	return [(tag, item_code, warehouse) for tag, (item_code, warehouse) in touched.items()]


def sync_metric_tag(tag_name, item_code, warehouse, txn_doctype, txn_name):
	dimension_field = get_metric_tag_dimension_fieldname()
	balance = get_stock_balance_for_dimension(item_code, warehouse, dimension_field, tag_name)

	tag = frappe.get_doc("Metric Tag", tag_name)
	tag.current_qty = balance
	tag.item_code = item_code
	tag.warehouse = warehouse
	tag.status = "Empty" if balance <= 0 else "Active"
	tag.last_transaction_type = txn_doctype
	tag.last_transaction_id = txn_name
	tag.last_updated = now_datetime()
	tag.save(ignore_permissions=True)


def sync_metric_tags(doc, method=None):
	"""on_submit / on_cancel hook for Stock Entry, Delivery Note, Purchase Receipt,
	Stock Reconciliation (and, by extension, the Stock Entries a Job Card generates)."""
	for tag_name, item_code, warehouse in get_touched_tags(doc):
		sync_metric_tag(tag_name, item_code, warehouse, doc.doctype, doc.name)


def validate_metric_tag_status(doc, method=None):
	"""before_submit hook — block submission if a row's tag is already Empty."""
	for tag_name, _item_code, _warehouse in get_touched_tags(doc):
		status = frappe.db.get_value("Metric Tag", tag_name, "status")
		if status == "Empty":
			frappe.throw(
				_("Row referencing Metric Tag {0} cannot be submitted — that tag is Empty.").format(
					frappe.bold(tag_name)
				)
			)
