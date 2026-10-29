import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate

COGS_ACCOUNT_NAMES = ("cost of goods sold", "cost of goods solds")

STOCK_COGS_SUBGROUP_NAMES = ("stock expenses", "inventory cogs")

CAPITALIZED_TO_INVENTORY_ACCOUNTS = {}

INTEREST_KEYWORDS = ("interest",)
SELLING_KEYWORDS = (
	"freight",
	"commission",
	"marketing",
	"distribution",
	"shipping",
	"postage",
	"storage fee",
	"sales expense",
)
PAYROLL_SELF_KEYWORDS = (
	"payroll",
	"salary",
	"salaries",
	"wage",
	"bonus",
	"workers comp",
	"employee benefit",
	"staff welfare",
)
PAYROLL_PARENT_KEYWORDS = ("payroll", "salary", "salaries")

BUCKET_LABELS = {
	"cogs_matched": _("Cost of goods sold – matched to inventory issued"),
	"direct_production": _("Direct production costs"),
	"capitalized": _("Less: product capitalized to inventory (net)"),
	"payroll": _("Payroll & employee benefits"),
	"ga": _("General & administrative expenses"),
	"selling": _("Selling & distribution expenses (net)"),
	"interest": _("Interest expense"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Company is mandatory"))
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("From Date and To Date are mandatory"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	statement = compute_income_statement(filters.company, filters.from_date, filters.to_date)

	columns = get_columns()
	data = build_rows(statement, filters)
	chart = get_chart_data(statement)
	report_summary = get_report_summary(statement)

	return columns, data, None, chart, report_summary


def compute_income_statement(company, from_date, to_date):
	currency = frappe.get_cached_value("Company", company, "default_currency")

	leaves = get_period_leaf_balances(company, from_date, to_date)
	income_leaves = [row for row in leaves if row.root_type == "Income"]
	expense_leaves = [row for row in leaves if row.root_type == "Expense"]

	cogs_ranges = get_cogs_branch_ranges(company)
	stock_cogs_ranges = get_named_subgroup_ranges(company, cogs_ranges, STOCK_COGS_SUBGROUP_NAMES)
	if not stock_cogs_ranges:
		stock_cogs_ranges = cogs_ranges

	buckets = {key: 0.0 for key in BUCKET_LABELS}
	for row in expense_leaves:
		bucket = classify_expense_leaf(row, company, cogs_ranges, stock_cogs_ranges)
		buckets[bucket] += flt(row.net)

	revenue_rows = [
		{"label": row.account_name, "amount": -flt(row.net)} for row in income_leaves if flt(row.net)
	]
	revenue_rows.sort(key=lambda r: -r["amount"])
	revenue = sum(row["amount"] for row in revenue_rows)

	cogs_matched = buckets["cogs_matched"]
	direct_production = buckets["direct_production"]
	capitalized = buckets["capitalized"]
	total_cost_of_sales = cogs_matched + direct_production + capitalized
	gross_profit = revenue - total_cost_of_sales
	gross_margin_pct = (gross_profit / revenue * 100.0) if revenue else 0.0

	payroll = buckets["payroll"]
	ga = buckets["ga"]
	selling = buckets["selling"]
	total_opex = payroll + ga + selling
	operating_income = gross_profit - total_opex

	interest = buckets["interest"]
	net_income = operating_income - interest
	net_margin_pct = (net_income / revenue * 100.0) if revenue else 0.0

	return frappe._dict(
		{
			"currency": currency,
			"revenue_rows": revenue_rows,
			"revenue": revenue,
			"cogs_matched": cogs_matched,
			"direct_production": direct_production,
			"capitalized": capitalized,
			"total_cost_of_sales": total_cost_of_sales,
			"gross_profit": gross_profit,
			"gross_margin_pct": gross_margin_pct,
			"payroll": payroll,
			"ga": ga,
			"selling": selling,
			"total_opex": total_opex,
			"operating_income": operating_income,
			"interest": interest,
			"net_income": net_income,
			"net_margin_pct": net_margin_pct,
			"used_stock_cogs_split": stock_cogs_ranges is not cogs_ranges,
		}
	)


def get_period_leaf_balances(company, from_date, to_date):
	return frappe.db.sql(
		"""
		select
			a.name, a.account_name, a.parent_account, a.root_type,
			a.lft, a.rgt,
			sum(g.debit - g.credit) as net
		from `tabGL Entry` g
		inner join `tabAccount` a on a.name = g.account
		where g.company = %(company)s
			and g.posting_date between %(from_date)s and %(to_date)s
			and g.is_cancelled = 0
			and a.root_type in ('Income', 'Expense')
			and a.is_group = 0
		group by a.name
		having sum(g.debit - g.credit) != 0
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)


def get_cogs_branch_ranges(company):
	anchors = frappe.db.sql(
		"""
		select name, lft, rgt from `tabAccount`
		where company = %(company)s and root_type = 'Expense'
			and lower(account_name) in %(names)s
		""",
		{"company": company, "names": COGS_ACCOUNT_NAMES},
		as_dict=True,
	)

	ranges = []
	for i, anchor in enumerate(anchors):
		contained = any(
			j != i and anchors[j].lft < anchor.lft and anchor.rgt < anchors[j].rgt
			for j in range(len(anchors))
		)
		if not contained:
			ranges.append((anchor.lft, anchor.rgt))
	return ranges


def get_named_subgroup_ranges(company, branch_ranges, names):
	if not branch_ranges:
		return []

	conditions = " or ".join(f"(a.lft >= {int(lft)} and a.rgt <= {int(rgt)})" for lft, rgt in branch_ranges)
	groups = frappe.db.sql(
		f"""
		select lft, rgt from `tabAccount` a
		where a.company = %(company)s and a.is_group = 1
			and lower(a.account_name) in %(names)s
			and ({conditions})
		""",
		{"company": company, "names": names},
		as_dict=True,
	)
	return [(g.lft, g.rgt) for g in groups]


def classify_expense_leaf(row, company, cogs_ranges, cogs_matched_ranges):
	name = (row.account_name or "").lower()
	parent = (row.parent_account or "").lower()

	if row.name in CAPITALIZED_TO_INVENTORY_ACCOUNTS.get(company, ()):
		return "capitalized"
	if any(keyword in name for keyword in INTEREST_KEYWORDS):
		return "interest"

	in_cogs_branch = any(lft <= row.lft <= rgt for lft, rgt in cogs_ranges)
	in_cogs_matched_subgroup = any(lft <= row.lft <= rgt for lft, rgt in cogs_matched_ranges)
	if in_cogs_branch and in_cogs_matched_subgroup:
		return "cogs_matched"
	if any(keyword in name for keyword in SELLING_KEYWORDS):
		return "selling"
	if any(keyword in name for keyword in PAYROLL_SELF_KEYWORDS) or any(
		keyword in parent for keyword in PAYROLL_PARENT_KEYWORDS
	):
		return "payroll"
	if in_cogs_branch:
		return "direct_production"
	return "ga"


def get_columns():
	return [
		{"fieldname": "particulars", "label": _("Particulars"), "fieldtype": "Data", "width": 380},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 50},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "percent", "label": _("%"), "fieldtype": "Percent", "width": 80},
	]


def build_rows(statement, filters):
	currency = statement.currency
	data = []

	def row(particulars, row_type, amount=None, percent=None, note=None, indent=0, is_negative=None):
		return {
			"particulars": particulars,
			"note": note or "",
			"amount": amount,
			"percent": percent,
			"currency": currency,
			"row_type": row_type,
			"indent": indent,
			"is_negative": (flt(amount) < 0) if is_negative is None and amount is not None else bool(is_negative),
		}

	data.append(row(_("Revenue"), "section"))
	for r in statement.revenue_rows:
		data.append(row(r["label"], "item", amount=r["amount"], note="4", indent=1))
	if not statement.revenue_rows:
		data.append(row(_("Sales"), "item", amount=0.0, note="4", indent=1))
	data.append(row(_("Total revenue"), "subtotal", amount=statement.revenue))
	data.append(row("", "blank"))

	data.append(row(_("Cost of Sales"), "section"))
	data.append(
		row(BUCKET_LABELS["cogs_matched"], "item", amount=statement.cogs_matched, note="5", indent=1)
	)
	data.append(
		row(BUCKET_LABELS["direct_production"], "item", amount=statement.direct_production, note="6", indent=1)
	)
	data.append(row(BUCKET_LABELS["capitalized"], "item", amount=statement.capitalized, note="5", indent=1))
	data.append(row(_("Total cost of sales"), "subtotal", amount=statement.total_cost_of_sales))
	data.append(row("", "blank"))

	data.append(
		row(_("Gross Profit"), "gross_profit", amount=statement.gross_profit)
	)
	data.append(row(_("Gross margin %"), "margin", percent=statement.gross_margin_pct))
	data.append(row("", "blank"))

	data.append(row(_("Operating Expenses"), "section"))
	data.append(row(BUCKET_LABELS["payroll"], "item", amount=statement.payroll, note="7", indent=1))
	data.append(row(BUCKET_LABELS["ga"], "item", amount=statement.ga, note="8", indent=1))
	data.append(row(BUCKET_LABELS["selling"], "item", amount=statement.selling, note="8", indent=1))
	data.append(row(_("Total operating expenses"), "subtotal", amount=statement.total_opex))
	data.append(row("", "blank"))

	data.append(row(_("Operating Income / (Loss)"), "operating_income", amount=statement.operating_income))
	data.append(row("", "blank"))

	data.append(row(_("Finance Costs"), "finance_header"))
	data.append(row(BUCKET_LABELS["interest"], "item", amount=statement.interest, note="8", indent=1))
	data.append(row("", "blank"))

	data.append(row(_("Net Income / (Loss) for the period"), "net_income", amount=statement.net_income))
	data.append(row(_("Net margin %"), "margin", percent=statement.net_margin_pct))

	for note_row in get_methodology_notes(statement):
		data.append(row(note_row, "note_text"))

	return data


def get_methodology_notes(statement):
	notes = [
		"",
		_(
			"Methodology: this is a best-effort management-style reclassification of the general "
			"ledger, not an audited statement. Every Income/Expense account with activity in the "
			"period is assigned to exactly one line above, so the lines always foot to the "
			"company's real total income/expense for the period - but which line an account lands "
			"on is decided by name/grouping heuristics (see management_income_statement.py), not a "
			"per-account chart of accounts review."
		),
		_(
			"Note 5 - \"matched to inventory issued\": every account under the company's Cost of "
			"Goods Sold group that sits inside a \"Stock Expenses\"/\"Inventory COGS\"-style "
			"subgroup (or the whole COGS group, if no such subgroup exists)."
		),
		_(
			"Note 5 - capitalized to inventory: no chart of accounts in this instance currently "
			"carries a dedicated account for this; it will read $0 until one is mapped in "
			"CAPITALIZED_TO_INVENTORY_ACCOUNTS."
		),
		_(
			"Note 6 - direct production costs: everything else under Cost of Goods Sold (labor, "
			"farm/production overhead) not already captured by Note 5, Note 7, or Note 8."
		),
		_(
			"Note 7 - payroll & employee benefits: accounts named/grouped as payroll, salary, "
			"wages, bonus, or workers' comp, wherever they sit in the chart of accounts."
		),
		_(
			"Note 8 - selling & distribution, G&A, and interest: freight/commission/marketing "
			"accounts, financing/interest accounts, and everything remaining, respectively."
		),
	]
	if not statement.used_stock_cogs_split:
		notes.append(
			_(
				"No \"Stock Expenses\"/\"Inventory COGS\" subgroup was found for this company - the "
				"entire Cost of Goods Sold group is reported as Note 5, and Note 6 reads $0."
			)
		)
	return notes


def get_period_label(from_date, to_date):
	from_date = getdate(from_date)
	to_date = getdate(to_date)
	months = (to_date.year - from_date.year) * 12 + (to_date.month - from_date.month) + 1
	if months <= 1:
		return _("For the Month Ended {0}").format(formatdate(to_date, "MMMM d, yyyy"))
	if months == 12:
		return _("For the Year Ended {0}").format(formatdate(to_date, "MMMM d, yyyy"))
	return _("For the {0} Months Ended {1}").format(months, formatdate(to_date, "MMMM d, yyyy"))


def get_report_summary(statement):
	currency = statement.currency
	return [
		{"value": statement.revenue, "label": _("Total Revenue"), "datatype": "Currency", "currency": currency},
		{"type": "separator", "value": "-"},
		{
			"value": statement.total_cost_of_sales,
			"label": _("Total Cost of Sales"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"type": "separator", "value": "=", "color": "blue"},
		{
			"value": statement.gross_profit,
			"label": _("Gross Profit"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"type": "separator", "value": "-"},
		{
			"value": statement.total_opex + statement.interest,
			"label": _("Total Expenses (Opex + Finance)"),
			"datatype": "Currency",
			"currency": currency,
		},
		{"type": "separator", "value": "=", "color": "blue"},
		{
			"value": statement.net_income,
			"indicator": "Green" if statement.net_income > 0 else "Red",
			"label": _("Net Income / (Loss)"),
			"datatype": "Currency",
			"currency": currency,
		},
	]


def get_chart_data(statement):
	currency = statement.currency
	return {
		"data": {
			"labels": [_("Revenue"), _("Cost of Sales"), _("Gross Profit"), _("Opex"), _("Net Income")],
			"datasets": [
				{
					"name": _("Amount"),
					"values": [
						statement.revenue,
						statement.total_cost_of_sales,
						statement.gross_profit,
						statement.total_opex,
						statement.net_income,
					],
				}
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
		"options": "currency",
		"currency": currency,
	}
