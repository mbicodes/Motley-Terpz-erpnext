# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
#
# Restructures the standard Profit and Loss Statement into a multi-step
# income statement: Income -> Total Income -> Cost of Goods Sold ->
# Total COGS -> Gross Profit -> Expense (everything under the Expense root
# that isn't COGS) -> Total Expense -> Net Profit.
#
# Parent/child accounts are kept exactly as they appear in the standard
# report (real groups, real indentation, collapsible) - the only structural
# change is that the Cost of Goods Sold branch is cut out of the Expense
# tree and shown under its own heading instead of buried inside Expense.
#
# COGS accounts are identified from the chart of accounts rather than a
# fixed account_type: for each company we find the Expense account(s) named
# "Cost of Goods Sold"/"Cost of Goods Solds" and treat that account plus its
# entire descendant branch as COGS. Everything else under Expense is a
# regular expense. This matches how COGS is actually modeled per company in
# this instance (sometimes a single leaf account, sometimes a large group
# with many product-level child accounts).
#
# Same restructuring as profit_and_loss_statement_gross_profit.py - kept as
# a separate, self-contained report (its own name/roles/menu wiring) rather
# than reusing that module directly.
#
# Every leaf account row is further expanded, in place, into its own
# transactions (vouchers) - no navigating away to General Ledger - and every
# voucher that carries its own item table (Sales/Purchase Invoice, Delivery
# Note, Purchase Receipt, Stock Entry, Stock Reconciliation - see
# VOUCHER_ITEM_DOCTYPE) is expanded one level further into its line items,
# exactly like QuickBooks lets you drill from a statement all the way down to
# the transaction (and, where there is one, the item) level. See
# attach_transaction_rows() in financial_statements.py - shared with the
# Detailed Balance Sheet report, which drills down the same way.

import frappe
from frappe import _
from frappe.utils import flt

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
	# standard report itself calls, so Total Income/Total Expense below tie
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

	# Body rows only: drop the root account row itself (our own "Income"/
	# "Expense" section heading takes its place at the same indent level)
	# and the trailing [total_row, blank] pair.
	income_rows = income_tree[1:-2] if income_tree and len(income_tree) >= 2 else []
	expense_rows = expense_tree[1:-2] if expense_tree and len(expense_tree) >= 2 else []

	cogs_rows, cogs_anchor_rows, opex_rows = split_cogs_branch(
		expense_rows, filters.company, period_list
	)

	# Sum only the anchor row(s) - each anchor's own "total"/period values are
	# already the rolled-up sum of its whole branch, so summing every row in
	# cogs_rows too would double-count everything beneath the anchor.
	total_cogs_row = make_total_row(cogs_anchor_rows, period_list, _("Total Cost of Goods Sold"), currency)
	gross_profit_row = make_diff_row(
		total_income_row, total_cogs_row, period_list, _("Gross Profit"), currency
	)
	# Total Expense (ex-COGS) is derived by subtracting COGS from the
	# authoritative combined Expense total, rather than summed independently
	# from opex_rows - so Total COGS + Total Expense always equals the
	# standard report's Total Expense exactly, and Net Profit below ties out
	# to the standard report's Net Profit exactly.
	total_expense_row = make_diff_row(
		total_expense_all_row, total_cogs_row, period_list, _("Total Expense"), currency
	)
	net_profit_row = make_diff_row(
		gross_profit_row, total_expense_row, period_list, _("Net Profit"), currency
	)

	# Expand every leaf account into its own transactions (and, for
	# vouchers with an item table, their line items) as further-indented
	# child rows in this same tree.
	income_rows = attach_transaction_rows(income_rows, filters, period_list, currency)
	# COGS is the one branch where the item drill-down shows valuation/cost
	# rate instead of the selling rate - it's about what the stock actually
	# cost, not what it was invoiced at.
	cogs_rows = attach_transaction_rows(cogs_rows, filters, period_list, currency, use_valuation_rate=True)
	opex_rows = attach_transaction_rows(opex_rows, filters, period_list, currency)

	# Group/parent accounts roll up every descendant's amount - needed above
	# for Total Income/COGS/Expense etc. to tie out, but confusing to display:
	# a parent's number reads like its own balance stacked on top of its
	# children's. Blank it for display only, after all of that arithmetic is
	# already done, so only real leaf accounts show a figure.
	blank_group_amounts(income_rows, period_list)
	blank_group_amounts(cogs_rows, period_list)
	blank_group_amounts(opex_rows, period_list)

	data = []
	data.append(get_section_heading_row(_("Income"), period_list))
	data.extend(income_rows)
	if total_income_row:
		data.append(total_income_row)
	data.append({})

	data.append(get_section_heading_row(_("Cost of Goods Sold"), period_list))
	data.extend(cogs_rows)
	data.append(total_cogs_row)
	data.append(gross_profit_row)
	data.append({})

	data.append(get_section_heading_row(_("Expense"), period_list))
	data.extend(opex_rows)
	data.append(total_expense_row)
	data.append({})

	data.append(net_profit_row)

	blank_missing_transaction_detail_fields(data)

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)
	columns.extend(get_transaction_detail_columns(data))

	chart = get_chart_data(
		filters,
		columns,
		total_income_row,
		total_cogs_row,
		gross_profit_row,
		total_expense_row,
		net_profit_row,
		currency,
	)

	report_summary, primitive_summary = get_report_summary(
		period_list,
		filters.periodicity,
		total_income_row,
		total_cogs_row,
		gross_profit_row,
		total_expense_row,
		net_profit_row,
		currency,
		filters,
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	if filters.get("selected_view") == "Margin":
		compute_margin_view_data(data, period_list, filters.accumulated_values)

	return columns, data, None, chart, report_summary, primitive_summary


def split_cogs_branch(expense_rows, company, period_list):
	"""Cut the Cost of Goods Sold branch(es) out of the Expense account tree.

	expense_rows is the Expense tree (real groups + leaves, in the same
	lft/pre-order the standard report uses, root already excluded). We locate
	the topmost Expense account(s) actually named "Cost of Goods Sold"/
	"Cost of Goods Solds" and cut out each one's entire branch - the account
	row plus every row more indented than it that immediately follows,
	which is exactly how frappe-datatable itself decides parent/child
	grouping. Everything left behind is a regular expense.

	Every ancestor group still left in Expense (e.g. "Direct Expenses",
	"Stock Expenses") had the removed branch's value baked into its own
	rolled-up total by accumulate_values_into_parents - so once the branch
	is pulled out, we subtract it back out of each remaining ancestor too.
	Otherwise those group subtotals would still include COGS while the
	Total Expense row below them wouldn't, and the numbers wouldn't add up.
	"""
	anchor_names = get_cogs_anchor_account_names(company)

	rows_by_account = {row.get("account"): row for row in expense_rows if row.get("account")}
	anchor_rows_in_order = [row for row in expense_rows if row.get("account") in anchor_names]
	for anchor_row in anchor_rows_in_order:
		subtract_from_ancestors(rows_by_account, anchor_row, period_list)

	cogs_rows = []
	cogs_anchor_rows = []
	opex_rows = []

	i = 0
	n = len(expense_rows)
	while i < n:
		row = expense_rows[i]
		if row.get("account") in anchor_names:
			anchor_indent = row.get("indent") or 0
			cogs_anchor_rows.append(row)
			cogs_rows.append(row)
			i += 1
			while i < n and (expense_rows[i].get("indent") or 0) > anchor_indent:
				cogs_rows.append(expense_rows[i])
				i += 1
		else:
			opex_rows.append(row)
			i += 1

	reindent_branches(cogs_rows, cogs_anchor_rows, new_anchor_indent=1)

	return cogs_rows, cogs_anchor_rows, opex_rows


def get_cogs_anchor_account_names(company):
	"""Topmost Expense account(s) for this company that represent Cost of
	Goods Sold. If one matching account contains another (e.g. a
	"Cost of Goods Solds" group that itself has a nested "Cost of Goods
	Sold" leaf inside it), keep only the outermost one so its branch is cut
	out as a single unit instead of being sliced twice.
	"""
	anchors = frappe.db.sql(
		"""
		select name, lft, rgt from `tabAccount`
		where company=%s and root_type='Expense'
		and account_name in %s
		""",
		(company, COGS_ACCOUNT_NAMES),
		as_dict=True,
	)

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
	total_expense_row,
	net_profit_row,
	currency,
	filters,
):
	def summarize(row):
		if not row:
			return 0.0
		if filters.accumulated_values:
			return flt(row.get(period_list[-1].key, 0.0))
		return sum(flt(row.get(period.key, 0.0)) for period in period_list)

	net_income = summarize(total_income_row)
	net_cogs = summarize(total_cogs_row)
	gross_profit = summarize(gross_profit_row)
	net_expense = summarize(total_expense_row)
	net_profit = summarize(net_profit_row)

	if len(period_list) == 1 and periodicity == "Yearly":
		profit_label = _("Net Profit This Year")
	else:
		profit_label = _("Net Profit")

	return [
		{"value": net_income, "label": _("Total Income"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{"value": net_cogs, "label": _("Total COGS"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "=", "color": "blue"},
		{"value": gross_profit, "label": _("Gross Profit"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{"value": net_expense, "label": _("Total Expense"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "=", "color": "blue"},
		{
			"value": net_profit,
			"indicator": "Green" if net_profit > 0 else "Red",
			"label": profit_label,
			"datatype": "Currency",
			"currency": currency,
		},
	], net_profit


def get_chart_data(
	filters,
	columns,
	total_income_row,
	total_cogs_row,
	gross_profit_row,
	total_expense_row,
	net_profit_row,
	currency,
):
	period_columns = columns[2:]
	labels = [d.get("label") for d in period_columns]

	def series(row):
		return [flt((row or {}).get(p.get("fieldname"), 0.0)) for p in period_columns]

	datasets = []
	if total_income_row:
		datasets.append({"name": _("Income"), "values": series(total_income_row)})
	datasets.append({"name": _("Cost of Goods Sold"), "values": series(total_cogs_row)})
	datasets.append({"name": _("Gross Profit"), "values": series(gross_profit_row)})
	datasets.append({"name": _("Expense"), "values": series(total_expense_row)})
	datasets.append({"name": _("Net Profit"), "values": series(net_profit_row)})

	chart = {"data": {"labels": labels, "datasets": datasets}}

	if not filters.accumulated_values:
		chart["type"] = "bar"
	else:
		chart["type"] = "line"

	chart["fieldtype"] = "Currency"
	chart["options"] = "currency"
	chart["currency"] = currency

	return chart
