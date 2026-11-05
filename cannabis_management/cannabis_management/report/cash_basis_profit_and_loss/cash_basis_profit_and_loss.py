# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Cash Basis Profit and Loss.

ERPNext's Profit and Loss Statement, switched from accrual to cash basis. The
layout, filters, account tree, totals, "Profit for the year", chart, summary
and Growth / Margin views are the P&L's own code; only the entries fed into it
differ.

The accrual P&L takes every GL Entry on an Income or Expense account. This one
takes an Income / Expense GL Entry only when cash moved for it: it sits in a
voucher with a Bank or Cash GL Entry, and its account is in that Bank / Cash
entry's Against column. Each such line counts once, at its own debit / credit,
so a bank line against several heads splits into the real amount per head.

Everything on the Bank / Cash side that is against a Balance Sheet head (bank
to bank transfers, Debtors / Creditors, a party on a Payment Entry, loans...)
is left out: only Profit and Loss accounts of the selected company count.
"""

import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions

from erpnext.accounts.report.financial_statements import (
	accumulate_values_into_parents,
	add_total_row,
	apply_additional_conditions,
	calculate_values,
	compute_growth_view_data,
	compute_margin_view_data,
	filter_accounts,
	filter_out_zero_value_rows,
	get_accounts,
	get_appropriate_currency,
	get_columns,
	get_period_list,
	prepare_data,
)
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import (
	get_chart_data,
	get_net_profit_loss,
	get_report_summary,
)

CASH_ACCOUNT_TYPES = ("Bank", "Cash")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company=filters.company,
	)

	income = get_cash_data(filters.company, "Income", "Credit", period_list, filters)
	expense = get_cash_data(filters.company, "Expense", "Debit", period_list, filters)

	net_profit_loss = get_net_profit_loss(
		income, expense, period_list, filters.company, filters.presentation_currency
	)

	data = []
	data.extend(income or [])
	data.extend(expense or [])
	if net_profit_loss:
		data.append(net_profit_loss)

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)
	chart = get_chart_data(filters, columns, income, expense, net_profit_loss, currency)
	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, income, expense, net_profit_loss, currency, filters
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)
	if filters.get("selected_view") == "Margin":
		compute_margin_view_data(data, period_list, filters.accumulated_values)

	return columns, data, None, chart, report_summary, primitive_summary


def get_cash_data(company, root_type, balance_must_be, period_list, filters):
	"""financial_statements.get_data, with the cash-basis entries in place of
	set_gl_entries_by_account."""
	accounts = get_accounts(company, root_type)
	if not accounts:
		return None

	accounts, accounts_by_name, parent_children_map = filter_accounts(accounts)
	company_currency = get_appropriate_currency(company, filters)

	gl_entries_by_account = {}
	for entry in get_cash_entries(company, root_type, period_list, filters):
		gl_entries_by_account.setdefault(entry.account, []).append(entry)

	calculate_values(accounts_by_name, gl_entries_by_account, period_list, filters.accumulated_values, False)
	accumulate_values_into_parents(accounts, accounts_by_name, period_list)
	out = prepare_data(accounts, balance_must_be, period_list, company_currency,
	                   accumulated_values=filters.accumulated_values)
	out = filter_out_zero_value_rows(out, parent_children_map, filters.show_zero_values)
	if out:
		add_total_row(out, root_type, balance_must_be, period_list, company_currency)
	return out


def get_cash_entries(company, root_type, period_list, filters):
	"""Income / Expense GL Entries that a Bank or Cash GL Entry of the same
	voucher was posted against.

	Same window, cost center / project / finance book / dimension filters and
	Period Closing Voucher exclusion as the accrual P&L (apply_additional_conditions).
	"""
	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(acc).on(acc.name == gle.account)
		.select(gle.name, gle.account, gle.posting_date, gle.debit, gle.credit, gle.fiscal_year)
		.where(gle.company == company)
		.where(gle.is_cancelled == 0)
		.where(acc.root_type == root_type)
		.where(acc.is_group == 0)
		.where(gle.posting_date <= period_list[-1]["to_date"])
	)
	query = apply_additional_conditions(
		"GL Entry", query, period_list[0]["year_start_date"], True, filters
	)
	sql, params = query.walk()

	# The cash link: a Bank / Cash entry in the same voucher lists this
	# account in its Against column (stored as "Head A, Head B").
	types = ", ".join(frappe.db.escape(t) for t in CASH_ACCOUNT_TYPES)
	sql += f"""
		and exists (
			select 1 from `tabGL Entry` cash_gle
			join `tabAccount` cash_acc on cash_acc.name = cash_gle.account
			where cash_gle.voucher_type = `tabGL Entry`.voucher_type
			  and cash_gle.voucher_no = `tabGL Entry`.voucher_no
			  and cash_gle.company = `tabGL Entry`.company
			  and cash_gle.is_cancelled = 0
			  and cash_acc.account_type in ({types})
			  and find_in_set(`tabGL Entry`.account, replace(cash_gle.against, ', ', ',')) > 0
		)"""

	match = build_match_conditions("GL Entry")
	if match:
		sql += " and " + match

	return frappe.db.sql(sql, params, as_dict=True)
