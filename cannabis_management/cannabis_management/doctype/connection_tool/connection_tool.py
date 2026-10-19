# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Break and make the links other documents hold to one document.

Frappe will not cancel a document while a submitted document links to it (and
ERPNext also refuses while a draft Sales Invoice does). This tool lists those
back-links, clears them so the cancel goes through, and later points them again
at the same document or at its amended copy. Item-row references such as
Delivery Note Item.so_detail are cleared and restored together with the link,
and the delivered / billed totals of the orders involved are recomputed.
"""

import json
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.dynamic_links import get_dynamic_link_map
from frappe.model.rename_doc import get_link_fields
from frappe.utils import cint, get_link_to_form

# Ledger rows must keep pointing at the voucher that posted them; the rest are
# cancelled or ignored by the document's own on_cancel.
SKIP_DOCTYPES = {
	"GL Entry",
	"Stock Ledger Entry",
	"Payment Ledger Entry",
	"Advance Payment Ledger Entry",
	"Unreconcile Payment",
	"Unreconcile Payment Entries",
	"Repost Item Valuation",
	"Repost Payment Ledger",
	"Repost Accounting Ledger",
	"Stock Reservation Entry",
	"Serial and Batch Bundle",
	"Connection Tool",
	"Connection Tool Link",
}

# Payment allocations are mirrored in the payment ledger, so clearing them here
# would leave the ledger pointing at the order. They are listed, never touched.
LOCKED_TABLES = {
	"Payment Entry Reference",
	"Journal Entry Account",
	"Sales Invoice Advance",
	"Purchase Invoice Advance",
}
LOCKED_NOTE = (
	"Payment allocation, not changed by this tool. ERPNext unlinks it on cancel when Accounts Settings > "
	"Unlink Advance Payment on Cancellation of Order is ticked; otherwise use Payment Reconciliation."
)

MAX_ROWS = 500
DOCSTATUS_LABEL = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


class ConnectionTool(Document):
	def validate(self):
		self.guard_broken_rows()
		self.reference_docstatus = docstatus_label(self.reference_doctype, self.reference_name)
		if self.is_new() and not self.links:
			self.scan()
		self.set_status()

	def guard_broken_rows(self):
		"""A broken row is the only record of where a link pointed, so it may not be dropped."""
		before = self.get_doc_before_save()
		broken = [r for r in before.links if r.status == "Broken"] if before else []
		if not broken:
			return

		if (before.reference_doctype, before.reference_name) != (self.reference_doctype, self.reference_name):
			frappe.throw(_("Make the broken connections again before changing the document."))

		kept = {r.name for r in self.links}
		for r in broken:
			if r.name not in kept:
				frappe.throw(
					_("Row {0} ({1} {2}) is broken. Make it again before removing it.").format(
						r.idx, r.linked_doctype, r.linked_name
					)
				)

	def scan(self):
		"""Rebuild the table: every live back-link, plus the broken rows still waiting to be made again."""
		found = find_back_links(self.reference_doctype, self.reference_name, cint(self.include_cancelled))
		live = {(r["table_doctype"], r["row_name"], r["fieldname"]) for r in found}

		# Relinked rows that now point elsewhere stay as history.
		kept = [
			r
			for r in self.links
			if r.status in ("Broken", "Relinked") and (r.table_doctype, r.row_name, r.fieldname) not in live
		]
		self.set("links", kept)
		for row in found[:MAX_ROWS]:
			self.append("links", row)
		for idx, row in enumerate(self.links, 1):
			row.idx = idx

		if len(found) > MAX_ROWS:
			frappe.msgprint(
				_("Only the first {0} of {1} links are listed.").format(MAX_ROWS, len(found)),
				indicator="orange",
			)

	def set_status(self):
		counts = {}
		for r in self.links:
			counts[r.status] = counts.get(r.status, 0) + 1

		if counts.get("Broken"):
			self.status = "Partially Broken" if counts.get("Linked") else "Broken"
		elif counts.get("Relinked"):
			self.status = "Relinked"
		elif self.links:
			self.status = "Connected"
		else:
			self.status = "No Connections"

	def pick(self, row_names, status):
		wanted = set(row_names or [])
		rows = [r for r in self.links if r.status == status and (not wanted or r.name in wanted)]
		if not rows:
			frappe.throw(_("No rows with status {0} selected.").format(_(status)))
		return rows

	def break_links(self, row_names=None):
		rows = self.pick(row_names, "Linked")
		warnings, done = [], []

		for (parent_dt, parent_name), group in group_by_parent(rows).items():
			changed = []
			with totals_in_sync(parent_dt, parent_name, warnings):
				for r in group:
					current = read_row(r)
					if not current or current.get(r.fieldname) != self.reference_name:
						warnings.append(
							_("{0} {1} row {2}: {3} no longer points at {4}, skipped.").format(
								r.linked_doctype, r.linked_name, r.row_idx or "-", r.fieldname, self.reference_name
							)
						)
						continue

					values = {r.fieldname: None}
					values.update(dict.fromkeys(json.loads(r.detail_refs or "{}"), None))
					frappe.db.set_value(r.table_doctype, r.row_name, values, update_modified=False)
					r.status, r.current_value = "Broken", None
					changed.append(r)

			if changed:
				done += changed
				add_info_comment(
					parent_dt,
					parent_name,
					_("Link to {0} {1} removed ({2}) by Connection Tool {3}.").format(
						_(self.reference_doctype),
						get_link_to_form(self.reference_doctype, self.reference_name),
						describe_fields(changed),
						get_link_to_form(self.doctype, self.name),
					),
				)
				frappe.clear_document_cache(parent_dt, parent_name)

		if done:
			add_info_comment(
				self.reference_doctype,
				self.reference_name,
				_("{0} link(s) to this document removed by Connection Tool {1}.").format(
					len(done), get_link_to_form(self.doctype, self.name)
				),
			)
		self.save()
		report(_("Broke {0} connection(s).").format(len(done)), warnings)

	def make_links(self, row_names=None):
		rows = self.pick(row_names, "Broken")
		target = self.relink_to or self.reference_name
		target_docstatus = frappe.db.get_value(self.reference_doctype, target, "docstatus")
		if target_docstatus is None:
			frappe.throw(_("{0} {1} not found.").format(_(self.reference_doctype), target))

		remap = target != self.reference_name
		target_rows = child_rows(self.reference_doctype, target) if remap else {}

		# Work out every value first so nothing is written unless all rows can be made.
		plan, errors = [], []
		for r in rows:
			if target_docstatus == 2 and frappe.db.get_value(r.linked_doctype, r.linked_name, "docstatus") == 1:
				errors.append(
					_("{0} {1} is submitted and {2} is cancelled. Set Relink To to the amended document.").format(
						r.linked_doctype, r.linked_name, target
					)
				)
				continue

			values = {r.fieldname: target}
			if r.link_type == "Dynamic Link":
				values[r.type_fieldname] = self.reference_doctype
			for field, ref in json.loads(r.detail_refs or "{}").items():
				values[field] = match_child_row(ref, target_rows) if remap else ref["value"]
				if not values[field]:
					errors.append(
						_("{0} {1} row {2}: {3} has no row matching {4} row {5} ({6}).").format(
							r.linked_doctype,
							r.linked_name,
							r.row_idx or "-",
							target,
							ref["child_doctype"],
							ref["idx"],
							ref.get("item_code") or "-",
						)
					)
			plan.append((r, values))

		if errors:
			frappe.throw("<br>".join(errors), title=_("Cannot make connections"))

		warnings, done = [], []
		for (parent_dt, parent_name), group in group_by_parent(plan, key=lambda p: p[0]).items():
			changed = []
			with totals_in_sync(parent_dt, parent_name, warnings):
				for r, values in group:
					current = read_row(r)
					if not current:
						warnings.append(
							_("{0} {1} row {2} no longer exists, skipped.").format(
								r.linked_doctype, r.linked_name, r.row_idx or "-"
							)
						)
						continue
					if current.get(r.fieldname):
						warnings.append(
							_("{0} {1} row {2}: {3} already points at {4}, skipped.").format(
								r.linked_doctype, r.linked_name, r.row_idx or "-", r.fieldname, current[r.fieldname]
							)
						)
						continue

					frappe.db.set_value(r.table_doctype, r.row_name, values, update_modified=False)
					r.status = "Relinked" if remap else "Linked"
					r.current_value = target
					changed.append(r)

			if changed:
				done += changed
				add_info_comment(
					parent_dt,
					parent_name,
					_("Linked to {0} {1} ({2}) by Connection Tool {3}.").format(
						_(self.reference_doctype),
						get_link_to_form(self.reference_doctype, target),
						describe_fields(changed),
						get_link_to_form(self.doctype, self.name),
					),
				)
				frappe.clear_document_cache(parent_dt, parent_name)

		if done:
			add_info_comment(
				self.reference_doctype,
				target,
				_("{0} link(s) made to this document by Connection Tool {1}.").format(
					len(done), get_link_to_form(self.doctype, self.name)
				),
			)
		self.save()
		report(_("Made {0} connection(s) to {1}.").format(len(done), target), warnings)


def find_back_links(doctype, name, include_cancelled=False):
	"""Every field in another document that points at doctype/name, one dict per row and field."""
	skip = SKIP_DOCTYPES | set(frappe.get_hooks("ignore_links_on_delete"))
	target_rows = child_rows(doctype, name)

	sources = [
		(lf["parent"], lf["fieldname"], None)
		for lf in get_link_fields(doctype)
		if not lf["issingle"] and lf["fieldname"] != "amended_from"
	]
	sources += [(df.parent, df.fieldname, df.options) for df in get_dynamic_link_map().get(doctype, [])]

	found, seen = [], set()
	for table, fieldname, type_field in sources:
		if table in skip or (table, fieldname) in seen:
			continue
		seen.add((table, fieldname))

		meta = get_meta_or_none(table)
		if not meta or meta.issingle or not frappe.db.has_column(table, fieldname):
			continue

		filters = {fieldname: name, "docstatus": ("<=", 2 if include_cancelled else 1)}
		if type_field:
			filters[type_field] = doctype
		ref_fields = row_reference_fields(meta, fieldname, target_rows)
		fields = ["name", "docstatus", *ref_fields]
		if meta.istable:
			fields += ["parent", "parenttype", "idx"]

		for d in frappe.get_all(table, filters=filters, fields=fields, limit=MAX_ROWS + 1):
			parent_dt = d.parenttype if meta.istable else table
			parent_name = d.parent if meta.istable else d.name
			if not parent_dt or not parent_name or parent_dt in skip:
				continue
			if parent_dt == doctype and parent_name == name:
				continue

			refs = {f: target_rows[d[f]] for f in ref_fields if d.get(f) in target_rows}
			locked = table in LOCKED_TABLES
			found.append(
				{
					"linked_doctype": parent_dt,
					"linked_name": parent_name,
					"linked_docstatus": docstatus_text(parent_dt, d.docstatus),
					"status": "Locked" if locked else "Linked",
					"table_doctype": table,
					"row_name": d.name,
					"row_idx": d.get("idx"),
					"fieldname": fieldname,
					"link_type": "Dynamic Link" if type_field else "Link",
					"type_fieldname": type_field,
					"original_value": name,
					"current_value": name,
					"detail_fields": ", ".join(refs),
					"detail_refs": json.dumps(refs) if refs else None,
					"note": LOCKED_NOTE if locked else blocking_note(doctype, parent_dt, d.docstatus),
				}
			)
	return found


def child_rows(doctype, name):
	"""Item rows of doctype/name keyed by row name, with what is needed to find the same row in an amendment."""
	rows = {}
	for df in frappe.get_meta(doctype).get_table_fields():
		child_meta = get_meta_or_none(df.options)
		if not child_meta or child_meta.get("is_virtual"):
			continue
		fields = ["name", "idx"] + (["item_code"] if child_meta.has_field("item_code") else [])
		for d in frappe.get_all(
			df.options,
			filters={"parent": name, "parenttype": doctype, "parentfield": df.fieldname},
			fields=fields,
		):
			rows[d.name] = {
				"value": d.name,
				"child_doctype": df.options,
				"parentfield": df.fieldname,
				"idx": d.idx,
				"item_code": d.get("item_code"),
			}
	return rows


def row_reference_fields(meta, link_field, target_rows):
	"""Fields that may hold the name of one of the target's item rows (so_detail, sales_order_item ...)."""
	if not target_rows:
		return []
	child_doctypes = {r["child_doctype"] for r in target_rows.values()}
	return [
		df.fieldname
		for df in meta.fields
		if df.fieldname != link_field
		and not df.get("is_virtual")
		and (df.fieldtype == "Data" or (df.fieldtype == "Link" and df.options in child_doctypes))
		and frappe.db.has_column(meta.name, df.fieldname)
	]


def match_child_row(ref, target_rows):
	"""The amended document's row standing in for ref: same table and position, else the only row with that item."""
	same_table = [
		r
		for r in target_rows.values()
		if r["child_doctype"] == ref["child_doctype"] and r["parentfield"] == ref["parentfield"]
	]
	for r in same_table:
		if r["idx"] == ref["idx"] and r["item_code"] == ref.get("item_code"):
			return r["value"]
	same_item = [r for r in same_table if ref.get("item_code") and r["item_code"] == ref["item_code"]]
	return same_item[0]["value"] if len(same_item) == 1 else None


@contextmanager
def totals_in_sync(doctype, name, warnings):
	"""Recompute the delivered / billed quantities and reserved stock this document feeds.

	Before the change the document is left out of its orders' totals, as if it were
	cancelled; afterwards it is counted again through the links it has now. Orders it
	was cut from lose its quantities and orders it was linked to gain them.
	"""
	before = status_updater_doc(doctype, name)
	if before:
		before.docstatus = 2
		run_safely(warnings, before, before.update_qty)
		if consumes_reservations(before):
			before._action = "cancel"
			run_safely(warnings, before, before.update_stock_reservation_entries)

	yield

	if before:
		after = status_updater_doc(doctype, name)
		if after:
			run_safely(warnings, after, after.update_qty)
			if consumes_reservations(after):
				after._action = "submit"
				run_safely(warnings, after, after.update_stock_reservation_entries)
		for doc in (before, after):
			if doc and hasattr(doc, "update_reserved_qty"):
				run_safely(warnings, doc, doc.update_reserved_qty)


def status_updater_doc(doctype, name):
	"""The submitted document set up the way its own on_submit sees it, or None if it feeds no totals."""
	if frappe.db.get_value(doctype, name, "docstatus") != 1:
		return None

	doc = frappe.get_doc(doctype, name)
	if not hasattr(doc, "update_qty"):
		return None

	# Sales / Purchase Invoice returns skip the order totals unless told otherwise.
	for flag in ("update_billed_amount_in_sales_order", "update_billed_amount_in_purchase_order"):
		if doc.meta.has_field(flag) and doc.get("is_return") and not doc.get(flag):
			doc.status_updater = []
	if hasattr(doc, "update_status_updater_args"):
		doc.update_status_updater_args()

	return doc if getattr(doc, "status_updater", None) else None


def consumes_reservations(doc):
	"""Delivery Notes (and stock-updating invoices) mark the order's Stock Reservation Entries delivered."""
	if not hasattr(doc, "update_stock_reservation_entries"):
		return False
	return doc.doctype != "Sales Invoice" or cint(doc.get("update_stock"))


def run_safely(warnings, doc, fn):
	frappe.db.savepoint("connection_tool")
	try:
		fn()
	except Exception as e:
		frappe.db.rollback(save_point="connection_tool")
		frappe.clear_last_message()
		warnings.append(_("Totals from {0} {1} not updated: {2}").format(doc.doctype, doc.name, e))


def read_row(r):
	return frappe.db.get_value(r.table_doctype, r.row_name, [r.fieldname], as_dict=True)


def group_by_parent(items, key=lambda r: r):
	groups = {}
	for item in items:
		row = key(item)
		groups.setdefault((row.linked_doctype, row.linked_name), []).append(item)
	return groups


def describe_fields(rows):
	return ", ".join(
		f"{r.fieldname} (row {r.row_idx})" if r.row_idx else r.fieldname
		for r in rows
	)


def blocking_note(doctype, linked_doctype, docstatus):
	if docstatus == 1:
		return _("Blocks cancel")
	if docstatus == 0 and linked_doctype == "Sales Invoice" and doctype == "Sales Order":
		return _("Draft invoice, blocks cancel")
	return _("Blocks delete only")


def docstatus_text(doctype, docstatus):
	meta = get_meta_or_none(doctype)
	if meta and not meta.is_submittable:
		return "Saved"
	return DOCSTATUS_LABEL.get(cint(docstatus))


def docstatus_label(doctype, name):
	if not (doctype and name):
		return None
	docstatus = frappe.db.get_value(doctype, name, "docstatus")
	return None if docstatus is None else docstatus_text(doctype, docstatus)


def get_meta_or_none(doctype):
	try:
		return frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		# doctype left behind by an uninstalled app's customizations
		frappe.clear_last_message()
		return None


def add_info_comment(doctype, name, text):
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": doctype,
			"reference_name": name,
			"content": text,
		}
	).insert(ignore_permissions=True)


def report(summary, warnings):
	message = summary
	if warnings:
		message += "<br><br>" + "<br>".join(warnings)
	frappe.msgprint(message, title=_("Connection Tool"), indicator="orange" if warnings else "green")


def get_tool(name):
	doc = frappe.get_doc("Connection Tool", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def find_connections(name):
	doc = get_tool(name)
	doc.scan()
	doc.save()


@frappe.whitelist()
def break_connections(name, rows=None):
	get_tool(name).break_links(frappe.parse_json(rows) if rows else None)


@frappe.whitelist()
def make_connections(name, rows=None):
	get_tool(name).make_links(frappe.parse_json(rows) if rows else None)


@frappe.whitelist()
def open_tool(reference_doctype, reference_name):
	"""The tool still holding broken links for this document, or a fresh one."""
	existing = frappe.db.get_value(
		"Connection Tool",
		{
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"status": ("in", ("Broken", "Partially Broken")),
		},
		"name",
		order_by="creation desc",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{"doctype": "Connection Tool", "reference_doctype": reference_doctype, "reference_name": reference_name}
	)
	doc.insert()
	return doc.name


@frappe.whitelist()
def get_latest_amendment(doctype, name):
	frappe.has_permission(doctype, "read", throw=True)
	if not frappe.get_meta(doctype).has_field("amended_from"):
		return None

	latest = name
	for _i in range(50):
		amended = frappe.db.get_value(doctype, {"amended_from": latest}, "name", order_by="creation desc")
		if not amended:
			break
		latest = amended
	return None if latest == name else latest
