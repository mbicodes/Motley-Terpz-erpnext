# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""ERPNext's General Ledger with an Item Group column and filter.

Every step is ERPNext's own report function, so filters, opening, totals and
closing behave exactly as in General Ledger. The only additions sit around
building the result:

* each GL Entry is weighed per item group (what each group's lines are worth
  on that account, debit and credit side apart);
* with the filter set, an entry is cut down to the chosen groups' share
  before opening and totals are computed;
* once ERPNext has built (and, when Consolidated, merged) the rows, each row
  is split into one row per item group, its amounts divided by those
  weights. The last piece takes the rounding, so rows still add up exactly.

GL Entry carries no item, so groups come from the voucher's item lines: a
line's income / expense account, and the stock account its warehouse posts
to (item-group mapping first, then the warehouse account). Stock sides are
weighed by the line's Stock Ledger value, the rest by the line amount. A
Delivery Note's stock GL filed under its Sales Invoice is matched through the
origin voucher stamped on the entry. Two fallbacks cover older postings and
operating costs: an entry on a warehouse's own stock account takes the lines
in that warehouse, and a Stock Entry's additional costs take its finished
items. Entries no item line posts to (receivables, taxes, payments, journals)
stay one row with no item group.
"""

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.nestedset import get_descendants_of

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
from erpnext.accounts.report.general_ledger import general_ledger as gl
from erpnext.stock import get_warehouse_account_map

from cannabis_management.overrides.warehouse_account_utils import resolve_account

# voucher type -> (item table, account fields, warehouse fields)
ITEM_TABLES = {
	"Sales Invoice": ("Sales Invoice Item", ("income_account", "expense_account"), ("warehouse",)),
	"Purchase Invoice": ("Purchase Invoice Item", ("expense_account",), ("warehouse",)),
	"Delivery Note": ("Delivery Note Item", ("expense_account",), ("warehouse", "target_warehouse")),
	"Purchase Receipt": ("Purchase Receipt Item", ("expense_account",), ("warehouse",)),
	"Stock Entry": ("Stock Entry Detail", ("expense_account",), ("s_warehouse", "t_warehouse")),
	"Stock Reconciliation": ("Stock Reconciliation Item", (), ("warehouse",)),
}


def execute(filters=None):
	if not filters:
		return [], []

	account_details = {}
	if filters.get("print_in_account_currency") and not filters.get("account"):
		frappe.throw(_("Select an account to print in account currency"))

	for acc in frappe.db.sql("""select name, is_group from tabAccount""", as_dict=1):
		account_details.setdefault(acc.name, acc)

	if filters.get("party"):
		filters.party = frappe.parse_json(filters.get("party"))
	if filters.get("item_group"):
		filters.item_group = frappe.parse_json(filters.get("item_group"))

	gl.validate_filters(filters, account_details)
	gl.validate_party(filters)
	filters = gl.set_account_currency(filters)

	columns = gl.get_columns(filters)
	idx = next((i for i, c in enumerate(columns) if c.get("fieldname") == "account"), 1)
	columns.insert(idx + 1, {"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Data", "width": 160})

	accounting_dimensions = get_accounting_dimensions() if filters.get("include_dimensions") else []
	gl_entries = gl.get_gl_entries(filters, accounting_dimensions)
	gl_entries = tag_item_groups(gl_entries, filters)
	data = gl.get_data_with_opening_closing(filters, account_details, accounting_dimensions, gl_entries)
	return columns, gl.get_result_as_list(split_rows(data), filters)


AMOUNT_FIELDS = (
	("debit", "credit"),
	("debit_in_account_currency", "credit_in_account_currency"),
	("debit_in_transaction_currency", "credit_in_transaction_currency"),
)


def tag_item_groups(gl_entries, filters):
	"""Give each entry its per-group shares; with the filter, keep only those."""
	if not gl_entries:
		return gl_entries

	origins = {
		r.name: (r.custom_origin_voucher_type, r.custom_origin_voucher_no)
		for r in frappe.get_all(
			"GL Entry",
			filters={"name": ["in", [g.gl_entry for g in gl_entries]], "custom_origin_voucher_no": ["is", "set"]},
			fields=["name", "custom_origin_voucher_type", "custom_origin_voucher_no"],
		)
	}

	def source(gle):
		return origins.get(gle.gl_entry) or (gle.voucher_type, gle.voucher_no)

	vouchers = {}
	for gle in gl_entries:
		vtype, vno = source(gle)
		if vtype in ITEM_TABLES:
			vouchers.setdefault(vtype, set()).add(vno)

	exact, fallback = get_voucher_account_weights(vouchers, filters.get("company"))

	allowed = None
	if filters.get("item_group"):
		allowed = set()
		for g in filters.item_group:
			allowed.add(g)
			allowed.update(get_descendants_of("Item Group", g))

	result = []
	for gle in gl_entries:
		key = (*source(gle), gle.account)
		weights = exact.get(key) or fallback.get(key)
		gle.item_group = None
		gle._shares = None
		if weights:
			gle._shares = {side: shares(weights, side) for side in ("dr", "cr")}
			if len(weights["groups"]) == 1:
				gle.item_group = weights["groups"][0]
		if allowed is not None:
			if not gle._shares or not keep_allowed(gle, allowed):
				continue
		result.append(gle)
	return result


def shares(weights, side):
	"""Fractions per group for one side, falling back to the other, then equal."""
	other = "cr" if side == "dr" else "dr"
	for w in (weights[side], weights[other]):
		total = sum(v for v in w.values() if v > 0)
		if total:
			return {g: w.get(g, 0) / total for g in weights["groups"] if w.get(g, 0) > 0}
	return {g: 1 / len(weights["groups"]) for g in weights["groups"]}


def keep_allowed(gle, allowed):
	"""Cut the entry down to the chosen groups' share. False when nothing is left."""
	for side, pos in (("dr", 0), ("cr", 1)):
		part = {g: f for g, f in gle._shares[side].items() if g in allowed}
		kept = sum(part.values())
		for pair in AMOUNT_FIELDS:
			field = pair[pos]
			if gle.get(field) is not None:
				gle[field] = flt(gle[field]) * kept
		gle._shares[side] = {g: f / kept for g, f in part.items()} if kept else {}
	if not gle._shares["dr"] and not gle._shares["cr"]:
		return False
	groups = set(gle._shares["dr"]) | set(gle._shares["cr"])
	gle.item_group = next(iter(groups)) if len(groups) == 1 else None
	return True


def split_rows(data):
	"""One row per item group; amounts divided by the entry's shares."""
	precision = frappe.get_precision("GL Entry", "debit") or 2
	out = []
	for row in data:
		row_shares = row.pop("_shares", None) if isinstance(row, dict) else None
		if not row_shares:
			out.append(row)
			continue
		groups = list(dict.fromkeys([*row_shares["dr"], *row_shares["cr"]]))
		if len(groups) <= 1:
			row.item_group = groups[0] if groups else row.get("item_group")
			out.append(row)
			continue
		pieces = [frappe._dict(row, item_group=g) for g in groups]
		for side, pos in (("dr", 0), ("cr", 1)):
			fractions = row_shares[side]
			for pair in AMOUNT_FIELDS:
				field = pair[pos]
				total = row.get(field)
				if total is None:
					continue
				remaining = flt(total)
				last = max((i for i, g in enumerate(groups) if fractions.get(g)), default=None)
				for i, g in enumerate(groups):
					if i == last:
						value = remaining
					else:
						value = flt(flt(total) * fractions.get(g, 0), precision)
						remaining -= value
					pieces[i][field] = value
		out += [p for p in pieces if any(flt(p.get(f)) for pair in AMOUNT_FIELDS for f in pair)] or pieces[:1]
	return out


def get_voucher_account_weights(vouchers, company):
	"""(voucher type, voucher no, account) -> {"groups", "dr": {group: w}, "cr": {group: w}}.

	Returns (exact, fallback); fallback is only read when exact has no match.
	"""
	exact, fallback = {}, {}
	warehouse_account = get_warehouse_account_map(company) if company else {}
	ig_cache, wh_map_cache = {}, {}
	finished = {}  # Stock Entry -> [(item group, amount)] of its finished items

	def add(target, key, group, value):
		entry = target.setdefault(key, {"groups": [], "dr": {}, "cr": {}})
		if group not in entry["groups"]:
			entry["groups"].append(group)
		side = "dr" if value >= 0 else "cr"
		entry[side][group] = entry[side].get(group, 0) + abs(flt(value))

	for vtype, names in vouchers.items():
		table, account_fields, warehouse_fields = ITEM_TABLES[vtype]
		meta = frappe.get_meta(table)
		account_fields = [f for f in account_fields if meta.has_field(f)]
		warehouse_fields = [f for f in warehouse_fields if meta.has_field(f)]
		amount_field = "base_net_amount" if meta.has_field("base_net_amount") else "amount"
		extra = [amount_field] + (["is_finished_item"] if vtype == "Stock Entry" else [])
		fields = ", ".join(f"line.`{f}`" for f in account_fields + warehouse_fields + extra)

		sle_value = {}
		for r in frappe.db.sql(
			"""
			SELECT voucher_no, voucher_detail_no, warehouse, SUM(stock_value_difference) AS value
			FROM `tabStock Ledger Entry`
			WHERE voucher_type = %(vtype)s AND voucher_no IN %(names)s AND is_cancelled = 0
			GROUP BY voucher_no, voucher_detail_no, warehouse
			""",
			{"names": list(names), "vtype": vtype},
			as_dict=True,
		):
			sle_value[(r.voucher_no, r.voucher_detail_no, r.warehouse)] = flt(r.value)

		for line in frappe.db.sql(
			f"""
			SELECT line.name, line.parent, line.item_code, item.item_group, {fields}
			FROM `tab{table}` line
			INNER JOIN `tabItem` item ON item.name = line.item_code
			WHERE line.parent IN %(names)s AND line.parenttype = %(vtype)s
			ORDER BY line.idx
			""",
			{"names": list(names), "vtype": vtype},
			as_dict=True,
		):
			if not line.item_group:
				continue
			amount = flt(line.get(amount_field))
			net_stock, has_stock = 0.0, False

			# Stock side: debit when stock came in, credit when it went out
			for f in warehouse_fields:
				wh = line.get(f)
				wh_account = (warehouse_account.get(wh) or {}).get("account") if wh else None
				if not wh_account:
					continue
				value = sle_value.get((line.parent, line.name, wh))
				if value is None:
					value = amount if f in ("t_warehouse", "target_warehouse") or vtype == "Purchase Receipt" else -amount
				else:
					has_stock = True
				net_stock += value
				account = resolve_account(wh, line.item_code, wh_account, ig_cache, wh_map_cache)
				add(exact, (vtype, line.parent, account), line.item_group, value)
				add(fallback, (vtype, line.parent, wh_account), line.item_group, value)

			for f in account_fields:
				account = line.get(f)
				if not account:
					continue
				if f == "income_account":
					value = -amount  # income is credited
				elif has_stock:
					value = -net_stock  # cost / difference account is the stock side's mirror
				else:
					value = amount
				add(exact, (vtype, line.parent, account), line.item_group, value)

			if line.get("is_finished_item"):
				finished.setdefault(line.parent, []).append((line.item_group, amount))

	# Operating / additional costs of a Stock Entry belong to what it produced (credited)
	if finished:
		for cost in frappe.get_all(
			"Landed Cost Taxes and Charges",
			filters={"parenttype": "Stock Entry", "parent": ["in", list(finished)]},
			fields=["parent", "expense_account"],
		):
			for group, amount in finished[cost.parent]:
				add(fallback, ("Stock Entry", cost.parent, cost.expense_account), group, -abs(amount))
	return exact, fallback
