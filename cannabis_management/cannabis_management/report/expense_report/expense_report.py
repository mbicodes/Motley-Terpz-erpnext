# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
#
# The TSBC Expense Report laid out by Expense Category instead of by account
# head. Same filter bar, same period columns, same indented tree, same Total
# row - only two things change:
#
#   * the first column holds the Expense Category (the ``custom_expense_category``
#     link on Purchase Invoice Item and Journal Entry Account) rather than an
#     account head, and
#   * the figures come straight off those two child tables instead of the
#     General Ledger. Every category lists the Purchase Invoices and Journal
#     Entries behind it, one indented row per voucher number with its date.
#
# Amounts are net and in company currency: ``base_net_amount`` for a Purchase
# Invoice Item (so a debit note / return subtracts, as it already carries a
# negative amount) and ``debit - credit`` for a Journal Entry Account (so a
# reversing entry subtracts too). Only submitted documents count, and only
# lines that actually carry a category - an uncategorised line appears nowhere
# on this report.

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.accounts.report.financial_statements import (
	compute_growth_view_data,
	get_columns,
	get_period_list,
)

PURCHASE_INVOICE = "Purchase Invoice"
JOURNAL_ENTRY = "Journal Entry"


def get_purchase_invoice_amounts(filters, from_date, to_date):
	"""Categorised Purchase Invoice Item lines, as (category, voucher_no,
	posting_date, amount) per invoice."""
	conditions = ""
	values = {
		"company": filters.company,
		"from_date": from_date,
		"to_date": to_date,
	}

	if filters.get("cost_center"):
		conditions += " and item.cost_center = %(cost_center)s"
		values["cost_center"] = filters.get("cost_center")

	if filters.get("project"):
		conditions += " and item.project = %(project)s"
		values["project"] = filters.get("project")

	return frappe.db.sql(
		f"""
		select
			item.custom_expense_category as expense_category,
			inv.name as voucher_no,
			inv.posting_date as posting_date,
			sum(item.base_net_amount) as amount
		from `tabPurchase Invoice Item` item
		inner join `tabPurchase Invoice` inv on inv.name = item.parent
		where
			inv.docstatus = 1
			and inv.company = %(company)s
			and inv.posting_date between %(from_date)s and %(to_date)s
			and ifnull(item.custom_expense_category, '') != ''
			{conditions}
		group by item.custom_expense_category, inv.name, inv.posting_date
		""",
		values,
		as_dict=1,
	)


def get_journal_entry_amounts(filters, from_date, to_date):
	"""Categorised Journal Entry Account lines, as (category, voucher_no,
	posting_date, amount) per entry.

	``debit - credit`` so a reversal nets off, mirroring how a Purchase
	Invoice return nets off on the other side.
	"""
	conditions = ""
	values = {
		"company": filters.company,
		"from_date": from_date,
		"to_date": to_date,
	}

	if filters.get("cost_center"):
		conditions += " and account.cost_center = %(cost_center)s"
		values["cost_center"] = filters.get("cost_center")

	if filters.get("project"):
		conditions += " and account.project = %(project)s"
		values["project"] = filters.get("project")

	# Finance book handling, same rule the financial statements use: a chosen
	# book shows that book's entries, plus the book-less ones when "Include
	# Default FB Entries" is ticked.
	if filters.get("finance_book"):
		values["finance_book"] = filters.get("finance_book")
		if filters.get("include_default_book_entries"):
			conditions += " and ifnull(je.finance_book, '') in (%(finance_book)s, '')"
		else:
			conditions += " and ifnull(je.finance_book, '') = %(finance_book)s"
	elif not filters.get("include_default_book_entries"):
		conditions += " and ifnull(je.finance_book, '') = ''"

	return frappe.db.sql(
		f"""
		select
			account.custom_expense_category as expense_category,
			je.name as voucher_no,
			je.posting_date as posting_date,
			sum(account.debit - account.credit) as amount
		from `tabJournal Entry Account` account
		inner join `tabJournal Entry` je on je.name = account.parent
		where
			je.docstatus = 1
			and je.company = %(company)s
			and je.posting_date between %(from_date)s and %(to_date)s
			and ifnull(account.custom_expense_category, '') != ''
			{conditions}
		group by account.custom_expense_category, je.name, je.posting_date
		""",
		values,
		as_dict=1,
	)


def get_amounts_by_category(filters, period_list):
	"""``{category: {(voucher_type, voucher_no, posting_date): {period_key: amount}}}``
	for the whole date span."""
	from_date = period_list[0]["from_date"]
	to_date = period_list[-1]["to_date"]

	sources = {
		PURCHASE_INVOICE: get_purchase_invoice_amounts(filters, from_date, to_date),
		JOURNAL_ENTRY: get_journal_entry_amounts(filters, from_date, to_date),
	}

	amounts = {}
	for voucher_type, entries in sources.items():
		for entry in entries:
			posting_date = getdate(entry.posting_date)
			period = next(
				(
					period
					for period in period_list
					if getdate(period["from_date"]) <= posting_date <= getdate(period["to_date"])
				),
				None,
			)
			if not period:
				continue

			by_voucher = amounts.setdefault(entry.expense_category, {})
			by_period = by_voucher.setdefault((voucher_type, entry.voucher_no, posting_date), {})
			by_period[period.key] = flt(by_period.get(period.key)) + flt(entry.amount)

	return amounts


def make_row(
	label, amounts, period_list, currency, indent, accumulated=False, parent=None, is_total=False
):
	"""One report row, filled period by period, with the running total applied
	when 'Accumulated Values' is on and a Total column when it is shown."""
	row = {
		"expense_category": label,
		"account_name": label,
		"posting_date": None,
		"currency": currency,
		"indent": indent,
		"has_value": False,
	}
	if parent:
		row["parent_account"] = parent
	if is_total:
		row["is_total_row"] = True

	total = 0.0
	for period in period_list:
		value = flt(amounts.get(period.key))
		total += value
		row[period.key] = total if accumulated else value
		if value:
			row["has_value"] = True

	row["total"] = total
	return row


def get_data(filters, period_list, currency):
	accumulated = bool(filters.get("accumulated_values"))
	amounts = get_amounts_by_category(filters, period_list)

	# Every category on record, so the report reads the same from period to
	# period, plus any category that has figures but no longer exists as a
	# master record.
	categories = frappe.get_all("Expense Category", pluck="name", order_by="name")
	categories += sorted(set(amounts) - set(categories))

	show_zero_values = filters.get("show_zero_values")

	data = []
	totals = {}
	for category in categories:
		by_voucher = amounts.get(category, {})

		category_amounts = {}
		for voucher_amounts in by_voucher.values():
			for key, value in voucher_amounts.items():
				category_amounts[key] = flt(category_amounts.get(key)) + flt(value)

		category_row = make_row(
			category, category_amounts, period_list, currency, indent=0, accumulated=accumulated
		)
		if not category_row["has_value"] and not show_zero_values:
			continue

		data.append(category_row)

		# Oldest first, so each category reads down the year.
		for voucher_type, voucher_no, posting_date in sorted(
			by_voucher, key=lambda key: (key[2], key[1])
		):
			voucher_row = make_row(
				voucher_no,
				by_voucher[(voucher_type, voucher_no, posting_date)],
				period_list,
				currency,
				indent=1,
				accumulated=accumulated,
				parent=category,
			)
			if not voucher_row["has_value"] and not show_zero_values:
				continue
			voucher_row.update(
				{"voucher_type": voucher_type, "voucher_no": voucher_no, "posting_date": posting_date}
			)
			data.append(voucher_row)

		for key, value in category_amounts.items():
			totals[key] = flt(totals.get(key)) + flt(value)

	if not data:
		return []

	label = "'" + _("Total Expense") + "'"
	total_row = make_row(
		label, totals, period_list, currency, indent=0, accumulated=accumulated, is_total=True
	)

	return data + [total_row, {}]


def get_report_columns(filters, period_list):
	"""erpnext's financial statement columns, with the account head swapped
	out for the Expense Category and a Date column beside it.

	Date goes second so the period columns keep their positions; the Growth
	View formatter picks them out by position.
	"""
	columns = get_columns(
		filters.periodicity, period_list, filters.accumulated_values, filters.company
	)
	columns[0] = {
		"fieldname": "expense_category",
		"label": _("Expense Category / Voucher No"),
		"fieldtype": "Data",
		"width": 300,
	}
	columns.insert(
		1,
		{
			"fieldname": "posting_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 110,
		},
	)

	return columns


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

	# Figures are booked in company currency (base_net_amount / debit / credit),
	# so that is what the report is stated in.
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	data = get_data(filters, period_list, currency)
	columns = get_report_columns(filters, period_list)

	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, data, currency, filters
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	return columns, data, None, None, report_summary, primitive_summary


def get_report_summary(period_list, periodicity, data, currency, filters):
	net_expense = 0.0

	if data:
		# The total row is the second-to-last, the blank spacer being last.
		total_row = data[-2]
		if filters.accumulated_values:
			# with 'accumulated_values' on, the last period already carries the
			# running total.
			net_expense = flt(total_row.get(period_list[-1].key))
		else:
			net_expense = sum(flt(total_row.get(period.key)) for period in period_list)

	if len(period_list) == 1 and periodicity == "Yearly":
		expense_label = _("Total Expense This Year")
	else:
		expense_label = _("Total Expense")

	return [
		{"value": net_expense, "label": expense_label, "datatype": "Currency", "currency": currency},
	], net_expense
