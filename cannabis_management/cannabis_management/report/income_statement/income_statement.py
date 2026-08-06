# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
#
# Restructures the standard Profit and Loss Statement into a multi-step
# income statement, for ANY company (no company-specific mapping): Income ->
# Total Revenue -> Cost of Goods Sold -> Total COGS -> Gross Profit ->
# Operating Expenses -> Total Operating Expenses -> Operating Income ->
# Finance Costs -> Total Finance Costs -> Net Income.
#
# Same base as profit_and_loss_statement_child_accounts.py in this package -
# real group/parent accounts kept exactly as in the standard report (real
# indentation, collapsible, drilldown to transactions/items) - restructured
# one step further to also pull Finance Costs out of Operating Expenses.
#
# Both cuts are identified from the chart of accounts itself, not a fixed
# account_type or a per-company account list, so this works unmodified for
# every company in the instance:
#   - Cost of Goods Sold: the Expense account(s) actually named "Cost of
#     Goods Sold"/"Cost of Goods Solds" (whatever accounts sit inside that
#     branch is COGS, however deep/wide it is for that company).
#   - Finance Costs: whatever's left of Expense after COGS is cut out, any
#     account whose name contains "Interest" (e.g. "Interest Paid (Loan)",
#     "Interest Expense") - the standard way interest/finance cost accounts
#     are named across every company's chart of accounts in this instance.
#     A company with no such account simply gets a $0 Finance Costs section.
#
# Everything else under Expense (not COGS, not Finance Costs) is Operating
# Expenses. Every leaf account row is further expanded, in place, into its
# own transactions/items exactly like the sibling P&L reports - see
# attach_transaction_rows() in financial_statements.py.

import frappe
from frappe import _
from frappe.utils import cint, flt

from cannabis_management.cannabis_management.report.financial_statements import (
	attach_transaction_rows,
	blank_group_amounts,
	blank_missing_transaction_detail_fields,
	compute_growth_view_data,
	compute_margin_view_data,
	get_columns,
	get_period_list,
	get_transaction_detail_columns,
)

# Deliberately erpnext's unmodified financial_statements.get_data() here, not
# this app's local "child accounts" copy - we want the real group/parent
# hierarchy (same as the standard Profit and Loss Statement), not a
# flattened leaf-only list.
from erpnext.accounts.report.financial_statements import get_data

COGS_ACCOUNT_NAMES = ("Cost of Goods Sold", "Cost of Goods Solds")
FINANCE_COST_NAME_LIKE = "%Interest%"


def execute(filters=None):
	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company=filters.company,
	)

	# Full account tree (real groups + leaves, indented exactly like the
	# standard Profit and Loss Statement) - this is the same get_data() the
	# standard report itself calls, so Total Revenue/Total Expense below tie
	# out to it exactly.
	income_tree = get_data(
		filters.company,
		"Income",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)

	expense_tree = get_data(
		filters.company,
		"Expense",
		"Debit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)

	total_income_row = income_tree[-2] if income_tree and len(income_tree) >= 2 else None
	total_expense_all_row = expense_tree[-2] if expense_tree and len(expense_tree) >= 2 else None
	if total_income_row:
		# get_data()'s add_total_row doesn't flag is_total_row - add it so this
		# row still bolds and sits at the root tree level like every other
		# summary row we build below.
		total_income_row["is_total_row"] = 1
		total_income_row["indent"] = 0

	# Body rows only: drop the root account row itself (our own section
	# headings take its place at the same indent level) and the trailing
	# [total_row, blank] pair.
	income_rows = income_tree[1:-2] if income_tree and len(income_tree) >= 2 else []
	expense_rows = expense_tree[1:-2] if expense_tree and len(expense_tree) >= 2 else []

	cogs_anchor_names = _maximal(get_accounts_by_exact_name(filters.company, COGS_ACCOUNT_NAMES))
	cogs_rows, cogs_anchor_rows, remaining_expense_rows = split_branch(
		expense_rows, cogs_anchor_names, period_list, new_indent=1
	)

	remaining_account_names = {row.get("account") for row in remaining_expense_rows if row.get("account")}
	finance_anchor_names = _maximal(
		get_accounts_by_name_like(filters.company, remaining_account_names, FINANCE_COST_NAME_LIKE)
	)
	finance_rows, finance_anchor_rows, opex_rows = split_branch(
		remaining_expense_rows, finance_anchor_names, period_list, new_indent=1
	)

	total_cogs_row = make_total_row(cogs_anchor_rows, period_list, _("Total Cost of Goods Sold"), currency)
	gross_profit_row = make_diff_row(
		total_income_row, total_cogs_row, period_list, _("Gross Profit"), currency
	)

	total_finance_cost_row = make_total_row(
		finance_anchor_rows, period_list, _("Total Finance Costs"), currency
	)

	# Total Operating Expenses is derived by subtracting both COGS and
	# Finance Costs from the authoritative combined Expense total, rather
	# than summed independently from opex_rows - so
	# Total COGS + Total Operating Expenses + Total Finance Costs always
	# equals the standard report's Total Expense exactly, and Net Income
	# below ties out to the standard report's Net Profit exactly.
	expense_minus_cogs_row = make_diff_row(total_expense_all_row, total_cogs_row, period_list, "_tmp", currency)
	total_opex_row = make_diff_row(
		expense_minus_cogs_row, total_finance_cost_row, period_list, _("Total Operating Expenses"), currency
	)

	operating_income_row = make_diff_row(
		gross_profit_row, total_opex_row, period_list, _("Operating Income / (Loss)"), currency
	)
	net_income_row = make_diff_row(
		operating_income_row, total_finance_cost_row, period_list, _("Net Income / (Loss)"), currency
	)
	net_income_row["is_net_income_row"] = 1

	# Tag every COGS leaf/group row with which rate mode its own on-demand
	# drill-down (get_account_drilldown() below) needs to request - done
	# unconditionally (cheap, and harmless for callers that never look at
	# it) so the caller never has to re-derive COGS branch membership itself.
	for row in cogs_rows:
		row["use_valuation_rate"] = 1

	if filters.get("skip_transaction_drilldown"):
		pass
	else:
		# Expand every leaf account into its own transactions (and, for
		# vouchers with an item table, their line items) as further-indented
		# child rows in this same tree.
		income_rows = attach_transaction_rows(income_rows, filters, period_list, currency)
		# COGS is the one branch where the item drill-down shows valuation/cost
		# rate instead of the selling rate - it's about what the stock actually
		# cost, not what it was invoiced at.
		cogs_rows = attach_transaction_rows(cogs_rows, filters, period_list, currency, use_valuation_rate=True)
		opex_rows = attach_transaction_rows(opex_rows, filters, period_list, currency)
		finance_rows = attach_transaction_rows(finance_rows, filters, period_list, currency)

	# Group/parent accounts roll up every descendant's amount - needed above
	# for the various totals to tie out, but confusing to display: a
	# parent's number reads like its own balance stacked on top of its
	# children's. Blank it for display only, after all of that arithmetic is
	# already done, so only real leaf accounts show a figure.
	blank_group_amounts(income_rows, period_list)
	blank_group_amounts(cogs_rows, period_list)
	blank_group_amounts(opex_rows, period_list)
	blank_group_amounts(finance_rows, period_list)

	data = []
	data.append(get_section_heading_row(_("Revenue"), period_list))
	data.extend(income_rows)
	if total_income_row:
		total_income_row["account_name"] = _("Total Revenue")
		data.append(total_income_row)
	data.append({})

	data.append(get_section_heading_row(_("Cost of Goods Sold"), period_list))
	data.extend(cogs_rows)
	data.append(total_cogs_row)
	data.append(gross_profit_row)
	data.append({})

	data.append(get_section_heading_row(_("Operating Expenses"), period_list))
	data.extend(opex_rows)
	data.append(total_opex_row)
	data.append(operating_income_row)
	data.append({})

	data.append(get_section_heading_row(_("Finance Costs"), period_list))
	data.extend(finance_rows)
	data.append(total_finance_cost_row)
	data.append({})

	data.append(net_income_row)

	blank_missing_transaction_detail_fields(data)

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)
	columns.extend(get_transaction_detail_columns(data))

	chart = get_chart_data(
		filters,
		columns,
		total_income_row,
		total_cogs_row,
		gross_profit_row,
		total_opex_row,
		operating_income_row,
		total_finance_cost_row,
		net_income_row,
		currency,
	)

	report_summary, primitive_summary = get_report_summary(
		period_list,
		filters.periodicity,
		total_income_row,
		total_cogs_row,
		gross_profit_row,
		total_opex_row,
		operating_income_row,
		total_finance_cost_row,
		net_income_row,
		currency,
		filters,
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	if filters.get("selected_view") == "Margin":
		compute_margin_view_data(data, period_list, filters.accumulated_values)

	return columns, data, None, chart, report_summary, primitive_summary


def split_branch(rows, anchor_names, period_list, new_indent=1):
	"""Cut the branch(es) rooted at every account in `anchor_names` out of
	`rows` (a real account tree - groups + leaves, in the same lft/pre-order
	the standard report uses). Each anchor's entire branch is the anchor row
	plus every row more indented than it that immediately follows - exactly
	how frappe-datatable itself decides parent/child grouping.

	Every ancestor group still left behind had the removed branch's value
	baked into its own rolled-up total by accumulate_values_into_parents -
	so once the branch is pulled out, it's subtracted back out of each
	remaining ancestor too, otherwise those group subtotals would still
	include it while the totals built from the remainder wouldn't.

	Returns (matched_rows, matched_anchor_rows, remaining_rows).
	"""
	if not anchor_names:
		return [], [], list(rows)

	rows_by_account = {row.get("account"): row for row in rows if row.get("account")}
	anchor_rows_in_order = [row for row in rows if row.get("account") in anchor_names]
	for anchor_row in anchor_rows_in_order:
		subtract_from_ancestors(rows_by_account, anchor_row, period_list)

	matched_rows, matched_anchor_rows, remaining_rows = [], [], []

	i, n = 0, len(rows)
	while i < n:
		row = rows[i]
		if row.get("account") in anchor_names:
			anchor_indent = row.get("indent") or 0
			matched_anchor_rows.append(row)
			matched_rows.append(row)
			i += 1
			while i < n and (rows[i].get("indent") or 0) > anchor_indent:
				matched_rows.append(rows[i])
				i += 1
		else:
			remaining_rows.append(row)
			i += 1

	reindent_branches(matched_rows, matched_anchor_rows, new_anchor_indent=new_indent)

	return matched_rows, matched_anchor_rows, remaining_rows


def get_accounts_by_exact_name(company, account_names):
	return frappe.db.sql(
		"""
		select name, lft, rgt from `tabAccount`
		where company=%s and root_type='Expense'
		and account_name in %s
		""",
		(company, tuple(account_names)),
		as_dict=True,
	)


def get_accounts_by_name_like(company, candidate_account_names, name_like):
	"""Same shape as get_accounts_by_exact_name(), but matched by a LIKE
	pattern and restricted to `candidate_account_names` (the accounts still
	left in play at the point of the call - e.g. once COGS has already been
	cut out, so an "Interest" account inside the COGS branch, if that ever
	happens, isn't pulled out a second time)."""
	if not candidate_account_names:
		return []
	return frappe.db.sql(
		"""
		select name, lft, rgt from `tabAccount`
		where company=%s and root_type='Expense'
		and name in %s and account_name like %s
		""",
		(company, tuple(candidate_account_names), name_like),
		as_dict=True,
	)


def _maximal(anchors):
	"""If one matching account contains another (e.g. a group that itself
	has a nested matching leaf inside it), keep only the outermost one so
	its branch is cut out as a single unit instead of being sliced twice."""
	maximal = []
	for i, anchor in enumerate(anchors):
		contained = any(
			j != i and anchors[j].lft < anchor.lft and anchor.rgt < anchors[j].rgt
			for j in range(len(anchors))
		)
		if not contained:
			maximal.append(anchor.name)
	return set(maximal)


def subtract_from_ancestors(rows_by_account, anchor_row, period_list):
	parent = anchor_row.get("parent_account")
	while parent and parent in rows_by_account:
		ancestor = rows_by_account[parent]
		for period in period_list:
			ancestor[period.key] = flt(ancestor.get(period.key, 0.0)) - flt(anchor_row.get(period.key, 0.0))
		ancestor["total"] = flt(ancestor.get("total", 0.0)) - flt(anchor_row.get("total", 0.0))
		parent = ancestor.get("parent_account")


def reindent_branches(rows, anchor_rows, new_anchor_indent):
	"""Shift each extracted branch so its anchor row sits at
	new_anchor_indent, preserving the relative depth of everything beneath
	it (e.g. an anchor 3 levels deep with children 1 level further down
	keeps that 1-level gap once re-based under the new heading)."""
	anchor_ids = {id(row) for row in anchor_rows}
	delta = 0
	for row in rows:
		if id(row) in anchor_ids:
			delta = new_anchor_indent - (row.get("indent") or 0)
			row["indent"] = new_anchor_indent
		else:
			row["indent"] = (row.get("indent") or 0) + delta


def get_section_heading_row(account_name, period_list):
	row = {
		"account_name": account_name,
		"is_group": 1,
		"is_total_row": 1,
		"indent": 0,
	}
	# Blank out every amount column. frappe's Currency formatter routes
	# anything falsy - including an unset key or "" - through format_currency,
	# which coerces it to "0.00"; only a strict None (JSON null) short-
	# circuits to a truly empty cell.
	for period in period_list:
		row[period.key] = None
	row["total"] = None
	return row


def make_total_row(rows, period_list, label, currency):
	total_row = {
		"account_name": "'" + label + "'",
		"account": "'" + label + "'",
		"currency": currency,
		"is_total_row": 1,
		"indent": 0,
		"total": 0.0,
	}
	for period in period_list:
		total_row[period.key] = 0.0

	for row in rows:
		for period in period_list:
			total_row[period.key] += flt(row.get(period.key, 0.0))
		total_row["total"] += flt(row.get("total", 0.0))

	return total_row


def make_diff_row(row_a, row_b, period_list, label, currency):
	row_a = row_a or {}
	row_b = row_b or {}
	diff_row = {
		"account_name": "'" + label + "'",
		"account": "'" + label + "'",
		"currency": currency,
		"is_total_row": 1,
		"indent": 0,
		"warn_if_negative": True,
		"total": flt(row_a.get("total", 0.0)) - flt(row_b.get("total", 0.0)),
	}
	for period in period_list:
		diff_row[period.key] = flt(row_a.get(period.key, 0.0)) - flt(row_b.get(period.key, 0.0))

	return diff_row


def get_report_summary(
	period_list,
	periodicity,
	total_income_row,
	total_cogs_row,
	gross_profit_row,
	total_opex_row,
	operating_income_row,
	total_finance_cost_row,
	net_income_row,
	currency,
	filters,
):
	def summarize(row):
		if not row:
			return 0.0
		if filters.accumulated_values:
			return flt(row.get(period_list[-1].key, 0.0))
		return sum(flt(row.get(period.key, 0.0)) for period in period_list)

	total_revenue = summarize(total_income_row)
	gross_profit = summarize(gross_profit_row)
	operating_income = summarize(operating_income_row)
	net_income = summarize(net_income_row)

	if len(period_list) == 1 and periodicity == "Yearly":
		net_income_label = _("Net Income This Year")
	else:
		net_income_label = _("Net Income")

	return [
		{"value": total_revenue, "label": _("Total Revenue"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{
			"value": summarize(total_cogs_row),
			"label": _("Total COGS"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"type": "separator", "value": "=", "color": "blue"},
		{"value": gross_profit, "label": _("Gross Profit"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{
			"value": summarize(total_opex_row),
			"label": _("Total Operating Expenses"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"type": "separator", "value": "=", "color": "blue"},
		{
			"value": operating_income,
			"label": _("Operating Income"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"type": "separator", "value": "-"},
		{
			"value": summarize(total_finance_cost_row),
			"label": _("Finance Costs"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"type": "separator", "value": "=", "color": "blue"},
		{
			"value": net_income,
			"indicator": "Green" if net_income > 0 else "Red",
			"label": net_income_label,
			"datatype": "Currency",
			"currency": currency,
		},
	], net_income


def get_chart_data(
	filters,
	columns,
	total_income_row,
	total_cogs_row,
	gross_profit_row,
	total_opex_row,
	operating_income_row,
	total_finance_cost_row,
	net_income_row,
	currency,
):
	period_columns = columns[2:]
	labels = [d.get("label") for d in period_columns]

	def series(row):
		return [flt((row or {}).get(p.get("fieldname"), 0.0)) for p in period_columns]

	datasets = []
	if total_income_row:
		datasets.append({"name": _("Revenue"), "values": series(total_income_row)})
	datasets.append({"name": _("Cost of Goods Sold"), "values": series(total_cogs_row)})
	datasets.append({"name": _("Gross Profit"), "values": series(gross_profit_row)})
	datasets.append({"name": _("Operating Expenses"), "values": series(total_opex_row)})
	datasets.append({"name": _("Operating Income"), "values": series(operating_income_row)})
	datasets.append({"name": _("Finance Costs"), "values": series(total_finance_cost_row)})
	datasets.append({"name": _("Net Income"), "values": series(net_income_row)})

	chart = {"data": {"labels": labels, "datasets": datasets}}

	if not filters.accumulated_values:
		chart["type"] = "bar"
	else:
		chart["type"] = "line"

	chart["fieldtype"] = "Currency"
	chart["options"] = "currency"
	chart["currency"] = currency

	return chart


def _resolve_drilldown_filters(filters):
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
	return frappe._dict(filters)


def _get_drilldown_period_list_and_currency(filters):
	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company=filters.company,
	)
	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)
	return period_list, currency


@frappe.whitelist()
def get_account_drilldown(account, indent, filters, use_valuation_rate=0):
	"""On-demand counterpart to attach_transaction_rows() for exactly ONE
	leaf account. Reuses attach_transaction_rows() itself unmodified against
	a single-row placeholder list, so the returned rows are byte-for-byte
	identical to what execute() would return inline for that account - just
	fetched lazily, for callers that want to expand one account at a time
	instead of eagerly building every account's drilldown up front."""
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("Not permitted to view General Ledger entries"), frappe.PermissionError)

	filters = _resolve_drilldown_filters(filters)
	period_list, currency = _get_drilldown_period_list_and_currency(filters)

	placeholder = {"account": account, "indent": cint(indent)}
	rows = attach_transaction_rows(
		[placeholder], filters, period_list, currency, use_valuation_rate=cint(use_valuation_rate)
	)
	rows = rows[1:]  # drop the placeholder row - the caller already has it
	blank_missing_transaction_detail_fields(rows)
	return rows


@frappe.whitelist()
def get_accounts_drilldown(accounts, filters):
	"""Bulk form of get_account_drilldown() for every leaf account at once -
	batches into as few GL Entry queries as attach_transaction_rows() itself
	would use (one per rate-mode - normal vs COGS valuation rate) rather
	than firing one request per account.

	`accounts` is a JSON list of {"account", "indent", "use_valuation_rate"}
	objects. Returns a dict keyed by account name."""
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("Not permitted to view General Ledger entries"), frappe.PermissionError)

	accounts = frappe.parse_json(accounts) if isinstance(accounts, str) else accounts
	filters = _resolve_drilldown_filters(filters)
	period_list, currency = _get_drilldown_period_list_and_currency(filters)

	result = {}

	def run_batch(entries, use_valuation_rate):
		if not entries:
			return
		placeholders = [{"account": e["account"], "indent": cint(e.get("indent", 0))} for e in entries]
		rows = attach_transaction_rows(
			placeholders, filters, period_list, currency, use_valuation_rate=use_valuation_rate
		)
		# attach_transaction_rows() preserves input order and never
		# interleaves - each placeholder's own row is immediately followed
		# by (only) its own children - so splitting the flat result back
		# into per-account buckets is a single linear walk.
		placeholder_accounts = {p["account"] for p in placeholders}
		current_account = None
		for row in rows:
			if row.get("account") in placeholder_accounts and not row.get("is_group"):
				current_account = row.get("account")
				result[current_account] = []
				continue
			if current_account is not None:
				result[current_account].append(row)

	run_batch([a for a in accounts if not cint(a.get("use_valuation_rate"))], False)
	run_batch([a for a in accounts if cint(a.get("use_valuation_rate"))], True)

	for account_rows in result.values():
		blank_missing_transaction_detail_fields(account_rows)

	return result
