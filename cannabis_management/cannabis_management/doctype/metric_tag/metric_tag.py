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
	source_fieldname, _target_fieldname = get_metric_tag_dimension_names()
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
	source_fieldname, _target_fieldname = get_metric_tag_dimension_names()
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


def validate_stock_entry_tag_mandatory(doc, method=None):
	"""validate hook for Stock Entry -- server-side mandatory check for the
	Source Tag field, replacing the Muid Inventory Dimension's own blanket
	reqd=1 on it (relaxed to 0 on this doctype's Custom Field specifically,
	since that flag applied identically to every row with no way to exempt
	one). A finished-good row (is_finished_item checked) is an output, not
	something being issued from stock -- it only ever needs its own Target
	Tag (to_<source_fieldname>), never a Source Tag, so it's exempt outright.
	A Repack raw-material row (Source Warehouse set) still needs one; so does
	every row on any other Stock Entry type, matching the field's old
	unconditional behaviour there.
	"""
	source_fieldname, _target_fieldname = get_metric_tag_dimension_names()
	is_repack = doc.stock_entry_type == "Repack"
	label = frappe.get_meta("Stock Entry Detail").get_label(source_fieldname)

	for row in doc.get("items") or []:
		if row.get("is_finished_item"):
			continue
		required = bool(row.get("s_warehouse")) if is_repack else True
		if required and not row.get(source_fieldname):
			frappe.throw(
				_("Row #{0}: {1} is mandatory.").format(row.idx, frappe.bold(label))
			)


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
	elif doc.doctype == "Stock Reconciliation":
		# Same single warehouse for both fields -- a reconciliation only ever
		# touches one warehouse per row, but (like Stock Entry) can carry a
		# Source Tag (a downward adjustment, against an existing tag) and a
		# Target Tag (an upward adjustment, into a fresh tag) on that same row
		# independently, so both are collected rather than picking just one.
		source_fieldname, _target_fieldname = get_metric_tag_dimension_names()
		to_fieldname = f"to_{source_fieldname}"
		for row in rows:
			warehouse = row.get("warehouse")
			if not warehouse:
				continue
			for tag_fieldname in (source_fieldname, to_fieldname, "reconcile_tag"):
				tag_name = row.get(tag_fieldname)
				if tag_name:
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


def get_reconciled_qty(item_code, warehouse, tag_name):
	"""Net quantity counted into/out of this tag by submitted Stock
	Reconciliations through their Reconcile Tag field. Those rows' Stock Ledger
	Entries carry actual_qty = 0 and no dimension (see doc_hooks.
	stock_reconciliation.validate_reconcile_tags), so the dimension balance
	never includes them."""
	total = frappe.db.sql(
		"""
		select sum(sri.quantity_difference)
		from `tabStock Reconciliation Item` sri
		where sri.reconcile_tag = %(tag)s
			and sri.item_code = %(item_code)s
			and sri.warehouse = %(warehouse)s
			and sri.docstatus = 1
		""",
		{"tag": tag_name, "item_code": item_code, "warehouse": warehouse},
	)[0][0]
	return flt(total)


def _tag_has_history(tag_name):
	"""Whether any live stock transaction still references this tag."""
	_source_fieldname, dimension_field = get_metric_tag_dimension_names()
	column = frappe.utils.sanitize_column(dimension_field)
	if frappe.db.sql(
		f"""
		select 1 from `tabStock Ledger Entry`
		where is_cancelled = 0 and ({column} = %(tag)s or target_tag = %(tag)s)
		limit 1
		""",  # nosemgrep
		{"tag": tag_name},
	):
		return True
	return bool(frappe.db.exists("Stock Reconciliation Item", {"reconcile_tag": tag_name, "docstatus": 1}))


def sync_metric_tag(tag_name, item_code, warehouse, txn_doctype, txn_name):
	dimension_field = get_metric_tag_dimension_fieldname()
	balance = get_stock_balance_for_dimension(item_code, warehouse, dimension_field, tag_name)
	balance += get_reconciled_qty(item_code, warehouse, tag_name)

	tag = frappe.get_doc("Metric Tag", tag_name)
	tag.current_qty = balance
	tag.item_code = item_code
	tag.warehouse = warehouse
	if balance > 0:
		tag.status = "Active"
	elif txn_doctype == "Stock Reconciliation" and not _tag_has_history(tag_name):
		# Cancelling the reconciliation that first used an Unused tag hands the
		# tag back, instead of burning it as Empty.
		tag.status = "Unused"
	else:
		tag.status = "Empty"
	if balance > 0 and not tag.get("custom_license"):
		# An Unused tag has no License until it first holds stock.
		license = frappe.db.get_value("Warehouse", warehouse, "custom_metrc_license_number")
		if license:
			tag.custom_license = license
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


# ---------------------------------------------------------------------------
# Source Tag / Target Tag on Stock Ledger Entry — mirrors each item row's own
# Source/Target tag onto every Stock Ledger Entry that row produced, so a
# ledger row always shows both ends of a same-transaction move (e.g. a Stock
# Entry transfer row) instead of only the single "Source Tag" value ERPNext's
# own Inventory Dimension framework copies in (leg-matched against whichever
# warehouse that specific SLE belongs to — see get_stock_entry_legs above).
# Registered in hooks.py on_submit, against the same four doctypes as
# sync_metric_tags/sync_package_movements -- and must run before the latter,
# since it reads the Source/Target Tag columns this writes.
# ---------------------------------------------------------------------------

# (source_fieldname, target_fieldname) on each item-row doctype. Purchase
# Receipt Item reverses the usual pairing: its plain source_fieldname sits
# next to the *receiving* warehouse field (this doc's primary warehouse is
# the target, not the source), so it holds the Target tag there and
# "from_"+source_fieldname (next to from_warehouse) holds the Source tag.
# Stock Reconciliation Item touches only one warehouse, but (like Stock
# Entry) still carries both a Source and a Target tag field on the same row
# -- Source for a downward adjustment, Target for an upward one.
#
# Built from get_metric_tag_dimension_names() rather than hardcoded "muid"/
# "to_muid" literals -- those are only the *fallback* dimension names; a site
# can (and this one does) configure the Muid Inventory Dimension with a
# different source_fieldname (e.g. "tags"), and every row here carries that
# fieldname, never literally "muid". Hardcoding it left this whole lookup
# returning (None, None) for every row, so sync_sle_source_target_tags below
# silently wrote nothing.
def _row_source_target_fields(row_doctype):
	source_fieldname, _target_fieldname = get_metric_tag_dimension_names()
	to_fieldname = f"to_{source_fieldname}"
	from_fieldname = f"from_{source_fieldname}"
	mapping = {
		"Stock Entry Detail": (source_fieldname, to_fieldname),
		"Delivery Note Item": (source_fieldname, to_fieldname),
		"Purchase Receipt Item": (from_fieldname, source_fieldname),
		"Stock Reconciliation Item": (source_fieldname, to_fieldname),
	}
	return mapping.get(row_doctype, (None, None))


def _row_source_target_tags(voucher_doctype, row):
	if row.get("reconcile_tag"):
		# Only the plain Target Tag column, never the dimension column: a
		# dimension on this SLE would make a repost treat it as additive.
		return None, row.reconcile_tag

	source_field, target_field = _row_source_target_fields(row.doctype)
	source_value = row.get(source_field) if source_field else None
	target_value = row.get(target_field) if target_field else None

	if voucher_doctype == "Purchase Receipt" and not source_value and not target_value:
		# Neither tag is linked yet — typically stock received from an
		# external vendor whose packages aren't registered as Metric Tags
		# here. Fall back to whatever the receiving clerk typed into Source
		# Package, so the ledger still carries something to trace the lot to,
		# even though it isn't a real Metric Tag reference.
		source_value = row.get("custom_source_package") or None

	return source_value, target_value


def sync_sle_source_target_tags(doc, method=None):
	"""on_submit hook — write each item row's Source/Target tag onto every
	Stock Ledger Entry that row produced.

	"Source Tag" is the Muid Inventory Dimension's own target_fieldname
	("metric_tag" — see get_metric_tag_dimension_names), just relabelled;
	"Target Tag" ("target_tag") is a plain field this app added alongside it.
	"""
	_, sle_source_fieldname = get_metric_tag_dimension_names()

	for row in doc.get("items") or []:
		source_value, target_value = _row_source_target_tags(doc.doctype, row)
		if not source_value and not target_value:
			continue

		# Only write the side that actually has a value. A single-leg row
		# (plain issue or plain receipt) always leaves the other side None --
		# writing that None here would blank out sle_source_fieldname
		# ("metric_tag"), which ERPNext's own Inventory Dimension framework
		# already populated natively (from whichever leg-matched field it
		# reads for that SLE) before this hook ever runs. Only a same-row
		# transfer (both legs on one row) has both values, and both are then
		# genuinely meant to land on the SLE.
		values = {}
		if source_value:
			values[sle_source_fieldname] = source_value
		if target_value:
			values["target_tag"] = target_value

		frappe.db.set_value(
			"Stock Ledger Entry",
			{
				"voucher_type": doc.doctype,
				"voucher_no": doc.name,
				"voucher_detail_no": row.name,
				"is_cancelled": 0,
			},
			values,
			update_modified=False,
		)


# ---------------------------------------------------------------------------
# Scan-to-select — lets the standard "Scan Barcode" field on the item table of
# any Metric-Tag-tracked transaction (see cannabis_management/public/js/
# metric_tag_scan.js) accept a Metric Tag's Tag Code or MUID instead of a
# barcode, and open a picker of what is currently in stock under that tag.
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_metric_tag_scan(search_value, child_doctype=None):
	"""Resolve `search_value` to a Metric Tag and list what is in stock under it.

	A physical tag can be reused over its lifetime, so more than one
	item/strain(batch) combination can legitimately come back for the same
	tag — the caller is expected to let the user choose when there is more
	than one row.

	`child_doctype` (the caller's item-table row doctype, e.g. "Purchase
	Receipt Item") is optional but lets the response carry the *actual*
	fieldname to write the tag into on that row — see get_row_tag_fieldname's
	docstring for why that can't just be assumed from the dimension name.
	"""
	search_value = (search_value or "").strip()
	if not search_value:
		return {"found": False}

	# Deliberately no Metric Tag permission gate beyond the @frappe.whitelist()
	# login requirement (matching erpnext.stock.utils.scan_barcode, which this
	# sits alongside): staff who can create a Purchase Receipt/Delivery
	# Note/etc. but don't hold the "Stock User" role that carries Metric Tag
	# read access still need this to work on every scan — real users on this
	# site (e.g. front-line receiving staff) hit exactly that gap. Throwing
	# PermissionError here would silently break normal barcode scanning too,
	# since the client falls through to it for every scan, not just tag ones.
	tag_name = frappe.db.exists("Metric Tag", search_value) or frappe.db.get_value(
		"Metric Tag", {"muid": search_value}
	)
	if not tag_name:
		return {"found": False}

	source_fieldname, dimension_field = get_metric_tag_dimension_names()
	column = frappe.utils.sanitize_column(dimension_field)

	rows = frappe.db.sql(
		f"""
		select item_code, warehouse, batch_no, stock_uom as uom, sum(actual_qty) as qty
		from `tabStock Ledger Entry`
		where {column} = %(tag)s and is_cancelled = 0
		group by item_code, warehouse, batch_no
		having sum(actual_qty) > 0.0000001
		order by item_code, warehouse
		""",  # nosemgrep
		{"tag": tag_name},
		as_dict=True,
	)

	if not rows:
		# Nothing in the Stock Ledger yet under this dimension (e.g. the tag
		# was just registered) — fall back to the cached snapshot on the tag.
		cached = frappe.db.get_value(
			"Metric Tag", tag_name, ["item_code", "warehouse", "current_qty", "uom"], as_dict=True
		)
		if cached and cached.item_code and flt(cached.current_qty) > 0:
			rows = [
				{
					"item_code": cached.item_code,
					"warehouse": cached.warehouse,
					"batch_no": None,
					"uom": cached.uom,
					"qty": cached.current_qty,
				}
			]

	for row in rows:
		row["item_name"] = frappe.db.get_value("Item", row["item_code"], "item_name")
		row["strain"] = (
			frappe.db.get_value("Batch", row["batch_no"], "custom_strain_name") if row.get("batch_no") else None
		)

	return {
		"found": True,
		"tag_name": tag_name,
		"dimension_fieldname": dimension_field,
		"source_fieldname": source_fieldname,
		"row_tag_fieldname": get_row_tag_fieldname(child_doctype) if child_doctype else None,
		"rows": rows,
	}
