"""Stock Reconciliation Item: the same Inventory Dimension layout as Stock Entry.

A Stock Entry row shows every dimension twice -- Source on the left, Target
on the right -- because ERPNext creates a "to_" field for each dimension on a
doctype with a target warehouse. Stock Reconciliation has one warehouse per
row, so it only ever got the source fields, and Target Tags was bolted on
underneath them. This lays the row out like Stock Entry: Source Brand /
Source Tags / Source Batch, a column break, then Target Brand / Target Tags /
Target Batch.

The Metrc Tag hooks already read both Source and Target Tags on a
reconciliation row (see metric_tag.get_touched_tags). Target Brand and Target
Batch are recorded on the row only: ERPNext copies just the source
dimensions into the Stock Ledger Entry of a single-warehouse row.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DIMENSION_FIELDS = {
    "Stock Reconciliation Item": [
        {"fieldname": "batch", "label": "Source Batch", "fieldtype": "Link",
         "options": "Project", "insert_after": "inventory_dimension"},
        {"fieldname": "inventory_dimension_col_break", "fieldtype": "Column Break",
         "insert_after": "batch"},
        {"fieldname": "to_batch", "label": "Target Batch", "fieldtype": "Link",
         "options": "Project", "insert_after": "inventory_dimension_col_break"},
    ]
}


def install_custom_fields():
    """Idempotent; re-asserted on every migrate via after_migrate."""
    create_custom_fields(DIMENSION_FIELDS, update=True)


# ---------------------------------------------------------------------------
# Source Tag vs Target Tag on a reconciliation row.
#
# ERPNext refuses a Stock Reconciliation that carries an inventory dimension on
# a row which already has stock (StockReconciliation.validate_inventory_dimension):
# a reconciliation asserts an ABSOLUTE balance for item + warehouse, and the
# balance it computes ignores dimensions — so adjusting one tag would restate
# the whole item/warehouse position and quietly wipe the other tags' stock.
# That check is worth keeping.
#
# It only looks at the dimension's own source_fieldname ("tags"), which on this
# app's layout means SOURCE Tags — the downward-adjustment field. An upward
# adjustment belongs in TARGET Tags ("to_tags"), which ERPNext never copies into
# the Stock Ledger Entry as a dimension, so it does not distort any balance.
# metric_tag.get_touched_tags reads both fields, so the Metrc Tag status sync
# and the Metrc Package movements still see the tag either way.
#
# So: an increase filed against Source Tags is simply in the wrong box, and is
# moved. A decrease is the case ERPNext is actually protecting against, and gets
# an explanation of what to use instead rather than core's opaque wording.
# ---------------------------------------------------------------------------

import frappe
from frappe import _
from frappe.utils import flt


def resolve_tag_direction(doc):
	"""Called from CMStockReconciliation.validate_inventory_dimension."""
	from metrc_customizations.metrc_customizations.doctype.metrc_tag.metrc_tag import (
		get_metric_tag_dimension_names,
	)

	source_field, _target = get_metric_tag_dimension_names()
	target_field = f"to_{source_field}"

	moved = []
	for row in doc.items:
		tag = row.get(source_field)
		if not tag:
			continue

		# No existing stock: this is an opening entry, which ERPNext allows.
		if not flt(row.current_qty):
			continue

		if flt(row.qty) >= flt(row.current_qty):
			if row.get(target_field):
				continue  # both filled — leave it alone and let core speak
			row.set(target_field, tag)
			row.set(source_field, None)
			moved.append((row.idx, tag))
		else:
			frappe.throw(
				_(
					"Row #{0}: {1} is in <b>Source Tags</b>, and this row reduces stock "
					"from {2} to {3}. A Stock Reconciliation sets the total balance for the "
					"item and warehouse and cannot take stock off one tag without restating "
					"the others.<br><br>To reduce a tagged package, use "
					"<b>Stock Entry &rarr; Material Issue</b> against that tag instead. "
					"To count stock <i>into</i> a tag here, put it in <b>Target Tags</b>."
				).format(row.idx, frappe.bold(tag), flt(row.current_qty), flt(row.qty)),
				title=_("Use Target Tags, or a Material Issue"),
			)

	if moved:
		lines = "".join(
			f"<li>Row #{idx}: {frappe.bold(tag)}</li>" for idx, tag in moved
		)
		frappe.msgprint(
			_(
				"Moved to <b>Target Tags</b> — this row adds stock, and Source Tags is for "
				"reductions:<ul>{0}</ul>"
			).format(lines),
			title=_("Metrc Tag moved"),
			indicator="blue",
		)


# ---------------------------------------------------------------------------
# Reconcile Tag: one field that is a Source or a Target tag depending on the
# tag picked.
#
#   - Active tag already holding this item  -> "Source": the tag's quantity is
#     adjusted by the row's quantity_difference, on its existing Metrc Package.
#   - Unused tag                            -> "Target": the difference is
#     counted into the tag, which goes Active and gets a new Metrc Package.
#
# The tag is deliberately kept out of the Muid dimension fields (Source/Target
# Tags). A dimension on a reconciliation row turns its qty into an additive
# opening quantity (see StockReconciliation.get_sle_for_items), and a
# reconciliation's Stock Ledger Entries always carry actual_qty = 0, so
# neither the dimension balance nor the package sync could see the change.
# The tag's quantity is taken from quantity_difference instead -- see
# metric_tag.get_reconciled_qty and metrc_package.sync_package_movements.
# ---------------------------------------------------------------------------


def clear_superseded_tag_fields(doc):
	"""A row with a Reconcile Tag must not also carry Source/Target Tags, or the
	tag would be counted twice. Runs before core's validate."""
	from metrc_customizations.metrc_customizations.doctype.metrc_tag.metrc_tag import (
		get_metric_tag_dimension_names,
	)

	source_field, _target = get_metric_tag_dimension_names()
	for row in doc.items:
		if row.get("reconcile_tag"):
			row.set(source_field, None)
			row.set(f"to_{source_field}", None)


def validate_reconcile_tags(doc):
	"""Runs after current_qty and quantity_difference are set on every row."""
	seen = set()
	for row in doc.items:
		tag_name = row.get("reconcile_tag")
		if not tag_name:
			row.reconcile_tag_mode = None
			continue

		if tag_name in seen:
			frappe.throw(
				_("Row #{0}: Reconcile Tag {1} is used on more than one row.").format(
					row.idx, frappe.bold(tag_name)
				)
			)
		seen.add(tag_name)

		tag = frappe.db.get_value(
			"Metrc Tag", tag_name, ["status", "item_code", "warehouse", "current_qty"], as_dict=True
		)
		diff = flt(row.qty) - flt(row.current_qty)

		if tag.status == "Used" and flt(tag.current_qty) > 0:
			if tag.item_code and tag.item_code != row.item_code:
				frappe.throw(
					_("Row #{0}: Reconcile Tag {1} holds {2}, not {3}.").format(
						row.idx, frappe.bold(tag_name), frappe.bold(tag.item_code), frappe.bold(row.item_code)
					)
				)
			if tag.warehouse and tag.warehouse != row.warehouse:
				frappe.throw(
					_("Row #{0}: Reconcile Tag {1} is in {2}, not {3}.").format(
						row.idx, frappe.bold(tag_name), frappe.bold(tag.warehouse), frappe.bold(row.warehouse)
					)
				)
			if flt(tag.current_qty) + diff < 0:
				frappe.throw(
					_(
						"Row #{0}: this row reduces stock by {1}, but Reconcile Tag {2} only holds {3}."
					).format(row.idx, abs(diff), frappe.bold(tag_name), flt(tag.current_qty))
				)
			row.reconcile_tag_mode = "Source"
		elif tag.status == "Received":
			if diff <= 0:
				frappe.throw(
					_(
						"Row #{0}: Reconcile Tag {1} is Received (not used yet), so this row must add stock. "
						"Quantity ({2}) has to be more than the current quantity in the warehouse ({3}); "
						"the difference is what goes into the new tag."
					).format(row.idx, frappe.bold(tag_name), flt(row.qty), flt(row.current_qty))
				)
			row.reconcile_tag_mode = "Target"
		else:
			frappe.throw(
				_("Row #{0}: Reconcile Tag {1} is {2}. Pick an Active tag holding this item, or an Unused tag.").format(
					row.idx, frappe.bold(tag_name), tag.status
				)
			)
