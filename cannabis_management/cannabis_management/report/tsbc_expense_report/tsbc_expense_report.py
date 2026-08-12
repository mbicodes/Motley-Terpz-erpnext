# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
#
# The "Expense" half of the standard Profit and Loss Statement, on its own:
# every Expense account (real groups + leaf/child accounts, indented exactly
# like the standard report) with its Debit balance, plus a Total Expense row
# at the bottom. No Income, no COGS split, no Net Profit - just what was
# spent, account by account, so it reads as a plain expense report instead of
# a full income statement.
#
# Deliberately reuses erpnext's own financial_statements.get_data() unmodified
# - the same function the standard Profit and Loss Statement calls for its
# own Expense section - so every child account and every total here ties out
# to that report exactly.

import re

import frappe
from frappe import _
from frappe.utils import cstr, flt

from erpnext.accounts.report.financial_statements import (
	compute_growth_view_data,
	get_columns,
	get_data,
	get_period_list,
)

# The report is scoped to this fixed set of TSBC farming expense heads - the
# only accounts that belong on it. Every other Expense account, and all the
# parent groups, are dropped.
ALLOWED_EXPENSE_HEADS = (
	"Cultivation Supplies / Nutrients - TSBC",
	"Farm Labor - TSBC",
	"Ground Prep / Irrigation - TSBC",
	"Harvest Labor - TSBC",
	"Spraying - TSBC",
	"Clone  - COGS - TSBC",
	"Consumable  - COGS - TSBC",
	"Farm Supplies - TSBC",
	"Harvest & Cultivation - TSBC",
	"Harvest Cost - TSBC",
	"Farm Rent - TSBC",
)


def _norm(name):
	"""Whitespace-normalised key. Two of the heads above are named with a
	double space ("Clone  - COGS - TSBC"), which is too easy to lose in an
	edit, so matching never depends on it."""
	return re.sub(r"\s+", " ", cstr(name)).strip().lower()


ALLOWED_KEYS = {_norm(head) for head in ALLOWED_EXPENSE_HEADS}


def keep_allowed_heads(expense, period_list, currency):
	"""Reduce the Expense tree to the allowed heads, keeping the tree view.

	The report still reads like the standard Profit and Loss Statement - same
	indented groups, same order - only the leaf accounts are restricted to
	``ALLOWED_EXPENSE_HEADS``. The parent groups on the way down to those
	accounts are kept so the layout is unchanged; every other account is
	dropped.

	Group figures are recomputed from the allowed leaves alone. ``get_data()``
	has already rolled *all* children into each parent, so leaving those
	numbers untouched would show a group total larger than the rows visible
	beneath it. The same applies to the "Total Expense (Debit)" row, which is
	rebuilt here. The trailing ``[total, {}]`` shape is preserved because
	``get_report_summary()`` and ``get_chart_data()`` both read the total as
	``expense[-2]``.
	"""
	rows = expense or []
	by_account = {row.get("account"): row for row in rows if row.get("account")}

	# Each allowed leaf, with the chain of groups above it.
	leaves = {}
	for row in rows:
		if _norm(row.get("account")) not in ALLOWED_KEYS:
			continue
		ancestors, parent = [], row.get("parent_account")
		while parent and parent in by_account:
			ancestors.append(parent)
			parent = by_account[parent].get("parent_account")
		leaves[row.get("account")] = ancestors

	if not leaves:
		return []

	keep = set(leaves) | {ancestor for chain in leaves.values() for ancestor in chain}

	# Re-total every group from the allowed leaves sitting under it.
	fields = [period.key for period in period_list] + ["total", "opening_balance"]
	sums = {ancestor: dict.fromkeys(fields, 0.0) for chain in leaves.values() for ancestor in chain}
	for account, ancestors in leaves.items():
		leaf = by_account[account]
		for ancestor in ancestors:
			for field in fields:
				sums[ancestor][field] += flt(leaf.get(field))

	label = "'" + _("Total Expense (Debit)") + "'"
	total_row = {"account": label, "account_name": label, "currency": currency}
	for field in fields:
		total_row[field] = sum(flt(by_account[account].get(field)) for account in leaves)

	# Rebuild in the original tree order.
	out = []
	for row in rows:
		account = row.get("account")
		if account not in keep:
			continue
		if account in sums:
			row.update(sums[account])
		out.append(row)

	return out + [total_row, {}]


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

	# Full Expense account tree (real groups + leaves, indented exactly like
	# the standard Profit and Loss Statement) with a Total Expense row
	# already appended - same get_data() the standard report itself calls,
	# so this ties out to it exactly.
	expense = get_data(
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

	# Keep only the allowed expense heads. Everything downstream - the data,
	# the chart and the summary - reads this same filtered list, so the total
	# on screen always matches the rows above it.
	expense = keep_allowed_heads(expense, period_list, currency)

	data = []
	data.extend(expense or [])

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)

	chart = get_chart_data(filters, columns, expense, currency)

	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, expense, currency, filters
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	return columns, data, None, chart, report_summary, primitive_summary


def get_report_summary(period_list, periodicity, expense, currency, filters):
	net_expense = 0.0

	if filters.accumulated_values:
		# when 'accumulated_values' is enabled, periods have a running
		# balance, so the last period already holds the net total.
		key = period_list[-1].key
		if expense:
			net_expense = expense[-2].get(key)
	else:
		for period in period_list:
			if expense:
				net_expense += expense[-2].get(period.key)

	if len(period_list) == 1 and periodicity == "Yearly":
		expense_label = _("Total Expense This Year")
	else:
		expense_label = _("Total Expense")

	return [
		{"value": net_expense, "label": expense_label, "datatype": "Currency", "currency": currency},
	], net_expense


def get_chart_data(filters, columns, expense, currency):
	labels = [d.get("label") for d in columns[2:]]

	expense_data = []
	for p in columns[2:]:
		if expense:
			expense_data.append(expense[-2].get(p.get("fieldname")))

	datasets = []
	if expense_data:
		datasets.append({"name": _("Expense"), "values": expense_data})

	chart = {"data": {"labels": labels, "datasets": datasets}}

	if not filters.accumulated_values:
		chart["type"] = "bar"
	else:
		chart["type"] = "line"

	chart["fieldtype"] = "Currency"
	chart["options"] = "currency"
	chart["currency"] = currency

	return chart
