# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
#
# Local copy of erpnext.accounts.report.financial_statements, kept in sync
# with upstream except for one change: get_data() drops group/parent account
# rows from its output so callers (e.g. this app's Profit and Loss Statement
# (Child Accounts) report) only ever see leaf accounts. See the "Cannabis
# Management customization" block inside get_data().


import copy
import functools
import math
import re

import frappe
from frappe import _
from frappe.query_builder.functions import Max, Min, Sum
from frappe.utils import add_days, add_months, cint, cstr, flt, formatdate, get_first_day, getdate
from pypika.terms import ExistsCriterion

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
	get_dimension_with_children,
)
from erpnext.accounts.report.utils import convert_to_presentation_currency, get_currency
from erpnext.accounts.utils import get_fiscal_year, get_zero_cutoff
from erpnext.stock import get_warehouse_account_map


def get_period_list(
	from_fiscal_year,
	to_fiscal_year,
	period_start_date,
	period_end_date,
	filter_based_on,
	periodicity,
	accumulated_values=False,
	company=None,
	reset_period_on_fy_change=True,
	ignore_fiscal_year=False,
):
	"""Get a list of dict {"from_date": from_date, "to_date": to_date, "key": key, "label": label}
	Periodicity can be (Yearly, Quarterly, Monthly)"""

	if filter_based_on == "Fiscal Year":
		fiscal_year = get_fiscal_year_data(from_fiscal_year, to_fiscal_year)
		validate_fiscal_year(fiscal_year, from_fiscal_year, to_fiscal_year)
		year_start_date = getdate(fiscal_year.year_start_date)
		year_end_date = getdate(fiscal_year.year_end_date)
	else:
		validate_dates(period_start_date, period_end_date)
		year_start_date = getdate(period_start_date)
		year_end_date = getdate(period_end_date)

	months_to_add = {"Yearly": 12, "Half-Yearly": 6, "Quarterly": 3, "Monthly": 1}[periodicity]

	period_list = []

	start_date = year_start_date
	months = get_months(year_start_date, year_end_date)

	for i in range(cint(math.ceil(months / months_to_add))):
		period = frappe._dict({"from_date": start_date})

		if i == 0 and filter_based_on == "Date Range":
			to_date = add_months(get_first_day(start_date), months_to_add)
		else:
			to_date = add_months(start_date, months_to_add)

		start_date = to_date

		# Subtract one day from to_date, as it may be first day in next fiscal year or month
		to_date = add_days(to_date, -1)

		if to_date <= year_end_date:
			# the normal case
			period.to_date = to_date
		else:
			# if a fiscal year ends before a 12 month period
			period.to_date = year_end_date

		if not ignore_fiscal_year:
			period.to_date_fiscal_year = get_fiscal_year(period.to_date, company=company)[0]
			period.from_date_fiscal_year_start_date = get_fiscal_year(period.from_date, company=company)[1]

		period_list.append(period)

		if period.to_date == year_end_date:
			break

	# common processing
	for opts in period_list:
		key = opts["to_date"].strftime("%b_%Y").lower()
		if periodicity == "Monthly" and not accumulated_values:
			label = formatdate(opts["to_date"], "MMM YYYY")
		else:
			if not accumulated_values:
				label = get_label(periodicity, opts["from_date"], opts["to_date"])
			else:
				if reset_period_on_fy_change:
					label = get_label(periodicity, opts.from_date_fiscal_year_start_date, opts["to_date"])
				else:
					label = get_label(periodicity, period_list[0].from_date, opts["to_date"])

		opts.update(
			{
				"key": key.replace(" ", "_").replace("-", "_"),
				"label": label,
				"year_start_date": year_start_date,
				"year_end_date": year_end_date,
			}
		)

	return period_list


def get_fiscal_year_data(from_fiscal_year, to_fiscal_year):
	from_year_start_date = frappe.get_cached_value("Fiscal Year", from_fiscal_year, "year_start_date")
	to_year_end_date = frappe.get_cached_value("Fiscal Year", to_fiscal_year, "year_end_date")

	fy = frappe.qb.DocType("Fiscal Year")

	query = (
		frappe.qb.from_(fy)
		.select(Min(fy.year_start_date).as_("year_start_date"), Max(fy.year_end_date).as_("year_end_date"))
		.where(fy.year_start_date >= from_year_start_date)
		.where(fy.year_end_date <= to_year_end_date)
	)

	fiscal_year = query.run(as_dict=True)
	return fiscal_year[0] if fiscal_year else {}


def validate_fiscal_year(fiscal_year, from_fiscal_year, to_fiscal_year):
	if not fiscal_year.get("year_start_date") or not fiscal_year.get("year_end_date"):
		frappe.throw(_("Start Year and End Year are mandatory"))

	if getdate(fiscal_year.get("year_end_date")) < getdate(fiscal_year.get("year_start_date")):
		frappe.throw(_("End Year cannot be before Start Year"))


def validate_dates(from_date, to_date):
	if not from_date or not to_date:
		frappe.throw(_("From Date and To Date are mandatory"))

	if to_date < from_date:
		frappe.throw(_("To Date cannot be less than From Date"))


def get_months(start_date, end_date):
	diff = (12 * end_date.year + end_date.month) - (12 * start_date.year + start_date.month)
	return diff + 1


def get_label(periodicity, from_date, to_date):
	if periodicity == "Yearly":
		if formatdate(from_date, "YYYY") == formatdate(to_date, "YYYY"):
			label = formatdate(from_date, "YYYY")
		else:
			label = formatdate(from_date, "YYYY") + "-" + formatdate(to_date, "YYYY")
	else:
		label = formatdate(from_date, "MMM YY") + "-" + formatdate(to_date, "MMM YY")

	return label


def get_data(
	company,
	root_type,
	balance_must_be,
	period_list,
	filters=None,
	accumulated_values=1,
	only_current_fiscal_year=True,
	ignore_closing_entries=False,
	ignore_accumulated_values_for_fy=False,
	total=True,
):
	accounts = get_accounts(company, root_type)
	if not accounts:
		return None

	accounts, accounts_by_name, parent_children_map = filter_accounts(accounts)

	company_currency = get_appropriate_currency(company, filters)

	gl_entries_by_account = {}
	for root in frappe.db.sql(
		"""select lft, rgt from tabAccount
			where root_type=%s and ifnull(parent_account, '') = ''""",
		root_type,
		as_dict=1,
	):
		set_gl_entries_by_account(
			company,
			period_list[0]["year_start_date"] if only_current_fiscal_year else None,
			period_list[-1]["to_date"],
			filters,
			gl_entries_by_account,
			root.lft,
			root.rgt,
			root_type=root_type,
			ignore_closing_entries=ignore_closing_entries,
		)

	calculate_values(
		accounts_by_name,
		gl_entries_by_account,
		period_list,
		accumulated_values,
		ignore_accumulated_values_for_fy,
	)
	accumulate_values_into_parents(accounts, accounts_by_name, period_list)
	out = prepare_data(
		accounts,
		balance_must_be,
		period_list,
		company_currency,
		accumulated_values=filters.accumulated_values,
	)
	out = filter_out_zero_value_rows(out, parent_children_map, filters.show_zero_values)

	# --- Cannabis Management customization: only child (leaf) accounts ---
	# Group/parent accounts already had every child's value rolled up into them
	# (accumulate_values_into_parents above) purely so totals stay correct.
	# Drop them from the display and clear parent_account on what's left so
	# add_total_row's "no parent_account" check below sums every remaining
	# (leaf) row instead of just top-level groups.
	out = [row for row in out if not row.get("is_group")]
	for row in out:
		row["indent"] = 0
		row["parent_account"] = ""

	if out and total:
		add_total_row(out, root_type, balance_must_be, period_list, company_currency)

	return out


def get_appropriate_currency(company, filters=None):
	if filters and filters.get("presentation_currency"):
		return filters["presentation_currency"]
	else:
		return frappe.get_cached_value("Company", company, "default_currency")


def calculate_values(
	accounts_by_name,
	gl_entries_by_account,
	period_list,
	accumulated_values,
	ignore_accumulated_values_for_fy,
):
	for entries in gl_entries_by_account.values():
		for entry in entries:
			d = accounts_by_name.get(entry.account)
			if not d:
				frappe.msgprint(
					_("Could not retrieve information for {0}.").format(entry.account),
					title="Error",
					raise_exception=1,
				)
			for period in period_list:
				# check if posting date is within the period

				if entry.posting_date <= period.to_date:
					if (accumulated_values or entry.posting_date >= period.from_date) and (
						not ignore_accumulated_values_for_fy
						or entry.fiscal_year == period.to_date_fiscal_year
					):
						d[period.key] = d.get(period.key, 0.0) + flt(entry.debit) - flt(entry.credit)

			if entry.posting_date < period_list[0].year_start_date:
				d["opening_balance"] = d.get("opening_balance", 0.0) + flt(entry.debit) - flt(entry.credit)


def accumulate_values_into_parents(accounts, accounts_by_name, period_list):
	"""accumulate children's values in parent accounts"""
	for d in reversed(accounts):
		if d.parent_account:
			for period in period_list:
				accounts_by_name[d.parent_account][period.key] = accounts_by_name[d.parent_account].get(
					period.key, 0.0
				) + d.get(period.key, 0.0)

			accounts_by_name[d.parent_account]["opening_balance"] = accounts_by_name[d.parent_account].get(
				"opening_balance", 0.0
			) + d.get("opening_balance", 0.0)


def prepare_data(accounts, balance_must_be, period_list, company_currency, accumulated_values):
	data = []
	year_start_date = period_list[0]["year_start_date"].strftime("%Y-%m-%d")
	year_end_date = period_list[-1]["year_end_date"].strftime("%Y-%m-%d")

	for d in accounts:
		# add to output
		has_value = False
		total = 0
		row = frappe._dict(
			{
				"account": _(d.name),
				"parent_account": _(d.parent_account) if d.parent_account else "",
				"indent": flt(d.indent),
				"year_start_date": year_start_date,
				"year_end_date": year_end_date,
				"currency": company_currency,
				"include_in_gross": d.include_in_gross,
				"account_type": d.account_type,
				"is_group": d.is_group,
				"opening_balance": d.get("opening_balance", 0.0) * (1 if balance_must_be == "Debit" else -1),
				"account_name": (
					f"{_(d.account_number)} - {_(d.account_name)}" if d.account_number else _(d.account_name)
				),
			}
		)
		for period in period_list:
			if d.get(period.key) and balance_must_be == "Credit":
				# change sign based on Debit or Credit, since calculation is done using (debit - credit)
				d[period.key] *= -1

			row[period.key] = flt(d.get(period.key, 0.0), 3)

			if abs(row[period.key]) >= get_zero_cutoff(company_currency):
				# ignore zero values
				has_value = True
				total += flt(row[period.key])

		if accumulated_values:
			# when 'accumulated_values' is enabled, periods have running balance.
			# so, last period will have the net amount.
			row["has_value"] = has_value
			row["total"] = flt(d.get(period_list[-1].key, 0.0), 3)
		else:
			row["has_value"] = has_value
			row["total"] = total
		data.append(row)

	return data


def filter_out_zero_value_rows(data, parent_children_map, show_zero_values=False):
	def get_all_parents(account, parent_children_map):
		for parent, children in parent_children_map.items():
			for child in children:
				if child["name"] == account and parent:
					accounts_to_show.add(parent)
					get_all_parents(parent, parent_children_map)

	data_with_value = []
	accounts_to_show = set()

	for d in data:
		if show_zero_values or d.get("has_value"):
			accounts_to_show.add(d.get("account"))
			get_all_parents(d.get("account"), parent_children_map)

	for d in data:
		if d.get("account") in accounts_to_show:
			data_with_value.append(d)

	return data_with_value


def add_total_row(out, root_type, balance_must_be, period_list, company_currency):
	total_row = {
		"account_name": "'" + _("Total {0} ({1})").format(_(root_type), _(balance_must_be)) + "'",
		"account": "'" + _("Total {0} ({1})").format(_(root_type), _(balance_must_be)) + "'",
		"currency": company_currency,
		"opening_balance": 0.0,
		"is_total_row": 1,
	}

	for row in out:
		if not row.get("parent_account"):
			for period in period_list:
				total_row.setdefault(period.key, 0.0)
				total_row[period.key] += row.get(period.key, 0.0)

			total_row.setdefault("total", 0.0)
			total_row["total"] += flt(row["total"])
			total_row["opening_balance"] += row["opening_balance"]

	if "total" in total_row:
		out.append(total_row)

		# blank row after Total
		out.append({})


def get_accounts(company, root_type):
	return frappe.db.sql(
		"""
		select name, account_number, parent_account, lft, rgt, root_type, report_type, account_name, include_in_gross, account_type, is_group, lft, rgt
		from `tabAccount`
		where company=%s and root_type=%s order by lft""",
		(company, root_type),
		as_dict=True,
	)


def filter_accounts(accounts, depth=20):
	parent_children_map = {}
	accounts_by_name = {}
	for d in accounts:
		accounts_by_name[d.name] = d
		parent_children_map.setdefault(d.parent_account or None, []).append(d)

	filtered_accounts = []

	def add_to_list(parent, level):
		if level < depth:
			children = parent_children_map.get(parent) or []
			sort_accounts(children, is_root=True if parent is None else False)

			for child in children:
				child.indent = level
				filtered_accounts.append(child)
				add_to_list(child.name, level + 1)

	add_to_list(None, 0)

	return filtered_accounts, accounts_by_name, parent_children_map


def sort_accounts(accounts, is_root=False, key="name"):
	"""Sort root types as Asset, Liability, Equity, Income, Expense"""

	def compare_accounts(a, b):
		if re.split(r"\W+", a[key])[0].isdigit():
			# if chart of accounts is numbered, then sort by number
			return int(a[key] > b[key]) - int(a[key] < b[key])
		elif is_root:
			if a.report_type != b.report_type and a.report_type == "Balance Sheet":
				return -1
			if a.root_type != b.root_type and a.root_type == "Asset":
				return -1
			if a.root_type == "Liability" and b.root_type == "Equity":
				return -1
			if a.root_type == "Income" and b.root_type == "Expense":
				return -1
		else:
			# sort by key (number) or name
			return int(a[key] > b[key]) - int(a[key] < b[key])
		return 1

	accounts.sort(key=functools.cmp_to_key(compare_accounts))


def set_gl_entries_by_account(
	company,
	from_date,
	to_date,
	filters,
	gl_entries_by_account,
	root_lft=None,
	root_rgt=None,
	root_type=None,
	ignore_closing_entries=False,
	ignore_opening_entries=False,
	group_by_account=False,
):
	"""Returns a dict like { "account": [gl entries], ... }"""
	gl_entries = []

	# For balance sheet
	ignore_closing_balances = frappe.db.get_single_value(
		"Accounts Settings", "ignore_account_closing_balance"
	)
	if not from_date and not ignore_closing_balances:
		last_period_closing_voucher = frappe.db.get_all(
			"Period Closing Voucher",
			filters={
				"docstatus": 1,
				"company": filters.company,
				"period_end_date": ("<", filters["period_start_date"]),
			},
			fields=["period_end_date", "name"],
			order_by="period_end_date desc",
			limit=1,
		)
		if last_period_closing_voucher:
			gl_entries += get_accounting_entries(
				"Account Closing Balance",
				from_date,
				to_date,
				filters,
				root_lft,
				root_rgt,
				root_type,
				ignore_closing_entries,
				last_period_closing_voucher[0].name,
				group_by_account=group_by_account,
			)
			from_date = add_days(last_period_closing_voucher[0].period_end_date, 1)
			ignore_opening_entries = True

	gl_entries += get_accounting_entries(
		"GL Entry",
		from_date,
		to_date,
		filters,
		root_lft,
		root_rgt,
		root_type,
		ignore_closing_entries,
		ignore_opening_entries=ignore_opening_entries,
		group_by_account=group_by_account,
	)

	if filters and filters.get("presentation_currency"):
		convert_to_presentation_currency(gl_entries, get_currency(filters))

	for entry in gl_entries:
		gl_entries_by_account.setdefault(entry.account, []).append(entry)

	return gl_entries_by_account


def get_accounting_entries(
	doctype,
	from_date,
	to_date,
	filters,
	root_lft=None,
	root_rgt=None,
	root_type=None,
	ignore_closing_entries=None,
	period_closing_voucher=None,
	ignore_opening_entries=False,
	group_by_account=False,
):
	gl_entry = frappe.qb.DocType(doctype)
	query = (
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.account,
			gl_entry.debit if not group_by_account else Sum(gl_entry.debit).as_("debit"),
			gl_entry.credit if not group_by_account else Sum(gl_entry.credit).as_("credit"),
			gl_entry.debit_in_account_currency
			if not group_by_account
			else Sum(gl_entry.debit_in_account_currency).as_("debit_in_account_currency"),
			gl_entry.credit_in_account_currency
			if not group_by_account
			else Sum(gl_entry.credit_in_account_currency).as_("credit_in_account_currency"),
			gl_entry.account_currency,
		)
		.where(gl_entry.company == filters.company)
	)

	ignore_is_opening = frappe.db.get_single_value(
		"Accounts Settings", "ignore_is_opening_check_for_reporting"
	)

	if doctype == "GL Entry":
		query = query.select(gl_entry.posting_date, gl_entry.is_opening, gl_entry.fiscal_year)
		query = query.where(gl_entry.is_cancelled == 0)
		query = query.where(gl_entry.posting_date <= to_date)
		query = query.force_index("posting_date_company_index")

		if ignore_opening_entries and not ignore_is_opening:
			query = query.where(gl_entry.is_opening == "No")
	else:
		query = query.select(gl_entry.closing_date.as_("posting_date"))
		query = query.where(gl_entry.period_closing_voucher == period_closing_voucher)

	query = apply_additional_conditions(doctype, query, from_date, ignore_closing_entries, filters)

	if (root_lft and root_rgt) or root_type:
		account_filter_query = get_account_filter_query(root_lft, root_rgt, root_type, gl_entry)
		query = query.where(ExistsCriterion(account_filter_query))

	from frappe.desk.reportview import build_match_conditions

	query, params = query.walk()
	match_conditions = build_match_conditions(doctype)

	if match_conditions:
		query += "and" + match_conditions

	if group_by_account:
		query += " GROUP BY `account`"

	return frappe.db.sql(query, params, as_dict=True)


def get_account_filter_query(root_lft, root_rgt, root_type, gl_entry):
	acc = frappe.qb.DocType("Account")
	exists_query = (
		frappe.qb.from_(acc).select(acc.name).where(acc.name == gl_entry.account).where(acc.is_group == 0)
	)
	if root_lft and root_rgt:
		exists_query = exists_query.where(acc.lft >= root_lft).where(acc.rgt <= root_rgt)

	if root_type:
		exists_query = exists_query.where(acc.root_type == root_type)

	return exists_query


def apply_additional_conditions(doctype, query, from_date, ignore_closing_entries, filters):
	gl_entry = frappe.qb.DocType(doctype)
	accounting_dimensions = get_accounting_dimensions(as_list=False)

	if ignore_closing_entries:
		if doctype == "GL Entry":
			query = query.where(gl_entry.voucher_type != "Period Closing Voucher")
		else:
			query = query.where(gl_entry.is_period_closing_voucher_entry == 0)

	if from_date and doctype == "GL Entry":
		query = query.where(gl_entry.posting_date >= from_date)

	if filters:
		if filters.get("project"):
			if not isinstance(filters.get("project"), list):
				filters.project = frappe.parse_json(filters.get("project"))

			query = query.where(gl_entry.project.isin(filters.project))

		if filters.get("cost_center"):
			filters.cost_center = get_cost_centers_with_children(filters.cost_center)
			query = query.where(gl_entry.cost_center.isin(filters.cost_center))

		if filters.get("include_default_book_entries"):
			company_fb = frappe.get_cached_value("Company", filters.company, "default_finance_book")

			if filters.finance_book and company_fb and cstr(filters.finance_book) != cstr(company_fb):
				frappe.throw(
					_("To use a different finance book, please uncheck 'Include Default FB Entries'")
				)

			query = query.where(
				(gl_entry.finance_book.isin([cstr(filters.finance_book), cstr(company_fb), ""]))
				| (gl_entry.finance_book.isnull())
			)
		else:
			query = query.where(
				(gl_entry.finance_book.isin([cstr(filters.finance_book), ""]))
				| (gl_entry.finance_book.isnull())
			)

	if accounting_dimensions:
		for dimension in accounting_dimensions:
			if filters.get(dimension.fieldname):
				if frappe.get_cached_value("DocType", dimension.document_type, "is_tree"):
					filters[dimension.fieldname] = get_dimension_with_children(
						dimension.document_type, filters.get(dimension.fieldname)
					)

				query = query.where(gl_entry[dimension.fieldname].isin(filters[dimension.fieldname]))

	return query


def get_cost_centers_with_children(cost_centers):
	if not isinstance(cost_centers, list):
		cost_centers = [d.strip() for d in cost_centers.strip().split(",") if d]

	all_cost_centers = []
	for d in cost_centers:
		if frappe.db.exists("Cost Center", d):
			lft, rgt = frappe.db.get_value("Cost Center", d, ["lft", "rgt"])
			children = frappe.get_all("Cost Center", filters={"lft": [">=", lft], "rgt": ["<=", rgt]})
			all_cost_centers += [c.name for c in children]
		else:
			frappe.throw(_("Cost Center: {0} does not exist").format(d))

	return list(set(all_cost_centers))


def get_columns(periodicity, period_list, accumulated_values=1, company=None, cash_flow=False):
	columns = [
		{
			"fieldname": "account" if not cash_flow else "section",
			"label": _("Account") if not cash_flow else _("Section"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 300,
		}
	]
	if company:
		columns.append(
			{
				"fieldname": "currency",
				"label": _("Currency"),
				"fieldtype": "Link",
				"options": "Currency",
				"hidden": 1,
			}
		)
	for period in period_list:
		columns.append(
			{
				"fieldname": period.key,
				"label": period.label,
				"fieldtype": "Currency",
				"options": "currency",
				"width": 150,
			}
		)
	if periodicity != "Yearly":
		if not accumulated_values:
			columns.append(
				{
					"fieldname": "total",
					"label": _("Total"),
					"fieldtype": "Currency",
					"width": 150,
					"options": "currency",
				}
			)

	return columns


def get_filtered_list_for_consolidated_report(filters, period_list):
	filtered_summary_list = []
	for period in period_list:
		if period == filters.get("company"):
			filtered_summary_list.append(period)

	return filtered_summary_list


def compute_growth_view_data(data, columns):
	data_copy = copy.deepcopy(data)

	for row_idx in range(len(data_copy)):
		for column_idx in range(1, len(columns)):
			previous_period_key = columns[column_idx - 1].get("key")
			current_period_key = columns[column_idx].get("key")
			current_period_value = data_copy[row_idx].get(current_period_key)
			previous_period_value = data_copy[row_idx].get(previous_period_key)
			annual_growth = 0

			if current_period_value is None:
				data[row_idx][current_period_key] = None
				continue

			if previous_period_value == 0 and current_period_value > 0:
				annual_growth = 1

			elif previous_period_value > 0:
				annual_growth = (current_period_value - previous_period_value) / previous_period_value

			growth_percent = round(annual_growth * 100, 2)

			data[row_idx][current_period_key] = growth_percent


VOUCHER_ITEM_DOCTYPE = {
	# (item doctype, selling/buying rate fieldname, valuation/cost rate
	# fieldname). Which of the two rate columns is used is a per-call choice
	# (see attach_transaction_rows()'s use_valuation_rate) - COGS accounts
	# want to show what the stock actually cost, everywhere else (Income,
	# Expense, Balance Sheet accounts) wants what it was actually invoiced
	# at. Sales Invoice/Delivery Note items don't have a "valuation_rate"
	# field of their own; "incoming_rate" is ERPNext's own field for the
	# same thing on outward stock movements. Stock Entry/Stock
	# Reconciliation are pure inventory movements with no selling price at
	# all, so both columns point at the same valuation_rate field.
	"Sales Invoice": ("Sales Invoice Item", "rate", "incoming_rate"),
	"Purchase Invoice": ("Purchase Invoice Item", "rate", "valuation_rate"),
	"Delivery Note": ("Delivery Note Item", "rate", "incoming_rate"),
	"Purchase Receipt": ("Purchase Receipt Item", "rate", "valuation_rate"),
	"Stock Entry": ("Stock Entry Detail", "valuation_rate", "valuation_rate"),
	"Stock Reconciliation": ("Stock Reconciliation Item", "valuation_rate", "valuation_rate"),
}

# Which item-row fields can identify the ONE GL account a given item actually
# posted to, per voucher type - used by attach_transaction_rows() to filter
# items_by_voucher() down to only the items relevant to the leaf account
# currently being drilled into (see item_matches_account() below). A single
# voucher's item table can span several accounts at once (e.g. a Delivery
# Note posting several items out of warehouse A and several out of warehouse
# B, each warehouse mapped to a different stock account, all summarized into
# one combined COGS entry): without this filter, every item on the voucher
# was shown under every one of the voucher's GL entries, regardless of which
# account that item actually affected.
#
# "direct": fields holding an actual Account name to compare against
# entry.account as-is (income/expense accounts, which the item carries
# directly). "warehouse": fields holding a Warehouse name, resolved to that
# warehouse's stock account via get_warehouse_account_map() before comparing
# - covers the asset/stock side of the same postings, where the item only
# knows which warehouse it moved through, not the account name itself.
VOUCHER_ITEM_ACCOUNT_FIELDS = {
	"Sales Invoice": {"direct": ("income_account", "expense_account"), "warehouse": ("warehouse", "target_warehouse")},
	"Purchase Invoice": {"direct": ("expense_account",), "warehouse": ("warehouse", "from_warehouse")},
	"Delivery Note": {"direct": ("expense_account",), "warehouse": ("warehouse", "target_warehouse")},
	"Purchase Receipt": {"direct": ("expense_account",), "warehouse": ("warehouse", "from_warehouse")},
	"Stock Entry": {"direct": ("expense_account",), "warehouse": ("s_warehouse", "t_warehouse")},
	"Stock Reconciliation": {"direct": (), "warehouse": ("warehouse",)},
}


def item_matches_account(item, voucher_type, account, warehouse_account_map):
	"""True if `item` (one row from items_by_voucher()) is actually one of the
	items that posted to `account` on this voucher - see
	VOUCHER_ITEM_ACCOUNT_FIELDS above. Voucher types with no mapping here fail
	open (keep the item) rather than silently hiding data for a type nobody's
	verified yet."""
	field_map = VOUCHER_ITEM_ACCOUNT_FIELDS.get(voucher_type)
	if not field_map:
		return True

	for fieldname in field_map["direct"]:
		if item.get(fieldname) == account:
			return True

	for fieldname in field_map["warehouse"]:
		warehouse = item.get(fieldname)
		if warehouse and warehouse_account_map.get(warehouse, {}).get("account") == account:
			return True

	return False


def blank_group_amounts(rows, period_list):
	"""Blank every period + total cell on group/parent account rows in place.
	Leaf accounts, transaction rows and item rows (none of which carry
	is_group) are left untouched, and so are the synthetic total/heading
	rows built elsewhere (they never set is_group either)."""
	for row in rows:
		if row.get("is_group"):
			for period in period_list:
				row[period.key] = None
			row["total"] = None


VALUATION_RATE_ACCOUNT_TYPES = {"Stock", "Stock Adjustment"}

# Voucher types the Stock Valuation Lineage report can backward-trace from
# (see get_item_lineage() in that report's .py) - only these item rows get
# the extra "trace lineage" expand step in the COGS branch.
LINEAGE_VOUCHER_TYPES = ("Sales Invoice", "Delivery Note")


def attach_transaction_rows(rows, filters, period_list, currency, use_valuation_rate=False):
	"""Expand every leaf account row in `rows` with its own transactions
	(vouchers) as indented child rows in this same tree - clicking the
	account's expand arrow reveals them right here, no separate General
	Ledger report involved. Vouchers with their own item table (see
	VOUCHER_ITEM_DOCTYPE) get one level further: their line items as
	grandchild rows.

	use_valuation_rate: pass True to force valuation/cost rate for every
	leaf account in this call - used for the Profit and Loss Statement's
	COGS branch, whose accounts are identified by name (see
	get_cogs_anchor_account_names() in profit_and_loss_statement_child_accounts.py),
	not a reliable account_type, so an explicit override is the only
	trustworthy signal there.

	Left False (the default), each leaf account decides for itself instead:
	Stock/Stock Adjustment accounts (VALUATION_RATE_ACCOUNT_TYPES) show
	valuation rate, everything else (Receivable, Payable, Bank, Income,
	Expense, ...) shows the selling/buying rate - this is what the Detailed
	Balance Sheet relies on, since its Asset tree mixes Stock accounts in
	with Receivable/Payable/Bank in the very same call, and the same
	voucher (e.g. a stock-updating Sales Invoice) can post to both a
	Receivable account and a Stock account at once, each wanting a
	different rate for the exact same line item.

	Group rows are left untouched (Frappe doesn't allow postings directly on
	a group account, so they never have transactions of their own)."""
	leaf_accounts = [row["account"] for row in rows if row.get("account") and not row.get("is_group")]
	if not leaf_accounts:
		return rows

	account_types = {}
	if not use_valuation_rate:
		account_types = {
			a.name: a.account_type
			for a in frappe.get_all(
				"Account", filters={"name": ["in", leaf_accounts]}, fields=["name", "account_type"]
			)
		}

	gl_entries = get_account_transactions(leaf_accounts, filters, period_list)
	if filters.get("presentation_currency"):
		convert_to_presentation_currency(gl_entries, get_currency(filters))

	entries_by_account = {}
	for entry in gl_entries:
		entries_by_account.setdefault(entry.account, []).append(entry)

	items_by_voucher = get_item_rows_by_voucher(gl_entries)
	warehouse_account_map = get_warehouse_account_map(filters.get("company"))

	out = []
	for row in rows:
		out.append(row)
		account = row.get("account")
		if not account or row.get("is_group"):
			continue

		account_indent = flt(row.get("indent", 0))
		account_uses_valuation_rate = use_valuation_rate or account_types.get(account) in VALUATION_RATE_ACCOUNT_TYPES

		for entry in entries_by_account.get(account, []):
			txn_key = f"{account}::txn::{entry.name}"
			out.append(
				make_transaction_row(
					txn_key, account, account_indent + 1, entry, period_list, currency
				)
			)

			if entry.voucher_type not in VOUCHER_ITEM_DOCTYPE:
				continue

			# Only forced valuation (the P&L COGS branch) offers the lineage
			# drill-down - Balance Sheet's Stock accounts also show valuation
			# rate (via the account_type auto-detect above) but weren't part
			# of what was asked for here, so they don't get the extra step.
			show_lineage = use_valuation_rate and entry.voucher_type in LINEAGE_VOUCHER_TYPES

			voucher_items = items_by_voucher.get((entry.voucher_type, entry.voucher_no), [])
			matching_items = [
				item
				for item in voucher_items
				if item_matches_account(item, entry.voucher_type, account, warehouse_account_map)
			]

			for item in matching_items:
				out.append(
					make_item_row(
						txn_key,
						account_indent + 2,
						item,
						period_list,
						currency,
						account_uses_valuation_rate,
						show_lineage=show_lineage,
						voucher_type=entry.voucher_type,
					)
				)

	return out


def make_transaction_row(txn_key, parent_account, indent, entry, period_list, currency):
	row = {
		# Quoted like make_total_row()/make_diff_row()'s synthetic rows -
		# the "account" column is fieldtype Link/Account, and frappe's Link
		# formatter special-cases a 'quoted' value to render as plain text
		# instead of building a (here, broken - txn_key isn't a real Account)
		# link to /app/account/<value>. Only real leaf account rows should
		# ever be clickable through to an actual Account record.
		"account": "'" + txn_key + "'",
		"parent_account": parent_account,
		"indent": indent,
		"account_name": f"{entry.voucher_type} {entry.voucher_no}",
		"currency": currency,
		"posting_date": entry.posting_date,
		"voucher_type": entry.voucher_type,
		"voucher_no": entry.voucher_no,
		"party": entry.party,
		"against": entry.against,
		"debit": entry.debit,
		"credit": entry.credit,
	}
	for period in period_list:
		row[period.key] = None
	row["total"] = None
	return row


def make_item_row(
	parent_key, indent, item, period_list, currency, use_valuation_rate, show_lineage=False, voucher_type=None
):
	rate = item.valuation_rate if use_valuation_rate else item.selling_rate
	# Recomputed rather than taken from the document's own stored amount -
	# that amount is always qty * selling rate, even when valuation rate is
	# what's about to be shown here, so trusting it would show a rate and
	# amount that don't multiply out to each other.
	amount = flt(item.qty) * flt(rate)
	row = {
		# Quoted for the same reason as make_transaction_row() above.
		"account": "'" + f"{parent_key}::item::{item.idx}" + "'",
		"parent_account": parent_key,
		"indent": indent,
		"account_name": item.item_name or item.item_code,
		"currency": currency,
		"item_code": item.item_code,
		"item_name": item.item_name,
		"qty": item.qty,
		"rate": rate,
		"amount": amount,
	}
	if show_lineage:
		# Everything get_item_lineage() (stock_valuation_lineage.py) needs to
		# re-identify this exact sold Stock Ledger Entry on demand - the
		# frontend calls it only when this row is actually expanded, instead
		# of every item in the report being traced up front.
		row["show_lineage"] = True
		row["warehouse"] = item.warehouse
		row["voucher_type"] = voucher_type
		row["voucher_no"] = item.parent
	for period in period_list:
		row[period.key] = None
	row["total"] = None
	return row


def get_account_transactions(accounts, filters, period_list):
	gl_entry = frappe.qb.DocType("GL Entry")
	query = (
		frappe.qb.from_(gl_entry)
		.select(
			gl_entry.name,
			gl_entry.posting_date,
			gl_entry.voucher_type,
			gl_entry.voucher_no,
			gl_entry.against,
			gl_entry.party_type,
			gl_entry.party,
			gl_entry.account,
			gl_entry.debit,
			gl_entry.credit,
			gl_entry.debit_in_account_currency,
			gl_entry.credit_in_account_currency,
			gl_entry.account_currency,
		)
		.where(gl_entry.company == filters.company)
		.where(gl_entry.is_cancelled == 0)
		.where(gl_entry.account.isin(accounts))
		.where(gl_entry.posting_date >= period_list[0]["year_start_date"])
		.where(gl_entry.posting_date <= period_list[-1]["to_date"])
		.orderby(gl_entry.posting_date)
		.orderby(gl_entry.creation)
	)
	# Same finance book / cost center / project / accounting dimension
	# filters the account totals above were computed with, so the
	# transactions listed under an account always match its total.
	query = apply_additional_conditions("GL Entry", query, None, True, filters)
	return query.run(as_dict=True)


def get_item_rows_by_voucher(gl_entries):
	"""Fetches BOTH the selling/buying rate and the valuation/cost rate for
	every item, aliased uniformly regardless of voucher type - which one
	make_item_row() actually uses is decided per leaf account by its caller
	(attach_transaction_rows()), not here, since the very same voucher can
	be attached under two different accounts in the same call that each
	want a different rate (e.g. a stock-updating Sales Invoice posts to
	both a Receivable account and a Stock account)."""
	voucher_names_by_doctype = {}
	for entry in gl_entries:
		if entry.voucher_type in VOUCHER_ITEM_DOCTYPE:
			voucher_names_by_doctype.setdefault(entry.voucher_type, set()).add(entry.voucher_no)

	items_by_voucher = {}
	for voucher_type, voucher_names in voucher_names_by_doctype.items():
		item_doctype, selling_rate_field, valuation_rate_field = VOUCHER_ITEM_DOCTYPE[voucher_type]
		fields = [
			"parent",
			"idx",
			"item_code",
			"item_name",
			"qty",
			f"{selling_rate_field} as selling_rate",
			f"{valuation_rate_field} as valuation_rate",
		]
		# Also fetch whichever fields item_matches_account() needs to tell
		# which account/warehouse this item actually posted to (varies by
		# voucher type - e.g. Stock Entry Detail has no plain "warehouse"
		# field, s_warehouse/t_warehouse instead).
		account_field_map = VOUCHER_ITEM_ACCOUNT_FIELDS.get(voucher_type, {})
		for fieldname in list(account_field_map.get("direct", ())) + list(account_field_map.get("warehouse", ())):
			if fieldname not in fields:
				fields.append(fieldname)
		items = frappe.get_all(
			item_doctype,
			filters={"parent": ["in", list(voucher_names)]},
			fields=fields,
			order_by="parent, idx",
		)
		for item in items:
			if voucher_type == "Stock Entry":
				item.warehouse = None
			items_by_voucher.setdefault((voucher_type, item.parent), []).append(item)

	return items_by_voucher


TRANSACTION_DETAIL_FIELDS = (
	"posting_date",
	"voucher_type",
	"voucher_no",
	"party",
	"against",
	"debit",
	"credit",
	"item_code",
	"item_name",
	"qty",
	"rate",
	"amount",
)


def blank_missing_transaction_detail_fields(data):
	"""Every transaction-detail column (see get_transaction_detail_columns())
	is only relevant to some rows - Debit/Credit/Party/Against only to
	transaction rows, Qty/Rate/Amount/Item Code/Item Name only to item rows,
	none of them to plain account/group/total rows. Frappe's Currency/Float
	formatters only render a blank cell for a field that's explicitly None;
	a field that's merely absent from the row still formats as "0.00" (the
	frontend checks `value === null`, not `value == null`) - so every row
	needs each not-applicable field set to a real None, not just left unset."""
	for row in data:
		if not row:
			continue
		for field in TRANSACTION_DETAIL_FIELDS:
			if field not in row:
				row[field] = None


def get_transaction_detail_columns(data):
	"""Only include a transaction-detail column if at least one row in this
	report run actually has a value for it - e.g. no point showing "Item
	Code"/"Qty"/"Rate" if none of the transactions drilled into this time
	carry an item table, or "Party" if every voucher here posts without
	one. `data` is the report's fully-built row list."""
	all_columns = [
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 130},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160,
		},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Data", "width": 140},
		{"label": _("Against"), "fieldname": "against", "fieldtype": "Data", "width": 140},
		{"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{
			# Selling/buying rate everywhere except the Cost of Goods Sold
			# branch, where callers pass use_valuation_rate=True to
			# attach_transaction_rows() and this same column shows the
			# valuation/cost rate instead - see VOUCHER_ITEM_DOCTYPE.
			"label": _("Rate"),
			"fieldname": "rate",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 120,
		},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": "currency", "width": 100},
	]

	return [
		column
		for column in all_columns
		if any(row.get(column["fieldname"]) not in (None, "") for row in data if row)
	]


def compute_margin_view_data(data, columns, accumulated_values, base_account_name=None):
	"""Percent-of-base view: every row's value is shown as a percentage of
	`base_account_name`'s value in that same column (e.g. "% of Income" for
	Profit and Loss, "% of Assets" - a common-size balance sheet - for the
	Balance Sheet). Defaults to Income to preserve the original P&L-only
	behaviour of this function."""
	if not columns:
		return

	if not accumulated_values:
		columns.append({"key": "total"})

	base_account_name = base_account_name or _("Income")

	data_copy = copy.deepcopy(data)

	base_row = None
	for row in data_copy:
		if row.get("account_name") == base_account_name:
			base_row = row
			break

	if not base_row:
		return

	for row_idx in range(len(data_copy)):
		# Taking the total income from each column (for all the financial years) as the base (100%)
		row = data_copy[row_idx]
		if not row:
			continue

		for column in columns:
			curr_period = column.get("key")
			base_value = base_row[curr_period]
			curr_value = row[curr_period]

			if curr_value is None or base_value is None or base_value <= 0:
				data[row_idx][curr_period] = None
				continue

			margin_percent = round((curr_value / base_value) * 100, 2)

			data[row_idx][curr_period] = margin_percent
