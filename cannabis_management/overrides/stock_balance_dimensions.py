"""Stock Balance, dimension-wise: drain Batch (project) stock that left untagged.

The Batch inventory dimension writes into the ledger's `project` field. Stock is
tagged with a Batch when it is made or received, but nearly every Delivery Note,
Sales Invoice and outgoing Stock Entry leaves the Batch blank. The standard report
buckets each ledger row by its own tag, so a Batch's stock goes in and never comes
out: the Batch row keeps its old quantity forever while the blank row runs
negative — stock shown under a Batch that is no longer on the shelf.

The core report also mis-reads Stock Reconciliations in this mode. Their ledger
rows carry the warehouse's new total (qty_after_transaction) and the report
subtracts the *bucket's* balance from it, so one bucket absorbs the whole
warehouse's stock.

In dimension-wise mode this replaces the bucketing:

- Each item + warehouse holds its stock as FIFO layers, one per receipt, each
  carrying that receipt's Batch.
- An outgoing row that names a Batch takes from that Batch's layers first.
- An outgoing row with no Batch takes from the oldest layers — the oldest stock
  is assumed to leave first. So does anything a tagged row takes beyond what its
  Batch actually holds in that warehouse.
- A Stock Reconciliation moves the warehouse to its counted total; the
  difference is the movement, and a shortfall comes off the oldest layers.
- A Stock Entry transfer that arrives untagged carries the Batches its outgoing
  half was taken from, so a Batch keeps its identity across warehouses.
- Stock that went out before it was booked in (backdated entries) is a
  shortfall on the outgoing row's tag; the next receipt fills it first.

Every unit is still counted exactly once, so each item + warehouse total matches
the plain report — only which Batch a unit sits under changes. Without a
dimension filter or "Show Dimension Wise Stock" the core report runs untouched.
"""

from collections import defaultdict, deque

import frappe
from frappe.utils import flt

from erpnext.stock.report.stock_balance import stock_balance as _core

_Report = _core.StockBalanceReport
_original_get_item_warehouse_map = _Report.get_item_warehouse_map
_original_apply_dimension_filters = _Report.apply_inventory_dimensions_filters

# Below this a quantity is rounding noise, not stock.
EPSILON = 1e-6


def apply(**kwargs):
	"""Install the override once per process (before_request / before_job hook)."""
	if getattr(_Report, "_cannabis_dimension_fix", False):
		return
	_Report.apply_inventory_dimensions_filters = _apply_inventory_dimensions_filters
	_Report.get_item_warehouse_map = _get_item_warehouse_map
	_Report._cannabis_dimension_fix = True


def _dimension_mode(report):
	return bool(report.filters.get("show_dimension_wise_stock")) or any(
		report.filters.get(fieldname) for fieldname in report.inventory_dimensions
	)


def _apply_inventory_dimensions_filters(self, query, sle):
	if not _dimension_mode(self):
		return _original_apply_dimension_filters(self, query, sle)

	# Read every row, not only the filtered Batch's: the untagged outgoing rows are
	# what drain a Batch. The filter is applied to the result instead.
	for fieldname in self.inventory_dimensions:
		query = query.select(fieldname)
	return query.select(sle.voucher_detail_no)


def _get_item_warehouse_map(self):
	if not _dimension_mode(self):
		return _original_get_item_warehouse_map(self)

	item_warehouse_map = {}
	self.opening_vouchers = self.get_opening_vouchers()
	ledger = _Ledger(self.inventory_dimensions)
	for opening in self.opening_data.values():
		ledger.seed(opening)

	if self.filters.get("show_stock_ageing_data"):
		self.sle_entries = self.sle_query.run(as_dict=True)

	# Kept from core: warms the cache so flt() doesn't query inside the unbuffered cursor.
	_system_settings = frappe.get_cached_doc("System Settings")
	with frappe.db.unbuffered_cursor():
		if not self.filters.get("show_stock_ageing_data"):
			self.sle_entries = self.sle_query.run(as_dict=True, as_iterator=True)

		for entry in self.sle_entries:
			for dims, qty_diff, value_diff in ledger.post(entry):
				row = frappe._dict(entry)
				row.update(zip(self.inventory_dimensions, dims))

				group_by_key = self.get_group_by_key(row)
				if group_by_key not in item_warehouse_map:
					self.initialize_data(item_warehouse_map, group_by_key, row)
				_accumulate(self, item_warehouse_map[group_by_key], row, qty_diff, value_diff)

				if self.opening_data.get(group_by_key):
					del self.opening_data[group_by_key]

	for group_by_key, entry in self.opening_data.items():
		if group_by_key not in item_warehouse_map:
			self.initialize_data(item_warehouse_map, group_by_key, entry)

	item_warehouse_map = _keep_filtered_dimensions(self, item_warehouse_map)
	return _core.filter_items_with_no_transactions(
		item_warehouse_map, self.float_precision, self.inventory_dimensions
	)


def _accumulate(report, qty_dict, row, qty_diff, value_diff):
	"""Core's prepare_item_warehouse_map, with the movement already worked out."""
	for fieldname in report.inventory_dimensions:
		qty_dict[fieldname] = row.get(fieldname)

	if row.posting_date < report.from_date or row.voucher_no in report.opening_vouchers.get(
		row.voucher_type, []
	):
		qty_dict.opening_qty += qty_diff
		qty_dict.opening_val += value_diff

	elif row.posting_date <= report.to_date:
		if flt(qty_diff, report.float_precision) >= 0:
			qty_dict.in_qty += qty_diff
		else:
			qty_dict.out_qty += abs(qty_diff)

		if flt(value_diff, report.float_precision) >= 0:
			qty_dict.in_val += value_diff
		else:
			qty_dict.out_val += abs(value_diff)

	qty_dict.val_rate = row.valuation_rate
	qty_dict.bal_qty += qty_diff
	qty_dict.bal_val += value_diff


def _keep_filtered_dimensions(report, item_warehouse_map):
	wanted = {}
	for fieldname in report.inventory_dimensions:
		value = report.filters.get(fieldname)
		if value:
			wanted[fieldname] = set(value if isinstance(value, list | tuple) else [value])

	if not wanted:
		return item_warehouse_map

	return {
		key: qty_dict
		for key, qty_dict in item_warehouse_map.items()
		if all(qty_dict.get(fieldname) in values for fieldname, values in wanted.items())
	}


class _Ledger:
	"""Per item + warehouse: the running quantity and FIFO layers of [dims, qty]."""

	def __init__(self, dimensions):
		self.dimensions = dimensions
		self.blank = (None,) * len(dimensions)
		self.qty = defaultdict(float)
		self.layers = defaultdict(deque)
		# [dims, qty] taken out with no stock behind it, oldest first.
		self.short = defaultdict(deque)
		# (voucher_no, voucher_detail_no) -> [(dims, qty)] the outgoing half of a
		# Stock Entry row took, for its incoming half to carry.
		self.transfers = {}

	def _dims(self, row):
		return tuple(row.get(fieldname) or None for fieldname in self.dimensions)

	def seed(self, opening):
		base = (opening.get("company"), opening.get("item_code"), opening.get("warehouse"))
		qty = flt(opening.get("bal_qty"))
		self.qty[base] += qty
		if qty > EPSILON:
			self.layers[base].append([self._dims(opening), qty])

	def post(self, entry):
		"""Split one ledger row into (dims, qty, value) movements."""
		base = (entry.company, entry.item_code, entry.warehouse)
		dims = self._dims(entry)
		layers = self.layers[base]

		if entry.voucher_type == "Stock Reconciliation" and (not entry.batch_no or entry.serial_no):
			qty = flt(entry.qty_after_transaction) - self.qty[base]
		else:
			qty = flt(entry.actual_qty)
		value = flt(entry.stock_value_difference)
		self.qty[base] += qty

		if qty > EPSILON:
			parts = [(dims, qty)]
			carried = self.transfers.pop((entry.voucher_no, entry.voucher_detail_no), None)
			if dims == self.blank and entry.voucher_type == "Stock Entry" and carried:
				parts = _rescale(carried, qty) or parts
			moved = []
			for d, q in parts:
				q = self._fill_shortfall(base, q, moved)
				if q > EPSILON:
					layers.append([d, q])
					moved.append((d, q))
			return _spread(_merge(moved), value)

		if qty < -EPSILON:
			taken = self._take(base, layers, -qty, dims)
			if entry.voucher_type == "Stock Entry":
				self.transfers[(entry.voucher_no, entry.voucher_detail_no)] = taken
			return _spread([(d, -q) for d, q in taken], value)

		# No quantity moved — a revaluation. Its value belongs to what is on hand.
		if abs(value) > EPSILON and layers:
			on_hand = _merge((d, q) for d, q in layers)
			return [(d, 0.0, v) for d, _q, v in _spread(on_hand, value)]
		return [(dims, 0.0, value)]

	def _take(self, base, layers, need, dims):
		"""Remove `need` from the layers: a tagged row from its own Batch first, then
		oldest first. Whatever the layers can't cover (negative stock) stays with the
		row's own tag as a shortfall."""
		taken = []
		if dims != self.blank:
			need = _drain(layers, need, taken, lambda d: d == dims)
		need = _drain(layers, need, taken, lambda d: True)
		if need > EPSILON:
			taken.append((dims, need))
			self.short[base].append([dims, need])
		return _merge(taken)

	def _fill_shortfall(self, base, qty, moved):
		"""Put incoming `qty` back under the tags that went short; return what's left."""
		short = self.short[base]
		while qty > EPSILON and short:
			gap = short[0]
			fill = min(gap[1], qty)
			moved.append((gap[0], fill))
			gap[1] -= fill
			qty -= fill
			if gap[1] <= EPSILON:
				short.popleft()
		return qty


def _drain(layers, need, taken, match):
	for layer in layers:
		if need <= EPSILON:
			break
		if layer[1] <= EPSILON or not match(layer[0]):
			continue
		qty = min(layer[1], need)
		layer[1] -= qty
		need -= qty
		taken.append((layer[0], qty))

	remaining = [layer for layer in layers if layer[1] > EPSILON]
	layers.clear()
	layers.extend(remaining)
	return need


def _merge(parts):
	merged = {}
	for dims, qty in parts:
		merged[dims] = merged.get(dims, 0.0) + qty
	return list(merged.items())


def _rescale(parts, qty):
	total = sum(q for _d, q in parts)
	return [(d, qty * q / total) for d, q in parts] if total > EPSILON else []


def _spread(parts, value):
	"""Attach each part's share of the row's value, in proportion to its quantity."""
	total = sum(abs(q) for _d, q in parts)
	if total <= EPSILON:
		return [(d, q, value / len(parts)) for d, q in parts]
	return [(d, q, value * abs(q) / total) for d, q in parts]
