import re

import frappe
from frappe import _
from frappe.utils import cstr, flt

from erpnext.accounts.report.financial_statements import (
	accumulate_values_into_parents,
	add_total_row,
	calculate_values,
	compute_growth_view_data,
	filter_accounts,
	filter_out_zero_value_rows,
	get_accounts,
	get_appropriate_currency,
	get_columns,
	get_period_list,
	prepare_data,
	set_gl_entries_by_account,
)

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
	return re.sub(r"\s+", " ", cstr(name)).strip().lower()

ALLOWED_KEYS = {_norm(head) for head in ALLOWED_EXPENSE_HEADS}


def keep_allowed_heads(expense, period_list, currency):
	rows = expense or []
	by_account = {row.get("account"): row for row in rows if row.get("account")}

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

	out = []
	for row in rows:
		account = row.get("account")
		if account not in keep:
			continue
		if account in sums:
			row.update(sums[account])
		out.append(row)

	return out + [total_row, {}]


def get_debit_only_data(company, period_list, filters):
	accounts = get_accounts(company, "Expense")
	if not accounts:
		return None

	accounts, accounts_by_name, parent_children_map = filter_accounts(accounts)

	company_currency = get_appropriate_currency(company, filters)

	gl_entries_by_account = {}
	for root in frappe.db.sql(
		"""select lft, rgt from `tabAccount`
			where root_type = 'Expense' and ifnull(parent_account, '') = ''""",
		as_dict=1,
	):
		set_gl_entries_by_account(
			company,
			period_list[0]["year_start_date"],
			period_list[-1]["to_date"],
			filters,
			gl_entries_by_account,
			root.lft,
			root.rgt,
			root_type="Expense",
			ignore_closing_entries=True,
		)

	for entries in gl_entries_by_account.values():
		for entry in entries:
			entry.credit = 0.0
			entry.credit_in_account_currency = 0.0

	calculate_values(accounts_by_name, gl_entries_by_account, period_list, filters.accumulated_values, False)
	accumulate_values_into_parents(accounts, accounts_by_name, period_list)

	out = prepare_data(
		accounts,
		"Debit",
		period_list,
		company_currency,
		accumulated_values=filters.accumulated_values,
	)
	out = filter_out_zero_value_rows(out, parent_children_map, filters.show_zero_values)

	if out:
		add_total_row(out, "Expense", "Debit", period_list, company_currency)

	return out


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

	expense = get_debit_only_data(filters.company, period_list, filters)

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)

	expense = keep_allowed_heads(expense, period_list, currency)

	data = []
	data.extend(expense or [])

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)

	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, expense, currency, filters
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	return columns, data, None, None, report_summary, primitive_summary


def get_report_summary(period_list, periodicity, expense, currency, filters):
	net_expense = 0.0

	if filters.accumulated_values:
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
