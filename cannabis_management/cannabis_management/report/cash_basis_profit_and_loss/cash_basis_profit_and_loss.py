# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Cash Basis Profit and Loss.

ERPNext's Profit and Loss Statement, switched from accrual to cash basis. The
layout, filters, account tree, totals, "Profit for the year", chart, summary
and Growth / Margin views are the P&L's own code; only the entries fed into it
differ.

The accrual P&L takes every GL Entry on an Income or Expense account. This one
takes an Income / Expense GL Entry only when cash moved for it: the same
Journal / Payment Entry moves a Bank or Cash account the opposite way (the
pairing the GL's Against column shows, read from the voucher because Against
keeps old account names after a rename). Each line counts once, at its own
debit / credit, so a bank line against several heads splits by head.

Customer payments are income on a cash basis: a credit to the company's Debtors
account posted against a Bank or Cash account means the customer paid us. That
shows in the Income section as "Debtors (customer payments)"; a refund paid back
from the bank reduces it. Only Debtors: intercompany receivables, Other
Receivables and UnEarned Income are money between the group or advances.

Every other Balance Sheet head on the Bank / Cash side (bank to bank transfers,
Creditors, intercompany, loans...) is left out.
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

	company_currency = get_appropriate_currency(company, filters)

	gl_entries_by_account = {}
	for entry in get_cash_entries(company, root_type, period_list, filters):
		gl_entries_by_account.setdefault(entry.account, []).append(entry)

	if root_type == "Income":
		# Customer payments: each Debtors account becomes a line directly under
		# the Income root, so the P&L code totals it like any income head.
		receipts = {}
		for entry in get_cash_entries(company, root_type, period_list, filters, receivable=True):
			receipts.setdefault(entry.account, []).append(entry)
		root = next((a for a in accounts if not a.parent_account), None)
		if root and receipts:
			names = dict(frappe.get_all("Account", filters={"name": ["in", list(receipts)]},
			                            fields=["name", "account_name"], as_list=True))
			for name, entries in receipts.items():
				accounts.append(frappe._dict(
					name=name, account_number=None, parent_account=root.name, root_type="Income",
					report_type="Profit and Loss", account_name=_("{0} (customer payments)").format(names.get(name, name)),
					include_in_gross=0, account_type="Receivable", is_group=0, lft=0, rgt=0,
				))
				gl_entries_by_account[name] = entries

	accounts, accounts_by_name, parent_children_map = filter_accounts(accounts)
	calculate_values(accounts_by_name, gl_entries_by_account, period_list, filters.accumulated_values, False)
	accumulate_values_into_parents(accounts, accounts_by_name, period_list)
	out = prepare_data(accounts, balance_must_be, period_list, company_currency,
	                   accumulated_values=filters.accumulated_values)
	out = filter_out_zero_value_rows(out, parent_children_map, filters.show_zero_values)
	if out:
		add_total_row(out, root_type, balance_must_be, period_list, company_currency)
	return out


def debtors_accounts(company):
	"""The company's Debtors: its default receivable account and any receivable
	account named Debtors."""
	names = set(frappe.get_all("Account", filters={"company": company, "account_type": "Receivable",
	                                                 "account_name": "Debtors", "is_group": 0}, pluck="name"))
	default = frappe.get_cached_value("Company", company, "default_receivable_account")
	if default:
		names.add(default)
	return list(names) or ["__none__"]


def get_cash_entries(company, root_type, period_list, filters, receivable=False):
	"""Income / Expense GL Entries paid in or out through a Bank or Cash account
	in the same Journal / Payment Entry.

	receivable=True instead returns the company's Debtors GL Entries paired the
	same way: customer payments (Debtors credited, bank debited), and refunds.

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
		.where(acc.name.isin(debtors_accounts(company)) if receivable else (acc.root_type == root_type))
		.where(acc.is_group == 0)
		.where(gle.posting_date <= period_list[-1]["to_date"])
	)
	query = apply_additional_conditions(
		"GL Entry", query, period_list[0]["year_start_date"], True, filters
	)
	sql, params = query.walk()

	# The cash link: the same voucher moves a Bank or Cash account the other way
	# (this line debited while the bank / cash is credited, or the reverse). That
	# is the pairing the GL's Against column describes, but read from the voucher
	# itself: Against is stored as text and keeps an account's old name after a
	# rename (e.g. "Blue Sky Bank - 7008 - MT", now "Bank-7008 - MT").
	types = ", ".join(frappe.db.escape(t) for t in CASH_ACCOUNT_TYPES)
	sql += f"""
		and `tabGL Entry`.voucher_type in ('Journal Entry', 'Payment Entry')
		and exists (
			select 1 from `tabGL Entry` cash_gle
			join `tabAccount` cash_acc on cash_acc.name = cash_gle.account
			where cash_gle.voucher_type = `tabGL Entry`.voucher_type
			  and cash_gle.voucher_no = `tabGL Entry`.voucher_no
			  and cash_gle.company = `tabGL Entry`.company
			  and cash_gle.is_cancelled = 0
			  and cash_acc.account_type in ({types})
			  and ((`tabGL Entry`.debit > 0 and cash_gle.credit > 0)
			       or (`tabGL Entry`.credit > 0 and cash_gle.debit > 0))
		)"""

	match = build_match_conditions("GL Entry")
	if match:
		sql += " and " + match

	return frappe.db.sql(sql, params, as_dict=True)
