# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
#
# TSBC Ranch Income Statement - a management-style income statement laid out
# to match the client's own draft (unaudited) statement: Revenue -> Cost of
# Sales (split into "matched to inventory issued" / "direct farm &
# cultivation production costs" / "harvested product capitalized to
# inventory, net") -> Gross Profit (+ Gross margin %) -> Operating Expenses
# (Payroll & benefits / G&A / Selling & distribution, net) -> Operating
# Income -> Finance Costs -> Net Income (+ Net margin %).
#
# The three-way Cost of Sales split and three-way Operating Expenses split in
# the client's draft are themselves accountant-made classifications with no
# corresponding tag anywhere in the ledger (checked: TSBC Ranch has a single
# Cost Center, and no account_type distinguishes "capitalized to inventory"
# from "direct farm cost" - see ACCOUNT_MAP below for exactly which accounts
# this report treats as each line). Revenue and the "capitalized to
# inventory, net" line (mapped 1:1 to the Stock Adjustment account) tie out
# exactly to any GL-derived total for the same accounts; the Cost of Sales/
# Opex sub-splits are this report's own GL-native grouping of the chart of
# accounts, not a guaranteed match to any one externally-prepared draft.
#
# Every amount is that account (sub)tree's GL movement for the selected date
# range only (debit-credit for Expense, credit-debit for Income) - no
# opening balance carried in, matching a "current-period movement only"
# statement.

import frappe
from frappe import _
from frappe.utils import flt

ACCOUNT_MAP = {
	"TSBC Ranch": {
		"revenue": {"include": ["Income - TSBC"]},
		"cogs_matched": {
			"include": ["Stock Expenses - TSBC", "Inventory COGS - TSBC"],
			"exclude": ["Stock Adjustment - TSBC"],
		},
		"cogs_direct_farm": {
			"include": [
				"Direct Labor - TSBC",
				"Production Overheads - TSBC",
				"Rent - TSBC",
				"Irrigation - TSBC",
				"Quality Testing - TSBC",
			]
		},
		"cogs_capitalized": {"include": ["Stock Adjustment - TSBC"]},
		"opex_payroll": {"include": ["Operating Expenses – Group - TSBC"]},
		"opex_ga": {
			"include": ["Farm Admin - TSBC", "Indirect Expenses - TSBC"],
			"exclude": [
				"Interest Paid (Loan) - TSBC",
				"Commission on Sales - TSBC",
				"Freight and Forwarding Charges - TSBC",
				"Marketing Expenses - TSBC",
				"Sales Expenses - TSBC",
			],
		},
		"opex_selling": {
			"include": [
				"Commission on Sales - TSBC",
				"Freight and Forwarding Charges - TSBC",
				"Marketing Expenses - TSBC",
				"Sales Expenses - TSBC",
			]
		},
		"finance_cost": {"include": ["Interest Paid (Loan) - TSBC"]},
	}
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = filters.company or "TSBC Ranch"
	from_date = filters.from_date
	to_date = filters.to_date

	if not (from_date and to_date):
		frappe.throw(_("From Date and To Date are mandatory"))

	if company not in ACCOUNT_MAP:
		frappe.throw(
			_("This report's account mapping is only defined for {0}").format(frappe.bold("TSBC Ranch"))
		)

	account_map = ACCOUNT_MAP[company]

	def bal(key, root_type):
		spec = account_map[key]
		return subtree_balance(company, from_date, to_date, root_type, spec["include"], spec.get("exclude"))

	revenue = bal("revenue", "Income")
	cogs_matched = bal("cogs_matched", "Expense")
	cogs_direct_farm = bal("cogs_direct_farm", "Expense")
	cogs_capitalized = bal("cogs_capitalized", "Expense")
	total_cogs = cogs_matched + cogs_direct_farm + cogs_capitalized

	gross_profit = revenue - total_cogs
	gross_margin = (gross_profit / revenue * 100) if revenue else 0.0

	opex_payroll = bal("opex_payroll", "Expense")
	opex_ga = bal("opex_ga", "Expense")
	opex_selling = bal("opex_selling", "Expense")
	total_opex = opex_payroll + opex_ga + opex_selling

	operating_income = gross_profit - total_opex

	finance_cost = bal("finance_cost", "Expense")
	net_income = operating_income - finance_cost
	net_margin = (net_income / revenue * 100) if revenue else 0.0

	currency = frappe.get_cached_value("Company", company, "default_currency")

	data = []
	data.append(
		_note_row(_("(Expressed in {0} — current-period movement only)").format(currency))
	)
	data.append({})

	data.append(_section_row(_("Revenue")))
	data.append(_row(_("Sale of fresh-frozen & procured product"), revenue, dollar=True))
	data.append(_total_row(_("Total revenue"), revenue))
	data.append({})

	data.append(_section_row(_("Cost of Sales")))
	data.append(_row(_("Cost of goods sold – matched to inventory issued"), cogs_matched, dollar=True))
	data.append(_row(_("Direct farm & cultivation production costs"), cogs_direct_farm))
	data.append(_row(_("Less: harvested product capitalized to inventory (net)"), cogs_capitalized))
	data.append(_total_row(_("Total cost of sales"), total_cogs))
	data.append({})

	data.append(_total_row(_("Gross Profit"), gross_profit, banner=True))
	data.append(_percent_row(_("Gross margin %"), gross_margin))
	data.append({})

	data.append(_section_row(_("Operating Expenses")))
	data.append(_row(_("Payroll & employee benefits"), opex_payroll, dollar=True))
	data.append(_row(_("General & administrative expenses"), opex_ga))
	data.append(_row(_("Selling & distribution expenses (net)"), opex_selling))
	data.append(_total_row(_("Total operating expenses"), total_opex))
	data.append({})

	data.append(_total_row(_("Operating Income / (Loss)"), operating_income, banner=True))
	data.append({})

	data.append(_section_row(_("Finance Costs")))
	data.append(_row(_("Interest expense"), finance_cost, dollar=True))
	data.append({})

	data.append(_net_row(_("NET INCOME / (LOSS) FOR THE PERIOD"), net_income))
	data.append({})
	data.append(_percent_row(_("Net margin %"), net_margin))

	columns = [
		{"fieldname": "account_name", "label": _("Description"), "fieldtype": "Data", "width": 420},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Data", "width": 160},
	]

	report_summary = [
		{"label": _("Total Revenue"), "value": fmt(revenue, dollar=True), "datatype": "Data"},
		{"label": _("Gross Profit"), "value": fmt(gross_profit, dollar=True), "datatype": "Data"},
		{"label": _("Operating Income"), "value": fmt(operating_income, dollar=True), "datatype": "Data"},
		{
			"label": _("Net Income"),
			"value": fmt(net_income, dollar=True),
			"indicator": "Green" if net_income >= 0 else "Red",
			"datatype": "Data",
		},
	]

	return columns, data, None, None, report_summary


def subtree_balance(company, from_date, to_date, root_type, include, exclude=None):
	"""Net GL movement for the selected date range across the full account
	subtree(s) rooted at every name in `include`, minus the subtree(s) rooted
	at every name in `exclude` (leaf or group - either works, matched via the
	same lft/rgt nested-set bounds ERPNext's own account tree uses). Sign is
	flipped for Income so a normal credit balance comes back positive."""
	include_bounds = _account_bounds(company, include)
	if not include_bounds:
		return 0.0
	exclude_bounds = _account_bounds(company, exclude or [])

	include_cond = " or ".join(["(acc.lft >= %s and acc.rgt <= %s)"] * len(include_bounds))
	params = [company, from_date, to_date]
	for b in include_bounds:
		params += [b.lft, b.rgt]

	where = f"({include_cond})"
	if exclude_bounds:
		exclude_cond = " or ".join(["(acc.lft >= %s and acc.rgt <= %s)"] * len(exclude_bounds))
		where += f" and not ({exclude_cond})"
		for b in exclude_bounds:
			params += [b.lft, b.rgt]

	row = frappe.db.sql(
		f"""
		select sum(gle.debit) as debit, sum(gle.credit) as credit
		from `tabGL Entry` gle
		join `tabAccount` acc on acc.name = gle.account
		where gle.company = %s
			and gle.is_cancelled = 0
			and gle.posting_date between %s and %s
			and {where}
		""",
		params,
		as_dict=True,
	)[0]

	debit = flt(row.debit)
	credit = flt(row.credit)
	return (credit - debit) if root_type == "Income" else (debit - credit)


def _account_bounds(company, account_names):
	if not account_names:
		return []
	return frappe.db.sql(
		"""select lft, rgt from `tabAccount` where company = %s and name in %s""",
		(company, tuple(account_names)),
		as_dict=True,
	)


def fmt(value, dollar=False):
	value = flt(value)
	if value < 0:
		return f"({abs(value):,.0f})"
	text = f"{value:,.0f}"
	return f"${text}" if dollar else text


def fmt_pct(value):
	return f"{flt(value):.1f}%"


def _row(label, value, dollar=False):
	return {"account_name": label, "amount": fmt(value, dollar=dollar), "indent": 1}


def _total_row(label, value, banner=False):
	return {
		"account_name": label,
		"amount": fmt(value, dollar=True),
		"indent": 0,
		"bold": 1,
		"banner": 1 if banner else 0,
	}


def _section_row(label):
	return {"account_name": label, "amount": "", "indent": 0, "bold": 1, "section": 1}


def _percent_row(label, value):
	return {"account_name": label, "amount": fmt_pct(value), "indent": 0, "italic": 1}


def _net_row(label, value):
	return {"account_name": label, "amount": fmt(value, dollar=True), "indent": 0, "bold": 1, "highlight": 1}


def _note_row(text):
	return {"account_name": text, "amount": "", "indent": 0, "italic": 1}
