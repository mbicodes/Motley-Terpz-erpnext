# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
#
# Every leaf account row (Asset/Liability/Equity) is expanded, in place, into
# its own transactions (vouchers) - no navigating away to General Ledger -
# and every voucher that carries its own item table (Sales/Purchase Invoice,
# Delivery Note, Purchase Receipt, Stock Entry, Stock Reconciliation) is
# expanded one level further into its line items, exactly like Profit and
# Loss Statement (Child Accounts) does. See attach_transaction_rows() in
# financial_statements.py, shared between the two reports. Group/parent
# account rows also have their rolled-up amount blanked for display - see
# blank_group_amounts() - so only leaf accounts show a figure.


import frappe
from frappe import _
from frappe.utils import cint, flt

from cannabis_management.cannabis_management.report.financial_statements import (
	attach_transaction_rows,
	blank_group_amounts,
	blank_missing_transaction_detail_fields,
	compute_margin_view_data,
	get_transaction_detail_columns,
)
from erpnext.accounts.report.financial_statements import (
	compute_growth_view_data,
	get_columns,
	get_data,
	get_filtered_list_for_consolidated_report,
	get_period_list,
)


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

	filters.period_start_date = period_list[0]["year_start_date"]

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)

	asset = get_data(
		filters.company,
		"Asset",
		"Debit",
		period_list,
		only_current_fiscal_year=False,
		filters=filters,
		accumulated_values=filters.accumulated_values,
	)

	liability = get_data(
		filters.company,
		"Liability",
		"Credit",
		period_list,
		only_current_fiscal_year=False,
		filters=filters,
		accumulated_values=filters.accumulated_values,
	)

	equity = get_data(
		filters.company,
		"Equity",
		"Credit",
		period_list,
		only_current_fiscal_year=False,
		filters=filters,
		accumulated_values=filters.accumulated_values,
	)

	simplify_root_heading(asset, period_list, _("Assets"))
	simplify_root_heading(liability, period_list, _("Liabilities"))
	simplify_root_heading(equity, period_list, _("Equity"))

	# get_provisional_profit_loss()/check_opening_balance()/get_report_summary()/
	# get_chart_data() below all index asset[-2]/asset[-1] (and the same for
	# liability/equity) directly, so expand_and_blank_group_rows() must leave
	# those two trailing rows exactly where they are - only the body between
	# the root row and that trailing pair gets expanded.
	asset = expand_and_blank_group_rows(asset, filters, period_list, currency)
	liability = expand_and_blank_group_rows(liability, filters, period_list, currency)
	equity = expand_and_blank_group_rows(equity, filters, period_list, currency)

	provisional_profit_loss, total_credit = get_provisional_profit_loss(
		asset, liability, equity, period_list, filters.company, currency
	)

	message, opening_balance = check_opening_balance(asset, liability, equity)

	data = []
	data.extend(asset or [])
	data.extend(liability or [])
	data.extend(equity or [])
	if opening_balance and round(opening_balance, 2) != 0:
		unclosed = {
			"account_name": "'" + _("Unclosed Fiscal Years Profit / Loss (Credit)") + "'",
			"account": "'" + _("Unclosed Fiscal Years Profit / Loss (Credit)") + "'",
			"warn_if_negative": True,
			"currency": currency,
		}
		for period in period_list:
			unclosed[period.key] = opening_balance
			if provisional_profit_loss:
				provisional_profit_loss[period.key] = provisional_profit_loss[period.key] - opening_balance

		unclosed["total"] = opening_balance
		data.append(unclosed)

	if provisional_profit_loss:
		data.append(provisional_profit_loss)
	if total_credit:
		data.append(total_credit)

	blank_missing_transaction_detail_fields(data)

	columns = get_columns(
		filters.periodicity, period_list, filters.accumulated_values, company=filters.company
	)
	columns.extend(get_transaction_detail_columns(data))

	chart = get_chart_data(filters, columns, asset, liability, equity, currency)

	report_summary, primitive_summary = get_report_summary(
		period_list, asset, liability, equity, provisional_profit_loss, currency, filters
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	if filters.get("selected_view") == "Margin":
		# Common-size balance sheet: every row shown as a % of Total Assets
		# (which by construction equals Total Liabilities + Equity), not %
		# of Income - there's no Income row on a Balance Sheet. The "Assets"
		# root heading row itself has its amount blanked by
		# simplify_root_heading() above (by design - see that function's
		# docstring), so the base has to be the real Total Asset row
		# add_total_row() appends instead - same quoted account_name format
		# used everywhere else in this file for synthetic total rows.
		total_asset_label = "'" + _("Total {0} ({1})").format(_("Asset"), _("Debit")) + "'"
		compute_margin_view_data(
			data, period_list, filters.accumulated_values, base_account_name=total_asset_label
		)

	return columns, data, message, chart, report_summary, primitive_summary


def expand_and_blank_group_rows(rows, filters, period_list, currency):
	"""Same in-place transaction/item drill-down and group-amount blanking
	the Profit and Loss Statement (Child Accounts) report uses - see
	attach_transaction_rows()/blank_group_amounts() in financial_statements.py.

	`rows` is get_data()'s output: [root account row, ...group/leaf rows...,
	total row, {}]. Root and the trailing [total row, {}] pair are left
	untouched - callers below (get_provisional_profit_loss(),
	check_opening_balance(), etc.) index into them directly - only the body
	in between is expanded."""
	if not rows or len(rows) < 2:
		return rows

	root, body, tail = rows[:1], rows[1:-2], rows[-2:]
	body = attach_transaction_rows(body, filters, period_list, currency)
	blank_group_amounts(body, period_list)
	return root + body + tail


def simplify_root_heading(rows, period_list, label):
	"""Turn the top-level root account row into a plain section heading:
	only the label shows, no rolled-up total (that belongs solely on the
	Total Asset/Liability/Equity row at the bottom of each section)."""
	if not rows:
		return
	root = rows[0]
	if root.get("indent") != 0:
		return
	root["account_name"] = label
	root["opening_balance"] = None
	root["total"] = None
	for period in period_list:
		root[period.key] = None


def get_provisional_profit_loss(
	asset, liability, equity, period_list, company, currency=None, consolidated=False
):
	provisional_profit_loss = {}
	total_row = {}
	if asset:
		total = total_row_total = 0
		currency = currency or frappe.get_cached_value("Company", company, "default_currency")
		total_row = {
			"account_name": "'" + _("Total (Credit)") + "'",
			"account": "'" + _("Total (Credit)") + "'",
			"warn_if_negative": True,
			"currency": currency,
		}
		has_value = False

		for period in period_list:
			key = period if consolidated else period.key
			total_assets = flt(asset[-2].get(key))
			effective_liability = 0.00

			if liability and liability[-1] == {}:
				effective_liability += flt(liability[-2].get(key))
			if equity and equity[-1] == {}:
				effective_liability += flt(equity[-2].get(key))

			provisional_profit_loss[key] = total_assets - effective_liability
			total_row[key] = provisional_profit_loss[key] + effective_liability

			if provisional_profit_loss[key]:
				has_value = True

			total += flt(provisional_profit_loss[key])
			provisional_profit_loss["total"] = total

			total_row_total += flt(total_row[key])
			total_row["total"] = total_row_total

		if has_value:
			provisional_profit_loss.update(
				{
					"account_name": "'" + _("Provisional Profit / Loss (Credit)") + "'",
					"account": "'" + _("Provisional Profit / Loss (Credit)") + "'",
					"warn_if_negative": True,
					"currency": currency,
				}
			)

	return provisional_profit_loss, total_row


def check_opening_balance(asset, liability, equity):
	# Check if previous year balance sheet closed
	opening_balance = 0
	float_precision = cint(frappe.db.get_default("float_precision")) or 2
	if asset:
		opening_balance = flt(asset[-1].get("opening_balance", 0), float_precision)
	if liability:
		opening_balance -= flt(liability[-1].get("opening_balance", 0), float_precision)
	if equity:
		opening_balance -= flt(equity[-1].get("opening_balance", 0), float_precision)

	opening_balance = flt(opening_balance, float_precision)
	if opening_balance:
		return _("Previous Financial Year is not closed"), opening_balance
	return None, None


def get_report_summary(
	period_list,
	asset,
	liability,
	equity,
	provisional_profit_loss,
	currency,
	filters,
	consolidated=False,
):
	net_asset, net_liability, net_equity, net_provisional_profit_loss = 0.0, 0.0, 0.0, 0.0

	if filters.get("accumulated_values"):
		period_list = [period_list[-1]]

	# from consolidated financial statement
	if filters.get("accumulated_in_group_company"):
		period_list = get_filtered_list_for_consolidated_report(filters, period_list)

	for period in period_list:
		key = period if consolidated else period.key
		if asset:
			net_asset += asset[-2].get(key)
		if liability and liability[-1] == {}:
			net_liability += liability[-2].get(key)
		if equity and equity[-1] == {}:
			net_equity += equity[-2].get(key)
		if provisional_profit_loss:
			net_provisional_profit_loss += provisional_profit_loss.get(key)

	return [
		{"value": net_asset, "label": _("Total Asset"), "datatype": "Currency", "currency": currency},
		{
			"value": net_liability,
			"label": _("Total Liability"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"value": net_equity, "label": _("Total Equity"), "datatype": "Currency", "currency": currency},
		{
			"value": net_provisional_profit_loss,
			"label": _("Provisional Profit / Loss (Credit)"),
			"indicator": "Green" if net_provisional_profit_loss > 0 else "Red",
			"datatype": "Currency",
			"currency": currency,
		},
	], (net_asset - net_liability + net_equity)


def get_chart_data(filters, columns, asset, liability, equity, currency):
	labels = [d.get("label") for d in columns[2:]]

	asset_data, liability_data, equity_data = [], [], []

	for p in columns[2:]:
		if asset:
			asset_data.append(asset[-2].get(p.get("fieldname")))
		if liability:
			liability_data.append(liability[-2].get(p.get("fieldname")))
		if equity:
			equity_data.append(equity[-2].get(p.get("fieldname")))

	datasets = []
	if asset_data:
		datasets.append({"name": _("Assets"), "values": asset_data})
	if liability_data:
		datasets.append({"name": _("Liabilities"), "values": liability_data})
	if equity_data:
		datasets.append({"name": _("Equity"), "values": equity_data})

	chart = {"data": {"labels": labels, "datasets": datasets}}

	if not filters.accumulated_values:
		chart["type"] = "bar"
	else:
		chart["type"] = "line"

	chart["fieldtype"] = "Currency"
	chart["options"] = "currency"
	chart["currency"] = currency

	return chart
