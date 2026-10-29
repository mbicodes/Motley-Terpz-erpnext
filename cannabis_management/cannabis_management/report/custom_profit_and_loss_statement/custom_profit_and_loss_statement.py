import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.report.financial_statements import (
	compute_growth_view_data,
	compute_margin_view_data,
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

	income = get_data(
		filters.company,
		"Income",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)

	expense = get_data(
		filters.company,
		"Expense",
		"Debit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)

	net_profit_loss = get_net_profit_loss(
		income, expense, period_list, filters.company, filters.presentation_currency
	)

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)

	data = []
	data.extend(income or [])
	data.extend(expense or [])
	if net_profit_loss:
		data.append(net_profit_loss)

	data.append({})
	data.extend(
		get_indirect_recap_section(
			income or [], "Indirect Income", _("Indirect Income"), _("Indirect Income Type"), currency, period_list
		)
	)
	data.append({})
	data.extend(
		get_indirect_recap_section(
			expense or [], "Indirect Expense", _("Indirect Expense"), _("Indirect Expense"), currency, period_list
		)
	)

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)

	chart = get_chart_data(filters, columns, income, expense, net_profit_loss, currency)

	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, income, expense, net_profit_loss, currency, filters
	)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)

	if filters.get("selected_view") == "Margin":
		compute_margin_view_data(data, period_list, filters.accumulated_values)

	data.extend(get_stock_quantity_rows(filters, period_list, currency))

	for row in data:
		if row and row.get("is_group") == 1:
			account_name = row.get("account_name", "") or ""
			if not any(x in account_name for x in ["Total", "Profit / Loss", "Profit for the year"]):
				for col in columns:
					if col.get("fieldtype") == "Currency":
						row[col.get("fieldname")] = ""

	return columns, data, None, chart, report_summary, primitive_summary


def get_report_summary(
	period_list, periodicity, income, expense, net_profit_loss, currency, filters, consolidated=False
):
	net_income, net_expense, net_profit = 0.0, 0.0, 0.0

	if filters.get("accumulated_in_group_company"):
		period_list = get_filtered_list_for_consolidated_report(filters, period_list)

	if filters.accumulated_values:
		key = period_list[-1].key
		if income:
			net_income = income[-2].get(key)
		if expense:
			net_expense = expense[-2].get(key)
		if net_profit_loss:
			net_profit = net_profit_loss.get(key)
	else:
		for period in period_list:
			key = period if consolidated else period.key
			if income:
				net_income += income[-2].get(key)
			if expense:
				net_expense += expense[-2].get(key)
			if net_profit_loss:
				net_profit += net_profit_loss.get(key)

	if len(period_list) == 1 and periodicity == "Yearly":
		profit_label = _("Profit This Year")
		income_label = _("Total Income This Year")
		expense_label = _("Total Expense This Year")
	else:
		profit_label = _("Net Profit")
		income_label = _("Total Income")
		expense_label = _("Total Expense")

	return [
		{"value": net_income, "label": income_label, "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{"value": net_expense, "label": expense_label, "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "=", "color": "blue"},
		{
			"value": net_profit,
			"indicator": "Green" if net_profit > 0 else "Red",
			"label": profit_label,
			"datatype": "Currency",
			"currency": currency,
		},
	], net_profit


def get_net_profit_loss(income, expense, period_list, company, currency=None, consolidated=False):
	total = 0
	net_profit_loss = {
		"account_name": "'" + _("Profit for the year") + "'",
		"account": "'" + _("Profit for the year") + "'",
		"warn_if_negative": True,
		"currency": currency or frappe.get_cached_value("Company", company, "default_currency"),
	}

	has_value = False

	for period in period_list:
		key = period if consolidated else period.key
		total_income = flt(income[-2][key], 3) if income else 0
		total_expense = flt(expense[-2][key], 3) if expense else 0

		net_profit_loss[key] = total_income - total_expense

		if net_profit_loss[key]:
			has_value = True

		total += flt(net_profit_loss[key])
		net_profit_loss["total"] = total

	if has_value:
		return net_profit_loss


def get_indirect_recap_section(rows, account_type, section_label, heading_label, currency, period_list):
	if not rows:
		return []

	children_by_parent = {}
	for row in rows:
		if not row:
			continue
		children_by_parent.setdefault(row.get("parent_account") or "", []).append(row)

	def leaves_under(account_key):
		leaves = []
		for child in children_by_parent.get(account_key, []):
			if child.get("is_group"):
				leaves.extend(leaves_under(child.get("account")))
			else:
				leaves.append(child)
		return leaves

	matched, seen = [], set()

	def add_leaf(leaf):
		key = leaf.get("account")
		if key and key not in seen:
			seen.add(key)
			matched.append(leaf)

	for row in rows:
		if not row or row.get("account_type") != account_type:
			continue
		if row.get("is_group"):
			for leaf in leaves_under(row.get("account")):
				add_leaf(leaf)
		else:
			add_leaf(row)

	if not matched:
		return []

	section_key = "'" + section_label + "'"
	header_row = frappe._dict(
		{
			"account_name": heading_label,
			"account": section_key,
			"parent_account": "",
			"currency": currency,
			"is_group": 1,
			"indent": 0,
		}
	)

	total_label = _("Total {0}").format(section_label)
	total_row = frappe._dict(
		{
			"account_name": total_label,
			"account": "'" + total_label + "'",
			"parent_account": "",
			"currency": currency,
			"indent": 0,
		}
	)

	out = [header_row]
	for leaf in matched:
		leaf_row = frappe._dict(dict(leaf))
		leaf_row["account"] = leaf.get("account") + "::recap"
		leaf_row["gl_account"] = leaf.get("account")
		leaf_row["parent_account"] = section_key
		leaf_row["indent"] = 1
		out.append(leaf_row)

		for period in period_list:
			total_row[period.key] = flt(total_row.get(period.key, 0.0)) + flt(leaf.get(period.key, 0.0))
		total_row["total"] = flt(total_row.get("total", 0.0)) + flt(leaf.get("total", 0.0))

	out.append(total_row)
	return out


def get_stock_quantity_rows(filters, period_list, currency):
	company = filters.company

	def qty_before(date):
		if not date:
			return 0.0

		ledger = frappe.db.sql(
			"""
			select sum(actual_qty) as qty
			from `tabStock Ledger Entry`
			where company = %(company)s
				and is_cancelled = 0
				and posting_date < %(date)s
			""",
			{"company": company, "date": date},
		)
		reco = frappe.db.sql(
			"""
			select sum(sri.quantity_difference) as qty
			from `tabStock Reconciliation Item` sri
			inner join `tabStock Reconciliation` sr on sr.name = sri.parent
			where sr.docstatus = 1
				and sr.company = %(company)s
				and sr.posting_date < %(date)s
			""",
			{"company": company, "date": date},
		)
		opening = flt(ledger[0][0]) if ledger and ledger[0][0] else 0.0
		opening += flt(reco[0][0]) if reco and reco[0][0] else 0.0
		return opening

	VOUCHER_PROJECT_UNION = """
		select 'Stock Entry' as voucher_type, name as voucher_no, project from `tabStock Entry` where company = %(company)s
		union all
		select 'Purchase Receipt', name, project from `tabPurchase Receipt` where company = %(company)s
		union all
		select 'Purchase Invoice', name, project from `tabPurchase Invoice` where company = %(company)s
		union all
		select 'Delivery Note', name, project from `tabDelivery Note` where company = %(company)s
		union all
		select 'Sales Invoice', name, project from `tabSales Invoice` where company = %(company)s
	"""

	def ledger_split_in_range(from_date, to_date, inward):
		params = {"company": company, "from_date": from_date, "to_date": to_date}

		if inward:
			bucket = """
				case
					when sle.voucher_type = 'Purchase Receipt' then 'purchases'
					when ifnull(sle.project, ifnull(vp.project, '')) != '' then 'harvest'
					else 'other'
				end
			"""
			condition, aggregate = "sle.actual_qty > 0", "sum(sle.actual_qty)"
			join = f"left join ({VOUCHER_PROJECT_UNION}) vp on vp.voucher_type = sle.voucher_type and vp.voucher_no = sle.voucher_no"
		else:
			bucket = """
				case
					when sle.voucher_type in ('Delivery Note', 'Sales Invoice') then 'sales'
					else 'other'
				end
			"""
			condition, aggregate = "sle.actual_qty < 0", "sum(abs(sle.actual_qty))"
			join = ""

		rows = frappe.db.sql(
			f"""
			select {bucket} as bucket, {aggregate} as qty
			from `tabStock Ledger Entry` sle
			{join}
			where sle.company = %(company)s
				and sle.is_cancelled = 0
				and sle.posting_date between %(from_date)s and %(to_date)s
				and {condition}
			group by bucket
			""",
			params,
			as_dict=True,
		)
		return {d.bucket: flt(d.qty) for d in rows}

	def reco_split_in_range(from_date, to_date):
		row = frappe.db.sql(
			"""
			select
				sum(case when sri.quantity_difference > 0 then sri.quantity_difference else 0 end) as gain,
				sum(case when sri.quantity_difference < 0 then -sri.quantity_difference else 0 end) as loss
			from `tabStock Reconciliation Item` sri
			inner join `tabStock Reconciliation` sr on sr.name = sri.parent
			where sr.docstatus = 1
				and sr.company = %(company)s
				and sr.posting_date between %(from_date)s and %(to_date)s
			""",
			{"company": company, "from_date": from_date, "to_date": to_date},
			as_dict=True,
		)
		gain = flt(row[0].gain) if row and row[0].gain else 0.0
		loss = flt(row[0].loss) if row and row[0].loss else 0.0
		return gain, loss

	def make_row(label, indent=0, is_total=0):
		return frappe._dict(
			{
				"account_name": _(label),
				"account": "'" + _(label) + "'",
				"currency": currency,
				"is_group": 0,
				"indent": indent,
				"is_qty_row": 1,
				"is_qty_total": is_total,
			}
		)

	opening_row = make_row("Opening Quantity")
	purchase_row = make_row("Purchases", indent=1)
	harvest_row = make_row("Harvest", indent=1)
	gain_row = make_row("Inventory Gain", indent=1)
	other_in_row = make_row("Other Inward", indent=1)
	inward_row = make_row("Total Inward Quantity", is_total=1)
	sales_row = make_row("Sales", indent=1)
	loss_row = make_row("Inventory Loss", indent=1)
	other_out_row = make_row("Other Outward", indent=1)
	outward_row = make_row("Total Outward Quantity", is_total=1)
	closing_row = make_row("Closing Quantity")

	flow_rows = [
		purchase_row,
		harvest_row,
		gain_row,
		other_in_row,
		inward_row,
		sales_row,
		loss_row,
		other_out_row,
		outward_row,
	]
	totals = {id(row): 0.0 for row in flow_rows}

	for period in period_list:
		opening_qty = qty_before(period.from_date)
		inward = ledger_split_in_range(period.from_date, period.to_date, inward=True)
		outward = ledger_split_in_range(period.from_date, period.to_date, inward=False)
		gain_qty, loss_qty = reco_split_in_range(period.from_date, period.to_date)

		period_values = {
			id(purchase_row): inward.get("purchases", 0.0),
			id(harvest_row): inward.get("harvest", 0.0),
			id(gain_row): gain_qty,
			id(other_in_row): inward.get("other", 0.0),
			id(sales_row): outward.get("sales", 0.0),
			id(loss_row): loss_qty,
			id(other_out_row): outward.get("other", 0.0),
		}
		period_values[id(inward_row)] = (
			period_values[id(purchase_row)]
			+ period_values[id(harvest_row)]
			+ period_values[id(gain_row)]
			+ period_values[id(other_in_row)]
		)
		period_values[id(outward_row)] = (
			period_values[id(sales_row)]
			+ period_values[id(loss_row)]
			+ period_values[id(other_out_row)]
		)

		closing_qty = opening_qty + period_values[id(inward_row)] - period_values[id(outward_row)]

		opening_row[period.key] = flt(opening_qty, 3)
		closing_row[period.key] = flt(closing_qty, 3)
		for row in flow_rows:
			qty = period_values[id(row)]
			row[period.key] = flt(qty, 3)
			totals[id(row)] += qty

	opening_row["total"] = opening_row.get(period_list[0].key, 0.0)
	closing_row["total"] = closing_row.get(period_list[-1].key, 0.0)
	for row in flow_rows:
		row["total"] = flt(totals[id(row)], 3)

	return [
		{},
		opening_row,
		purchase_row,
		harvest_row,
		gain_row,
		other_in_row,
		inward_row,
		sales_row,
		loss_row,
		other_out_row,
		outward_row,
		closing_row,
	]


def get_chart_data(filters, columns, income, expense, net_profit_loss, currency):
	labels = [d.get("label") for d in columns[2:]]

	income_data, expense_data, net_profit = [], [], []

	for p in columns[2:]:
		if income:
			income_data.append(income[-2].get(p.get("fieldname")))
		if expense:
			expense_data.append(expense[-2].get(p.get("fieldname")))
		if net_profit_loss:
			net_profit.append(net_profit_loss.get(p.get("fieldname")))

	datasets = []
	if income_data:
		datasets.append({"name": _("Income"), "values": income_data})
	if expense_data:
		datasets.append({"name": _("Expense"), "values": expense_data})
	if net_profit:
		datasets.append({"name": _("Net Profit/Loss"), "values": net_profit})

	chart = {"data": {"labels": labels, "datasets": datasets}}

	if not filters.accumulated_values:
		chart["type"] = "bar"
	else:
		chart["type"] = "line"

	chart["fieldtype"] = "Currency"
	chart["options"] = "currency"
	chart["currency"] = currency

	return chart
