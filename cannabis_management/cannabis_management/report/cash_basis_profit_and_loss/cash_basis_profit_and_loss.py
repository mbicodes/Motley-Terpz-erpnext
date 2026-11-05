# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Cash Basis Profit and Loss.

The Profit and Loss Statement's filters and period columns, built only from
the GL Entries on Bank and Cash accounts:

  * Income  = what came in:  the debit on a Bank/Cash entry
  * Expense = what went out: the credit on a Bank/Cash entry

Each row is the entry's Against value, shown as stored: an account for a
Journal Entry, the party for a Payment Entry, or several accounts joined by
commas when one bank line was booked against more than one. So a $100 debit
on a bank account against Account B is a $100 Income row "Account B".

Period columns, the Growth / Margin views and every filter (cost center,
project, finance book, accounting dimensions...) come from ERPNext's own
financial_statements helpers, so they behave exactly as on the P&L. Opening
entries and Period Closing Vouchers are left out: they are not cash moving.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.accounts.report.financial_statements import (
	apply_additional_conditions,
	compute_growth_view_data,
	compute_margin_view_data,
	get_columns,
	get_period_list,
)


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
	currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	entries = _bank_cash_entries(filters, period_list)
	labels = _labels(entries)

	income = _section(_("Income"), "debit", entries, labels, period_list, filters, currency)
	expense = _section(_("Expense"), "credit", entries, labels, period_list, filters, currency)
	net = _net_row(income, expense, period_list, currency)

	data = income + expense + ([net] if net else [])
	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company)
	chart = _chart(columns, income, expense, net, currency)
	summary = _summary(period_list, income, expense, net, currency)

	if filters.get("selected_view") == "Growth":
		compute_growth_view_data(data, period_list)
	if filters.get("selected_view") == "Margin":
		compute_margin_view_data(data, period_list, filters.accumulated_values)

	return columns, data, None, chart, summary


def _bank_cash_entries(filters, period_list):
	"""Every live, non-opening GL Entry on a Bank or Cash account in the range."""
	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(acc).on(acc.name == gle.account)
		.select(gle.posting_date, gle.against, gle.debit, gle.credit)
		.where(gle.company == filters.company)
		.where(gle.is_cancelled == 0)
		.where(gle.is_opening != "Yes")
		.where(acc.account_type.isin(["Bank", "Cash"]))
		.where(gle.posting_date <= period_list[-1].to_date)
	)
	# Same cost center / project / finance book / dimension handling as the P&L;
	# ignore_closing_entries drops Period Closing Vouchers.
	query = apply_additional_conditions("GL Entry", query, period_list[0].from_date, True, filters)

	from frappe.desk.reportview import build_match_conditions

	sql, params = query.walk()
	match = build_match_conditions("GL Entry")
	if match:
		sql += " and " + match
	return frappe.db.sql(sql, params, as_dict=True)


def _labels(entries):
	"""Against value -> row details. Accounts and parties link to their ledger;
	an employee ID gets the employee's name after it."""
	values = {(e.against or "").strip() or _("(no against)") for e in entries}
	single = [v for v in values if "," not in v]
	accounts = set(frappe.get_all("Account", filters={"name": ["in", single]}, pluck="name")) if single else set()
	employees = dict(frappe.get_all("Employee", filters={"name": ["in", single]},
	                                fields=["name", "employee_name"], as_list=True)) if single else {}
	out = {}
	for v in values:
		info = {"label": v}
		if v in accounts:
			info["account"] = v
		elif v in employees:
			info["label"] = f"{v}: {employees[v]}"
			info["party_type"], info["party"] = "Employee", v
		elif "," not in v:
			for party_type in ("Customer", "Supplier"):
				if frappe.db.exists(party_type, v):
					info["party_type"], info["party"] = party_type, v
					break
		out[v] = info
	return out


def _section(title, side, entries, labels, period_list, filters, currency):
	"""Header row (section totals, as the P&L's root account), one row per
	Against value, a Total row, then the blank spacer the P&L leaves."""
	rows = {}
	for e in entries:
		amount = flt(e[side])
		if not amount:
			continue
		key = (e.against or "").strip() or _("(no against)")
		row = rows.setdefault(key, {p.key: 0.0 for p in period_list})
		posted = getdate(e.posting_date)
		for p in period_list:
			if getdate(p.from_date) <= posted <= getdate(p.to_date):
				row[p.key] += amount
				break

	def finish(values):
		if filters.accumulated_values:
			running = 0.0
			for p in period_list:
				running += values[p.key]
				values[p.key] = running
			values["total"] = values[period_list[-1].key]
		else:
			values["total"] = sum(values[p.key] for p in period_list)
		for p in period_list:
			values[p.key] = flt(values[p.key], 3)
		return values

	children = []
	for key, values in rows.items():
		info = labels.get(key, {"label": key})
		row = finish(values)
		if not filters.show_zero_values and not any(row[p.key] for p in period_list):
			continue
		row.update({
			"account_name": info["label"],
			"account": info.get("account") or info["label"],
			"parent_account": title,
			"indent": 1,
			"currency": currency,
			"has_value": True,
			"year_start_date": period_list[0].year_start_date,
			"year_end_date": period_list[-1].year_end_date,
			"is_ledger_account": 1 if info.get("account") else 0,
			"party_type": info.get("party_type"),
			"party": info.get("party"),
		})
		children.append(row)
	children.sort(key=lambda r: -abs(r["total"]))

	totals = {p.key: sum(r[p.key] for r in children) for p in period_list}
	totals["total"] = sum(r["total"] for r in children)
	header = dict(totals, account_name=title, account=title, indent=0, currency=currency,
	              has_value=bool(children))
	total_row = dict(totals, account_name="'" + _("Total {0}").format(title) + "'",
	                 account="'" + _("Total {0}").format(title) + "'", currency=currency)
	return [header] + children + [total_row, {}]


def _net_row(income, expense, period_list, currency):
	net = {"account_name": "'" + _("Net Cash Profit / Loss") + "'",
	       "account": "'" + _("Net Cash Profit / Loss") + "'",
	       "warn_if_negative": True, "currency": currency}
	inc, exp = income[-2], expense[-2]
	for p in period_list:
		net[p.key] = flt(inc.get(p.key), 3) - flt(exp.get(p.key), 3)
	net["total"] = flt(inc.get("total"), 3) - flt(exp.get("total"), 3)
	return net if any(net[p.key] for p in period_list) or net["total"] else None


def _chart(columns, income, expense, net, currency):
	periods = [c for c in columns if c.get("fieldtype") == "Currency" and c["fieldname"] != "total"]
	datasets = [
		{"name": _("Income"), "values": [income[-2].get(c["fieldname"]) or 0 for c in periods]},
		{"name": _("Expense"), "values": [expense[-2].get(c["fieldname"]) or 0 for c in periods]},
	]
	if net:
		datasets.append({"name": _("Net Cash Profit / Loss"), "values": [net.get(c["fieldname"]) or 0 for c in periods]})
	return {
		"data": {"labels": [c["label"] for c in periods], "datasets": datasets},
		"type": "bar",
		"fieldtype": "Currency",
		"options": "currency",
		"currency": currency,
	}


def _summary(period_list, income, expense, net, currency):
	key = "total"
	inc = flt(income[-2].get(key))
	exp = flt(expense[-2].get(key))
	net_value = inc - exp
	return [
		{"value": inc, "label": _("Total Cash In (Income)"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{"value": exp, "label": _("Total Cash Out (Expense)"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "=", "color": "blue"},
		{"value": net_value, "indicator": "Green" if net_value > 0 else "Red",
		 "label": _("Net Cash Profit / Loss"), "datatype": "Currency", "currency": currency},
	]
