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
		total_income_row["is_total_row"] = 1
		total_income_row["indent"] = 0

	income_rows = income_tree[1:-2] if income_tree and len(income_tree) >= 2 else []
	expense_rows = expense_tree[1:-2] if expense_tree and len(expense_tree) >= 2 else []

	cogs_rows, cogs_anchor_rows, opex_rows = split_cogs_branch(
		expense_rows, filters.company, period_list
	)

	total_cogs_row = make_total_row(cogs_anchor_rows, period_list, _("Total Cost of Goods Sold"), currency)
	gross_profit_row = make_diff_row(
		total_income_row, total_cogs_row, period_list, _("Gross Profit"), currency
	)
	total_expense_row = make_diff_row(
		total_expense_all_row, total_cogs_row, period_list, _("Total Expense"), currency
	)
	net_profit_row = make_diff_row(
		gross_profit_row, total_expense_row, period_list, _("Net Profit"), currency
	)

	for row in cogs_rows:
		row["use_valuation_rate"] = 1

	if filters.get("skip_transaction_drilldown"):
		pass
	else:
		income_rows = attach_transaction_rows(income_rows, filters, period_list, currency)
		cogs_rows = attach_transaction_rows(cogs_rows, filters, period_list, currency, use_valuation_rate=True)
		opex_rows = attach_transaction_rows(opex_rows, filters, period_list, currency)

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
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("Not permitted to view General Ledger entries"), frappe.PermissionError)

	filters = _resolve_drilldown_filters(filters)
	period_list, currency = _get_drilldown_period_list_and_currency(filters)

	placeholder = {"account": account, "indent": cint(indent)}
	rows = attach_transaction_rows(
		[placeholder], filters, period_list, currency, use_valuation_rate=cint(use_valuation_rate)
	)
	rows = rows[1:]
	blank_missing_transaction_detail_fields(rows)
	return rows


@frappe.whitelist()
def get_accounts_drilldown(accounts, filters):
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
