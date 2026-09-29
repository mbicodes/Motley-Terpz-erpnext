# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
#
# Data layer for the CFO Dashboard page (page/cfo_dashboard) and the
# CFO Income Statement Matrix report. Implements the "Financial Dashboard -
# ERPNext v15 Functional Mapping" spec: every figure resolves to GL Entry,
# fetched ONCE per request as (account, month, project, cost center) sums and
# then re-aggregated in Python for every period, statement and chart.
#
# Classification:
#   * P&L lines reuse management_income_statement's expense classifier, so the
#     split into Direct / Selling / G&A / Finance matches that report. On top
#     of it, Depreciation accounts are tracked separately (for EBITDA) and
#     "income tax" accounts become Tax. Income under an "Indirect Income"
#     group is Other Income; every other Income leaf is Revenue.
#   * Balance sheet categories come from account_type plus the chart's own
#     "Current Assets" / "Current Liabilities" / "Loans" groups.
#   * Cash flow is the indirect method built from balance movements, so it
#     always reconciles to the actual change in Cash + Bank.
#
# Period Closing Voucher entries are excluded everywhere: they only move the
# year's P&L into equity, and total equity is derived as Assets - Liabilities
# (which already carries unclosed profit).

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, today

from cannabis_management.cannabis_management.report.management_income_statement.management_income_statement import (
	STOCK_COGS_SUBGROUP_NAMES,
	classify_expense_leaf,
	get_cogs_branch_ranges,
	get_named_subgroup_ranges,
)

# Status thresholds. "higher" metrics compare actual to a benchmark (Budget
# when one exists, else prior year); ratios use absolute bands.
VARIANCE_WATCH_PCT = -10.0  # below 0% -> Watchlist, below this -> Attention
RATIO_BANDS = {
	# ratio: (good_if, on_track_limit, watch_limit)
	"current_ratio": ("high", 1.5, 1.0),
	"cash_ratio": ("high", 0.5, 0.2),
	"debt_to_equity": ("low", 1.0, 2.0),
	"debt_to_assets": ("low", 0.4, 0.6),
}

DASHBOARD_ROLES = ("System Manager", "Accounts Manager")

PL_LINES = ("revenue", "other_income", "direct", "selling", "ga", "da", "finance", "tax")
BS_ASSET_CATS = ("cash", "receivable", "inventory", "other_ca", "fixed_gross", "acc_dep", "other_nca")
BS_LIAB_CATS = ("payable", "debt", "other_cl", "other_ncl")

BS_LABELS = {
	"cash": _("Cash & Bank"),
	"receivable": _("Accounts Receivable"),
	"inventory": _("Inventory"),
	"other_ca": _("Other Current Assets"),
	"fixed_gross": _("Fixed Assets (Gross)"),
	"acc_dep": _("Accumulated Depreciation"),
	"other_nca": _("Other Non-Current Assets"),
	"payable": _("Accounts Payable"),
	"debt": _("Loans & Borrowings"),
	"other_cl": _("Other Current Liabilities"),
	"other_ncl": _("Non-Current Liabilities"),
	"equity": _("Owner's Equity"),
	"retained": _("Retained / Unclosed Profit"),
}

METRICS = {
	"revenue": _("Revenue"),
	"gross_profit": _("Gross Profit"),
	"ebitda": _("EBITDA"),
	"net_profit": _("Net Profit"),
}


# ---------------------------------------------------------------- entry points


@frappe.whitelist()
def get_filter_defaults(company=None):
	frappe.only_for(DASHBOARD_ROLES)
	fiscal_year = get_default_fiscal_year(company)
	return {"filter_based_on": "Fiscal Year", "fiscal_year": fiscal_year, **get_fiscal_year_dates(fiscal_year)}


@frappe.whitelist()
def get_fiscal_year_dates(fiscal_year):
	"""Default date range for a fiscal year: its start to today (or its end, if already over)."""
	start, end = frappe.db.get_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"])
	to_date = min(getdate(end), max(getdate(start), getdate(today())))
	return {"from_date": str(getdate(start)), "to_date": str(to_date)}


@frappe.whitelist()
def get_dashboard(
	company=None,
	filter_based_on="Fiscal Year",
	fiscal_year=None,
	from_date=None,
	to_date=None,
	project=None,
	cost_center=None,
	dimension="Project",
	metric="revenue",
):
	frappe.only_for(DASHBOARD_ROLES)
	if filter_based_on == "Date Range":
		if not (from_date and to_date):
			frappe.throw(_("From Date and To Date are required for Date Range"))
		fiscal_year = None
	else:
		# Fiscal Year mode: the year alone decides the dates
		filter_based_on, from_date, to_date = "Fiscal Year", None, None
	ctx = build_context(company, fiscal_year, from_date, to_date, project, cost_center)
	currency, frappe.flags.cfo_currency_symbol = resolve_currency(ctx.companies)
	data = Ledger(ctx)
	return {
		"meta": {
			"companies": ctx.companies,
			"filter_based_on": filter_based_on,
			"currency": currency,
			"currency_symbol": frappe.flags.cfo_currency_symbol,
			"fiscal_year": ctx.fiscal_year,
			"period_label": label_range(ctx.ytd),
			"ftm_label": label_range(ctx.ftm),
			"ytd_label": label_range(ctx.ytd),
			"fy_label": label_range(ctx.full_year),
			"py_label": label_range(ctx.py(ctx.ytd)),
			"from_date": str(ctx.from_date),
			"to_date": str(ctx.to_date),
			"project": ctx.project,
			"cost_center": ctx.cost_center,
			"has_budget": data.has_budget,
		},
		"executive": executive_summary(data, ctx),
		"ytd": ytd_review(data, ctx),
		"variance": variance_analysis(data, ctx, dimension, metric),
		"income_statement": income_statement_matrix(data, ctx),
		"balance_sheet": balance_sheet_analysis(data, ctx),
		"roe": roe_analysis(data, ctx),
		"cash_flow": cash_flow_analysis(data, ctx),
		"liquidity": liquidity_analysis(data, ctx),
	}


# --------------------------------------------------------------------- context


def get_default_fiscal_year(company=None):
	try:
		from erpnext.accounts.utils import get_fiscal_year

		return get_fiscal_year(today(), company=company or None, as_dict=True).name
	except Exception:
		return frappe.db.get_value(
			"Fiscal Year", {"year_start_date": ["<=", today()], "year_end_date": [">=", today()]}, "name"
		) or frappe.db.get_value("Fiscal Year", {}, "name", order_by="year_start_date desc")


def build_context(company, fiscal_year, from_date, to_date, project=None, cost_center=None):
	"""Every period the dashboard shows, derived from the selected date range:

	* Period (ytd)  = From Date .. To Date
	* FTM           = To Date's month, clipped to From Date
	* Full Year     = trailing 12 months ending To Date
	* PY            = any of the above shifted back one year
	Fiscal Year only supplies the default range when dates are not given."""
	fiscal_year = fiscal_year or get_default_fiscal_year(company)
	defaults = get_fiscal_year_dates(fiscal_year)
	from_date = getdate(from_date or defaults["from_date"])
	to_date = getdate(to_date or defaults["to_date"])
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date"))

	# get_list honours Company user permissions, so a fenced user never sees
	# another entity's books through "all companies"
	allowed = frappe.get_list("Company", pluck="name", order_by="name")
	if company and company not in allowed:
		frappe.throw(_("Not permitted for Company {0}").format(company), frappe.PermissionError)
	companies = [company] if company else allowed
	if not companies:
		frappe.throw(_("No Company available"), frappe.PermissionError)

	ctx = frappe._dict(
		companies=companies,
		fiscal_year=fiscal_year,
		from_date=from_date,
		to_date=to_date,
		# kept under their old names: every section reads these
		fy_start=from_date,
		period_end=to_date,
		project=project or None,
		cost_center=cost_center or None,
		ftm=(max(from_date, get_first_day(to_date)), to_date),
		ytd=(from_date, to_date),
		full_year=(add_days(add_months(to_date, -12), 1), to_date),
	)
	ctx.py = shift_year
	ctx.cost_centers = descendants("Cost Center", cost_center) if cost_center else None
	# Earliest date anything needs: prior-year versions of every period
	ctx.range_start = min(shift_year(ctx.full_year)[0], shift_year(ctx.ytd)[0], get_first_day(add_months(to_date, -23)))
	return ctx


def shift_year(rng):
	"""Same period one year earlier; a month-end stays a month-end (Feb 29 -> Feb 28)."""
	a, b = rng
	end = add_months(b, -12)
	if b == get_last_day(b):
		end = get_last_day(end)
	return (add_months(a, -12), getdate(end))


def descendants(doctype, name):
	lft, rgt = frappe.db.get_value(doctype, name, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return {name}
	return set(frappe.get_all(doctype, filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"))


def label_range(rng):
	a, b = getdate(rng[0]), getdate(rng[1])
	whole_months = a == get_first_day(a) and b == get_last_day(b)
	if whole_months:
		if (a.year, a.month) == (b.year, b.month):
			return a.strftime("%b %Y")
		return f"{a.strftime('%b %Y')} – {b.strftime('%b %Y')}"
	return f"{a.strftime('%d %b %Y')} – {b.strftime('%d %b %Y')}"


def month_key(d):
	return getdate(d).strftime("%Y-%m")


def month_windows(start, end):
	"""(start, end) per calendar month overlapping [start, end], clipped to it."""
	windows, d = [], get_first_day(start)
	start, end = getdate(start), getdate(end)
	while d <= end:
		windows.append((max(d, start), min(get_last_day(d), end)))
		d = add_months(d, 1)
	return windows


# ---------------------------------------------------------------------- ledger


class Ledger:
	"""GL sums for the whole request, classified once, queried many ways."""

	def __init__(self, ctx):
		self.ctx = ctx
		self.load_accounts()
		self.load_gl()
		self.load_budget()

	# -- accounts --------------------------------------------------------------

	def load_accounts(self):
		ctx = self.ctx
		accounts = frappe.db.sql(
			"""
			select name, account_name, parent_account, root_type, account_type, is_group, lft, rgt, company
			from `tabAccount` where company in %(companies)s
			""",
			{"companies": ctx.companies},
			as_dict=True,
		)
		groups = [a for a in accounts if a.is_group]

		def ancestors(acc):
			return [g for g in groups if g.lft < acc.lft and acc.rgt < g.rgt and g.company == acc.company]

		cogs = {c: get_cogs_branch_ranges(c) for c in ctx.companies}
		stock_cogs = {c: get_named_subgroup_ranges(c, cogs[c], STOCK_COGS_SUBGROUP_NAMES) or cogs[c] for c in ctx.companies}

		self.pl_class, self.bs_class = {}, {}
		self.current_liab = set()
		for acc in accounts:
			if acc.is_group:
				continue
			anc = ancestors(acc)
			anc_names = [(g.account_name or "").lower() for g in anc]
			anc_types = [g.account_type for g in anc]
			name = (acc.account_name or "").lower()

			if acc.root_type == "Income":
				self.pl_class[acc.name] = "other_income" if any("indirect" in n for n in anc_names) else "revenue"
			elif acc.root_type == "Expense":
				if acc.account_type == "Depreciation" or "depreciation" in name or "amortiz" in name or "amortis" in name:
					self.pl_class[acc.name] = "da"
				elif "income tax" in name:
					self.pl_class[acc.name] = "tax"
				else:
					bucket = classify_expense_leaf(acc, acc.company, cogs[acc.company], stock_cogs[acc.company])
					self.pl_class[acc.name] = {
						"cogs_matched": "direct",
						"direct_production": "direct",
						"capitalized": "direct",
						"selling": "selling",
						"payroll": "ga",
						"ga": "ga",
						"interest": "finance",
					}[bucket]
			elif acc.root_type == "Asset":
				self.bs_class[acc.name] = self.classify_asset(acc, name, anc_names, anc_types)
			elif acc.root_type == "Liability":
				is_current = any("current liabilit" in n for n in anc_names)
				if is_current:
					self.current_liab.add(acc.name)
				if any(k in n for n in [name, *anc_names] for k in ("loan", "overdraft", "borrow")):
					self.bs_class[acc.name] = "debt"
				elif acc.account_type == "Payable":
					self.bs_class[acc.name] = "payable"
				else:
					self.bs_class[acc.name] = "other_cl" if is_current else "other_ncl"
			elif acc.root_type == "Equity":
				self.bs_class[acc.name] = "equity"

	@staticmethod
	def classify_asset(acc, name, anc_names, anc_types):
		if acc.account_type in ("Cash", "Bank"):
			return "cash"
		if acc.account_type == "Receivable":
			return "receivable"
		if acc.account_type == "Stock" or "Stock" in anc_types or any("inventory" in n for n in anc_names):
			return "inventory"
		if acc.account_type == "Accumulated Depreciation":
			return "acc_dep"
		if acc.account_type in ("Fixed Asset", "Capital Work in Progress") or any("fixed asset" in n for n in anc_names):
			return "fixed_gross"
		if any("current asset" in n for n in anc_names):
			return "other_ca"
		return "other_nca"

	# -- gl --------------------------------------------------------------------

	def load_gl(self):
		ctx = self.ctx
		params = {"companies": ctx.companies, "start": ctx.range_start, "end": ctx.to_date}
		opening = frappe.db.sql(
			"""
			select account, sum(debit - credit) as net from `tabGL Entry`
			where company in %(companies)s and is_cancelled = 0 and posting_date < %(start)s
				and voucher_type != 'Period Closing Voucher'
			group by account
			""",
			params,
			as_dict=True,
		)
		# Daily sums, so any From/To Date slices exactly
		rows = frappe.db.sql(
			"""
			select account, posting_date,
				ifnull(project, '') as project, ifnull(cost_center, '') as cost_center,
				sum(debit - credit) as net, sum(debit) as debit
			from `tabGL Entry`
			where company in %(companies)s and is_cancelled = 0
				and posting_date between %(start)s and %(end)s
				and voucher_type != 'Period Closing Voucher'
			group by account, posting_date, project, cost_center
			""",
			params,
			as_dict=True,
		)
		self.pl_rows, self.bs_rows = [], []
		for r in rows:
			if r.account in self.pl_class:
				r.line = self.pl_class[r.account]
				self.pl_rows.append(r)
			elif r.account in self.bs_class:
				r.cat = self.bs_class[r.account]
				r.current_liab = r.account in self.current_liab
				self.bs_rows.append(r)
		self.bs_opening, self.current_liab_opening = {}, 0.0
		for r in opening:
			cat = self.bs_class.get(r.account)
			if cat:
				self.bs_opening[cat] = self.bs_opening.get(cat, 0) + flt(r.net)
				if r.account in self.current_liab:
					self.current_liab_opening += flt(r.net)
		# Unclosed P&L before the range is part of equity via Assets - Liabilities

	def load_budget(self):
		ctx = self.ctx
		self.budget_month = {}
		budgets = frappe.db.sql(
			"""
			select b.name, b.fiscal_year, b.monthly_distribution, b.budget_against, b.project, b.cost_center,
				ba.account, ba.budget_amount, fy.year_start_date
			from `tabBudget` b
			inner join `tabBudget Account` ba on ba.parent = b.name
			inner join `tabFiscal Year` fy on fy.name = b.fiscal_year
			where b.docstatus = 1 and b.company in %(companies)s
				and fy.year_end_date >= %(start)s and fy.year_start_date <= %(end)s
			""",
			{"companies": ctx.companies, "start": ctx.range_start, "end": ctx.to_date},
			as_dict=True,
		)
		self.has_budget = bool(budgets)
		for b in budgets:
			if ctx.project and not (b.budget_against == "Project" and b.project == ctx.project):
				continue
			if ctx.cost_centers and not (b.budget_against == "Cost Center" and b.cost_center in ctx.cost_centers):
				continue
			line = self.pl_class.get(b.account)
			if not line:
				continue
			weights = self.distribution(b.monthly_distribution)
			for i in range(12):
				ym = month_key(add_months(b.year_start_date, i))
				month_name = getdate(ym + "-01").strftime("%B")
				amount = flt(b.budget_amount) * (weights.get(month_name, 100.0 / 12) / 100.0)
				key = (line, ym)
				self.budget_month[key] = self.budget_month.get(key, 0) + amount

	@staticmethod
	def distribution(name):
		if not name:
			return {}
		return {
			d.month: flt(d.percentage_allocation)
			for d in frappe.get_all(
				"Monthly Distribution Percentage", filters={"parent": name}, fields=["month", "percentage_allocation"]
			)
		}

	# -- queries -----------------------------------------------------------------

	def pl_lines(self, rng, dim=None, use_project_filter=True):
		"""{line: natural-sign amount}; with `dim`, {dim_value: {line: amount}}.

		Project / Cost Center filters apply to P&L only - balance sheet and
		cash flow stay at company level (use_project_filter=False)."""
		start, end = getdate(rng[0]), getdate(rng[1])
		project = self.ctx.project if use_project_filter else None
		cost_centers = self.ctx.cost_centers if use_project_filter else None
		out = {}
		for r in self.pl_rows:
			if not (start <= r.posting_date <= end):
				continue
			if project and r.project != project:
				continue
			if cost_centers and r.cost_center not in cost_centers:
				continue
			sign = -1 if r.line in ("revenue", "other_income") else 1
			bucket = out.setdefault(r[dim] or _("Not Set"), {}) if dim else out
			bucket[r.line] = bucket.get(r.line, 0) + sign * flt(r.net)
		return out

	def budget_lines(self, rng):
		"""Budget for the range; a part-month gets its share by days."""
		out = {}
		for a, b in month_windows(*rng):
			ym = month_key(a)
			share = ((b - a).days + 1) / get_last_day(a).day
			for (line, key), amount in self.budget_month.items():
				if key == ym:
					out[line] = out.get(line, 0) + amount * share
		return out

	def statement(self, rng, **kw):
		return derive_statement(self.pl_lines(rng, **kw))

	def debt_repaid(self, rng):
		start, end = getdate(rng[0]), getdate(rng[1])
		return sum(flt(r.debit) for r in self.bs_rows if r.cat == "debt" and start <= r.posting_date <= end)

	def balances(self, as_of):
		"""Category balances at close of `as_of` (natural sign)."""
		as_of = getdate(as_of)
		bal = dict(self.bs_opening)
		cl = self.current_liab_opening
		for r in self.bs_rows:
			if r.posting_date <= as_of:
				bal[r.cat] = bal.get(r.cat, 0) + flt(r.net)
				if r.current_liab:
					cl += flt(r.net)
		out = {cat: flt(bal.get(cat)) for cat in BS_ASSET_CATS}
		out.update({cat: -flt(bal.get(cat)) for cat in BS_LIAB_CATS})
		out["equity"] = -flt(bal.get("equity"))
		out["total_assets"] = sum(out[c] for c in BS_ASSET_CATS)
		out["total_liabilities"] = sum(out[c] for c in BS_LIAB_CATS)
		out["total_equity"] = out["total_assets"] - out["total_liabilities"]
		out["retained"] = out["total_equity"] - out["equity"]
		out["current_assets"] = out["cash"] + out["receivable"] + out["inventory"] + out["other_ca"]
		out["current_liabilities"] = -cl
		out["fixed_net"] = out["fixed_gross"] + out["acc_dep"]
		return out

	def cash_flow(self, rng):
		start, end = rng
		o = self.balances(add_days(start, -1))
		c = self.balances(end)
		np = self.statement(rng, use_project_filter=False).net_profit
		d = {k: c[k] - o[k] for k in c}
		operating = [
			(_("Net Profit"), np),
			# Accumulated depreciation carries a credit (negative) balance, so
			# its growth is a negative movement that adds cash back
			(_("Depreciation (non-cash)"), -d["acc_dep"]),
			(_("Change in Receivables"), -d["receivable"]),
			(_("Change in Inventory"), -d["inventory"]),
			(_("Change in Other Current Assets"), -d["other_ca"]),
			(_("Change in Other Non-Current Assets"), -d["other_nca"]),
			(_("Change in Payables"), d["payable"]),
			(_("Change in Other Liabilities"), d["other_cl"] + d["other_ncl"]),
		]
		investing = [(_("Capital Expenditure"), -d["fixed_gross"])]
		financing = [(_("Net Borrowings"), d["debt"]), (_("Owner's Equity"), d["equity"])]
		cfo = sum(v for _l, v in operating)
		cfi = sum(v for _l, v in investing)
		cff = sum(v for _l, v in financing)
		return frappe._dict(
			opening_cash=o["cash"],
			closing_cash=c["cash"],
			operating=operating,
			investing=investing,
			financing=financing,
			cfo=cfo,
			cfi=cfi,
			cff=cff,
			net=cfo + cfi + cff,
			capex=d["fixed_gross"],
			fcf=cfo - d["fixed_gross"],
			unreconciled=(c["cash"] - o["cash"]) - (cfo + cfi + cff),
		)


def derive_statement(lines):
	g = lambda k: flt(lines.get(k))  # noqa: E731
	s = frappe._dict({k: g(k) for k in PL_LINES})
	s.gross_profit = s.revenue - s.direct
	s.total_opex = s.selling + s.ga + s.da
	s.operating_profit = s.gross_profit - s.total_opex
	s.other_net = s.other_income
	s.pbt = s.operating_profit - s.finance + s.other_net
	s.net_profit = s.pbt - s.tax
	s.ebitda = s.operating_profit + s.da
	return s


# --------------------------------------------------------------------- helpers


def pct(a, b):
	return (flt(a) / flt(b) * 100.0) if flt(b) else None


def ratio(a, b):
	return (flt(a) / flt(b)) if flt(b) else None


def variance_status(actual, benchmark):
	"""On Track / Watchlist / Attention for a higher-is-better metric."""
	if benchmark in (None, 0):
		return "on_track" if flt(actual) >= 0 else "attention"
	change = (flt(actual) - flt(benchmark)) / abs(flt(benchmark)) * 100.0
	if change >= 0:
		return "on_track"
	return "watch" if change >= VARIANCE_WATCH_PCT else "attention"


def ratio_status(key, value):
	if value is None:
		return "na"
	direction, good, watch = RATIO_BANDS[key]
	if direction == "high":
		return "on_track" if value >= good else ("watch" if value >= watch else "attention")
	return "on_track" if value <= good else ("watch" if value <= watch else "attention")


def sign_status(value):
	return "on_track" if flt(value) >= 0 else "attention"


def fmt(v):
	"""Short money text for notes, e.g. -$1.25M; symbol set per request."""
	v = flt(v)
	sign, v, symbol = ("-" if v < 0 else ""), abs(v), frappe.flags.cfo_currency_symbol or ""
	for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
		if v >= div:
			return f"{sign}{symbol}{v / div:,.2f}{suffix}"
	return f"{sign}{symbol}{v:,.0f}"


def resolve_currency(companies):
	"""Shared default currency of the selected companies (None if they differ)."""
	currencies = {frappe.get_cached_value("Company", c, "default_currency") for c in companies}
	if len(currencies) != 1:
		return None, ""
	currency = currencies.pop()
	return currency, frappe.db.get_value("Currency", currency, "symbol") or currency


def fmt_pct(v):
	return "—" if v is None else f"{v:,.2f}%"


def kpi(label, value, status=None, kind="currency", compare=None):
	return {"label": label, "value": value, "status": status, "kind": kind, "compare": compare or []}


def bridge(start_label, start, steps, end_label, end):
	"""Waterfall payload: first/last bars are totals, steps float between."""
	bars = [{"label": start_label, "value": flt(start), "total": True}]
	bars += [{"label": label, "value": flt(v)} for label, v in steps]
	bars.append({"label": end_label, "value": flt(end), "total": True})
	return bars


# ------------------------------------------------------------------- page 1


def executive_summary(data, ctx):
	cy = data.statement(ctx.ytd)
	py = data.statement(ctx.py(ctx.ytd))
	bs = data.balances(ctx.period_end)
	bs_open = data.balances(add_days(ctx.fy_start, -1))
	cf = data.cash_flow(ctx.ytd)

	income = [
		kpi(METRICS[m], cy[m], variance_status(cy[m], py[m]), compare=[{"label": "PY", "value": py[m]}])
		for m in METRICS
	]
	r = bs_ratios(bs)
	balance = [
		kpi(_("Current Ratio"), r["current_ratio"], ratio_status("current_ratio", r["current_ratio"]), "ratio"),
		kpi(_("Cash Ratio"), r["cash_ratio"], ratio_status("cash_ratio", r["cash_ratio"]), "ratio"),
		kpi(_("Debt to Equity"), r["debt_to_equity"], ratio_status("debt_to_equity", r["debt_to_equity"]), "ratio"),
		kpi(_("Debt to Assets"), r["debt_to_assets"], ratio_status("debt_to_assets", r["debt_to_assets"]), "ratio"),
	]
	cash = [
		kpi(_("Net Cash Flow"), cf.net, sign_status(cf.net)),
		kpi(_("CF Operating"), cf.cfo, sign_status(cf.cfo)),
		kpi(_("CF Investing"), cf.cfi, "info"),
		kpi(_("CF Financing"), cf.cff, "info"),
	]
	return {
		"income_kpis": income,
		"balance_kpis": balance,
		"cash_kpis": cash,
		"income_bridge": income_bridge(cy),
		"balance_bridge": balance_bridge(bs_open, bs),
		"cash_bridge": cash_bridge(cf),
		"notes": [
			_("Revenue for the period {0} vs PY {1} ({2}).").format(fmt(cy.revenue), fmt(py.revenue), fmt_pct(pct(cy.revenue - py.revenue, py.revenue))),
			_("Net profit for the period {0}; net margin {1}.").format(fmt(cy.net_profit), fmt_pct(pct(cy.net_profit, cy.revenue))),
			_("Cash moved from {0} to {1} over the period.").format(fmt(cf.opening_cash), fmt(cf.closing_cash)),
		],
	}


def income_bridge(s):
	return bridge(
		_("Revenue"),
		s.revenue,
		[
			(_("Direct Costs"), -s.direct),
			(_("Selling & Dist."), -s.selling),
			(_("G&A"), -s.ga),
			(_("Depreciation"), -s.da),
			(_("Finance Cost"), -s.finance),
			(_("Other Income"), s.other_net),
			(_("Tax"), -s.tax),
		],
		_("Net Profit"),
		s.net_profit,
	)


def balance_bridge(o, c):
	steps = [(BS_LABELS[k], c[k] - o[k]) for k in BS_ASSET_CATS]
	steps += [(BS_LABELS[k], -(c[k] - o[k])) for k in BS_LIAB_CATS]
	return bridge(_("Opening Net Assets"), o["total_equity"], [s for s in steps if abs(s[1]) >= 0.5], _("Closing Net Assets"), c["total_equity"])


def cash_bridge(cf):
	return bridge(
		_("Opening Cash"),
		cf.opening_cash,
		[(_("Operating"), cf.cfo), (_("Investing"), cf.cfi), (_("Financing"), cf.cff)],
		_("Closing Cash"),
		cf.closing_cash,
	)


# ------------------------------------------------------------------- page 2


def ytd_review(data, ctx):
	cy = data.statement(ctx.ytd)
	py = data.statement(ctx.py(ctx.ytd))
	budget = derive_statement(data.budget_lines(ctx.ytd)) if data.has_budget else None
	charts, brief = [], []
	for m, label in METRICS.items():
		b = budget[m] if budget else None
		bench = b if b else py[m]
		status = variance_status(cy[m], bench)
		charts.append({"metric": m, "label": label, "py": py[m], "actual": cy[m], "budget": b, "status": status})
		brief.append(
			{
				"metric": label,
				"status": status,
				"text": _("{0} {1}: {2} vs PY ({3}){4}.").format(
					label,
					fmt(cy[m]),
					fmt(cy[m] - py[m]),
					fmt_pct(pct(cy[m] - py[m], abs(py[m]) if py[m] else 0)),
					_(", {0} vs budget").format(fmt(cy[m] - b)) if b else "",
				),
			}
		)
	return {"charts": charts, "brief": brief}


# ------------------------------------------------------------------- page 3


def variance_analysis(data, ctx, dimension, metric):
	metric = metric if metric in METRICS else "revenue"
	dim = "cost_center" if dimension == "Cost Center" else "project"
	cy = data.statement(ctx.ytd)
	py = data.statement(ctx.py(ctx.ytd))
	cy_dim = {k: derive_statement(v)[metric] for k, v in data.pl_lines(ctx.ytd, dim=dim).items()}
	py_dim = {k: derive_statement(v)[metric] for k, v in data.pl_lines(ctx.py(ctx.ytd), dim=dim).items()}

	rows = []
	for key in set(cy_dim) | set(py_dim):
		c, p = flt(cy_dim.get(key)), flt(py_dim.get(key))
		if abs(c) < 0.5 and abs(p) < 0.5:
			continue
		rows.append({"name": key, "cy": c, "py": p, "delta": c - p, "delta_pct": pct(c - p, abs(p)), "status": variance_status(c, p)})
	rows.sort(key=lambda r: -abs(r["delta"]))

	steps = [(r["name"], r["delta"]) for r in rows[:8]]
	rest = sum(r["delta"] for r in rows[8:])
	if abs(rest) >= 0.5:
		steps.append((_("Others"), rest))

	c, p = cy[metric], py[metric]
	return {
		"metric": metric,
		"metric_label": METRICS[metric],
		"dimension": _("Cost Center") if dim == "cost_center" else _("Project"),
		"kpis": [
			kpi(_("{0} PY").format(METRICS[metric]), p),
			kpi(_("{0} CY").format(METRICS[metric]), c),
			kpi(_("vs PY"), c - p, sign_status(c - p)),
			kpi(_("vs PY %"), pct(c - p, abs(p)), sign_status(c - p), "percent"),
		],
		"bridge": bridge(_("PY"), p, steps, _("CY"), c),
		"rows": rows,
	}


# ------------------------------------------------------------------- page 4

MATRIX_ROWS = [
	("revenue", _("Revenue"), False),
	("direct", _("Direct Costs"), False),
	("gross_profit", _("Gross Profit"), True),
	("selling", _("Selling & Distribution Costs"), False),
	("ga_total", _("General & Admin Costs"), False),
	("total_opex", _("Total Operating Costs"), True),
	("operating_profit", _("Operating Profit"), True),
	("finance", _("Finance Cost"), False),
	("other_net", _("Other Income / (Expense)"), False),
	("pbt", _("Profit Before Tax"), True),
	("tax", _("Tax"), False),
	("net_profit", _("Net Profit"), True),
	("ebitda", _("EBITDA"), True),
]
COST_ROWS = {"direct", "selling", "ga_total", "total_opex", "finance", "tax"}


def income_statement_matrix(data, ctx):
	groups = []
	for key, label, rng in (("ftm", _("FTM"), ctx.ftm), ("ytd", _("Period"), ctx.ytd), ("fy", _("Full Year"), ctx.full_year)):
		actual = data.statement(rng)
		prior = data.statement(ctx.py(rng))
		budget = derive_statement(data.budget_lines(rng)) if data.has_budget else None
		for s in filter(None, (actual, prior, budget)):
			s.ga_total = s.ga + s.da
		groups.append({"key": key, "label": label, "period": label_range(rng), "actual": actual, "py": prior, "budget": budget})

	rows = []
	for field, label, bold in MATRIX_ROWS:
		row = {"field": field, "label": label, "bold": bold, "cost": field in COST_ROWS}
		for g in groups:
			a, p = g["actual"][field], g["py"][field]
			b = g["budget"][field] if g["budget"] else None
			# For costs a positive variance is unfavourable; favourable flag drives colour
			fav = (lambda d: d <= 0) if field in COST_ROWS else (lambda d: d >= 0)
			row[g["key"]] = {
				"actual": a,
				"py": p,
				"vs_py": a - p,
				"vs_py_fav": fav(a - p),
				"budget": b,
				"vs_budget": (a - b) if b is not None else None,
				"vs_budget_fav": fav(a - b) if b is not None else None,
			}
		rows.append(row)
	return {"groups": [{k: g[k] for k in ("key", "label", "period")} for g in groups], "rows": rows}


# ------------------------------------------------------------------- page 5


def bs_ratios(bs):
	return {
		"current_ratio": ratio(bs["current_assets"], bs["current_liabilities"]),
		"cash_ratio": ratio(bs["cash"], bs["current_liabilities"]),
		"debt_to_equity": ratio(bs["debt"], bs["total_equity"]),
		"debt_to_assets": ratio(bs["debt"], bs["total_assets"]),
	}


def balance_sheet_analysis(data, ctx):
	o = data.balances(add_days(ctx.fy_start, -1))
	c = data.balances(ctx.period_end)
	ro, rc = bs_ratios(o), bs_ratios(c)

	def line(key, label=None, bold=False):
		return {"label": label or BS_LABELS[key], "actual": c[key], "opening": o[key], "diff": c[key] - o[key], "bold": bold}

	table = (
		[{"section": _("Assets")}]
		+ [line(k) for k in BS_ASSET_CATS]
		+ [line("total_assets", _("Total Assets"), True), {"section": _("Liabilities")}]
		+ [line(k) for k in BS_LIAB_CATS]
		+ [line("total_liabilities", _("Total Liabilities"), True), {"section": _("Equity")}]
		+ [line("equity"), line("retained"), line("total_equity", _("Total Equity"), True)]
	)
	cards = [
		kpi(_("Current Ratio"), rc["current_ratio"], ratio_status("current_ratio", rc["current_ratio"]), "ratio", [{"label": _("Opening"), "value": ro["current_ratio"], "kind": "ratio"}]),
		kpi(_("Cash Ratio"), rc["cash_ratio"], ratio_status("cash_ratio", rc["cash_ratio"]), "ratio", [{"label": _("Opening"), "value": ro["cash_ratio"], "kind": "ratio"}]),
		kpi(_("Debt to Equity"), rc["debt_to_equity"], ratio_status("debt_to_equity", rc["debt_to_equity"]), "ratio", [{"label": _("Opening"), "value": ro["debt_to_equity"], "kind": "ratio"}]),
		kpi(_("Debt to Assets"), rc["debt_to_assets"], ratio_status("debt_to_assets", rc["debt_to_assets"]), "ratio", [{"label": _("Opening"), "value": ro["debt_to_assets"], "kind": "ratio"}]),
	]
	biggest = sorted(
		[(BS_LABELS[k], c[k] - o[k]) for k in BS_ASSET_CATS + BS_LIAB_CATS], key=lambda x: -abs(x[1])
	)[:3]
	notes = [
		_("Total assets {0} vs opening {1}; equity {2} vs {3}.").format(fmt(c["total_assets"]), fmt(o["total_assets"]), fmt(c["total_equity"]), fmt(o["total_equity"])),
		_("Current ratio {0} (opening {1}); cash ratio {2}.").format(fmt_ratio(rc["current_ratio"]), fmt_ratio(ro["current_ratio"]), fmt_ratio(rc["cash_ratio"])),
		_("Largest movements: {0}.").format(", ".join(f"{label} {fmt(v)}" for label, v in biggest)),
	]
	return {"cards": cards, "table": table, "bridge": balance_bridge(o, c), "notes": notes, "opening_label": add_days(ctx.fy_start, -1).strftime("%d %b %Y")}


def fmt_ratio(v):
	return "—" if v is None else f"{v:,.2f}x"


# ------------------------------------------------------------------- page 6


def dupont(s, bs):
	margin = ratio(s.net_profit, s.revenue)
	turnover = ratio(s.revenue, bs["total_assets"])
	leverage = ratio(bs["total_assets"], bs["total_equity"])
	roe = ratio(s.net_profit, bs["total_equity"])
	return {"roe": roe, "margin": margin, "turnover": turnover, "leverage": leverage}


def roe_analysis(data, ctx):
	cur = dupont(data.statement(ctx.ytd, use_project_filter=False), data.balances(ctx.period_end))
	py_rng = ctx.py(ctx.ytd)
	prev = dupont(data.statement(py_rng, use_project_filter=False), data.balances(py_rng[1]))

	def p(v):
		return None if v is None else v * 100.0

	blocks = [
		{"label": _("Return on Equity"), "value": p(cur["roe"]), "py": p(prev["roe"]), "kind": "percent"},
		{"label": _("Net Profit %"), "value": p(cur["margin"]), "py": p(prev["margin"]), "kind": "percent"},
		{"label": _("Asset Turnover"), "value": p(cur["turnover"]), "py": p(prev["turnover"]), "kind": "percent"},
		{"label": _("Financial Leverage"), "value": cur["leverage"], "py": prev["leverage"], "kind": "ratio"},
	]
	for b in blocks:
		b["status"] = "na" if b["value"] is None else variance_status(b["value"], b["py"])

	steps, notes = [], []
	if None not in cur.values() and None not in prev.values():
		m0, t0, l0 = prev["margin"], prev["turnover"], prev["leverage"]
		m1, t1, l1 = cur["margin"], cur["turnover"], cur["leverage"]
		steps = [
			(_("Net Margin"), (m1 - m0) * t0 * l0 * 100),
			(_("Asset Turnover"), m1 * (t1 - t0) * l0 * 100),
			(_("Leverage Impact"), m1 * t1 * (l1 - l0) * 100),
		]
		notes.append(_("ROE moved from {0} to {1} vs the same period last year.").format(fmt_pct(p(prev["roe"])), fmt_pct(p(cur["roe"]))))
		driver = max(steps, key=lambda s: abs(s[1]))
		notes.append(_("Biggest driver: {0} ({1} pts).").format(driver[0], f"{driver[1]:+.2f}"))
	else:
		notes.append(_("ROE bridge needs revenue, assets and equity in both periods."))
	notes.append(_("ROE uses the period's profit (not annualised) over closing equity."))
	bars = bridge(_("Opening ROE (PY)"), p(prev["roe"]) or 0, steps, _("Closing ROE"), p(cur["roe"]) or 0)
	return {"blocks": blocks, "bridge": bars, "notes": notes}


# ------------------------------------------------------------------- page 7


def cash_flow_analysis(data, ctx):
	cf = data.cash_flow(ctx.ytd)
	py = data.cash_flow(ctx.py(ctx.ytd))
	table = []
	for section, rows, total_label, total, py_rows, py_total in (
		(_("Operating Activities"), cf.operating, _("Net Cash from Operating"), cf.cfo, py.operating, py.cfo),
		(_("Investing Activities"), cf.investing, _("Net Cash from Investing"), cf.cfi, py.investing, py.cfi),
		(_("Financing Activities"), cf.financing, _("Net Cash from Financing"), cf.cff, py.financing, py.cff),
	):
		table.append({"section": section})
		for (label, v), (_l, pv) in zip(rows, py_rows):
			table.append({"label": label, "actual": v, "py": pv, "diff": v - pv})
		table.append({"label": total_label, "actual": total, "py": py_total, "diff": total - py_total, "bold": True})
	table += [
		{"label": _("Net Change in Cash"), "actual": cf.net, "py": py.net, "diff": cf.net - py.net, "bold": True},
		{"label": _("Opening Cash"), "actual": cf.opening_cash, "py": py.opening_cash, "diff": cf.opening_cash - py.opening_cash},
		{"label": _("Closing Cash"), "actual": cf.closing_cash, "py": py.closing_cash, "diff": cf.closing_cash - py.closing_cash, "bold": True},
	]
	cards = [
		kpi(_("Free Cash Flow"), cf.fcf, sign_status(cf.fcf), compare=[{"label": "PY", "value": py.fcf}]),
		kpi(_("CF Operating"), cf.cfo, sign_status(cf.cfo), compare=[{"label": "PY", "value": py.cfo}]),
		kpi(_("CF Investing"), cf.cfi, "info", compare=[{"label": "PY", "value": py.cfi}]),
		kpi(_("CF Financing"), cf.cff, "info", compare=[{"label": "PY", "value": py.cff}]),
	]
	steps = [(label, v) for label, v in cf.operating + cf.investing + cf.financing if abs(v) >= 0.5]
	notes = [
		_("Operating cash flow {0} (PY {1}); free cash flow {2}.").format(fmt(cf.cfo), fmt(py.cfo), fmt(cf.fcf)),
		_("Capital expenditure {0}; net borrowings {1}.").format(fmt(cf.capex), fmt(cf.financing[0][1])),
		_("Cash moved from {0} to {1}.").format(fmt(cf.opening_cash), fmt(cf.closing_cash)),
	]
	if abs(cf.unreconciled) >= 1:
		notes.append(_("Unreconciled difference: {0}.").format(fmt(cf.unreconciled)))
	return {
		"cards": cards,
		"table": table,
		"bridge": bridge(_("Opening Cash"), cf.opening_cash, steps, _("Closing Cash"), cf.closing_cash),
		"notes": notes,
	}


# ------------------------------------------------------------------- page 8


def liquidity_analysis(data, ctx):
	# Trailing 12 calendar months ending To Date (last one clipped to it)
	labels, dscr, opex_cov = [], [], []
	for rng in month_windows(get_first_day(add_months(ctx.to_date, -11)), ctx.to_date):
		cf = data.cash_flow(rng)
		s = data.statement(rng, use_project_filter=False)
		bal = data.balances(rng[1])
		debt_service = s.finance + data.debt_repaid(rng)
		labels.append(rng[0].strftime("%b %y"))
		dscr.append(round(cf.cfo / debt_service, 2) if debt_service else None)
		opex_cov.append(round(bal["cash"] / s.total_opex, 2) if s.total_opex else None)

	quarters = []
	for q in range(3, -1, -1):
		end = min(get_last_day(add_months(ctx.to_date, -3 * q)), ctx.to_date)
		start = get_first_day(add_months(end, -2))
		cf = data.cash_flow((start, end))
		bal = data.balances(end)
		quarters.append(
			{
				"label": f"{start.strftime('%b')}–{end.strftime('%b %y')}",
				"fcf": cf.fcf,
				"net_debt": bal["debt"] - bal["cash"],
				"liquidity": bal["cash"],
				"borrowings": bal["debt"],
			}
		)

	last = quarters[-1]
	valid_dscr = [v for v in dscr if v is not None]
	notes = [
		_("Available liquidity (cash & bank) {0} against borrowings {1}.").format(fmt(last["liquidity"]), fmt(last["borrowings"])),
		_("Net debt {0} at {1}.").format(fmt(last["net_debt"]), ctx.to_date.strftime("%d %b %Y")),
		_("Latest DSCR {0}.").format(f"{valid_dscr[-1]:.2f}x" if valid_dscr else _("n/a (no debt service)")),
		_("OPEX coverage = cash ÷ month's operating costs (months of runway)."),
	]
	return {"labels": labels, "dscr": dscr, "opex_coverage": opex_cov, "quarters": quarters, "notes": notes}


# ---------------------------------------------------------------------- export

STATUS_TEXT = {"on_track": "On Track", "watch": "Watchlist", "attention": "Attention", "info": "", "na": "n/a"}


@frappe.whitelist()
def export_dashboard(**filters):
	"""The whole dashboard as an .xlsx: one sheet per section, same numbers."""
	from io import BytesIO

	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Font, PatternFill

	filters.pop("cmd", None)
	d = get_dashboard(**filters)
	meta = d["meta"]
	wb = Workbook()
	wb.remove(wb.active)
	head_fill = PatternFill("solid", fgColor="1F3864")
	head_font = Font(bold=True, color="FFFFFF")
	# Excel number format carrying the currency symbol, negatives in brackets
	symbol = (meta["currency_symbol"] or "").replace('"', "")
	money = f'"{symbol}"#,##0;("{symbol}"#,##0)' if symbol else "#,##0;(#,##0)"

	def sheet(title, heading):
		ws = wb.create_sheet(title[:31])
		ws.append([heading])
		ws["A1"].font = Font(bold=True, size=14)
		scope = ", ".join(meta["companies"])
		ws.append([f"Company: {scope}" + (f" | Currency: {meta['currency']}" if meta["currency"] else " | Currency: mixed")])
		basis = f"Fiscal Year {meta['fiscal_year']}" if meta["filter_based_on"] == "Fiscal Year" else "Date Range"
		extras = [basis, f"Period: {meta['period_label']}", f"PY: {meta['py_label']}"]
		if meta["project"]:
			extras.append(f"Project: {meta['project']}")
		if meta["cost_center"]:
			extras.append(f"Cost Center: {meta['cost_center']}")
		ws.append([" | ".join(extras)])
		ws.append([])
		ws.column_dimensions["A"].width = 38
		return ws

	def header(ws, cols):
		ws.append(cols)
		for cell in ws[ws.max_row]:
			cell.fill, cell.font = head_fill, head_font
			cell.alignment = Alignment(horizontal="center", wrap_text=True)
		for i in range(2, len(cols) + 1):
			ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = 16

	def row(ws, values, bold=False, fmt=money):
		ws.append(values)
		for cell in ws[ws.max_row][1:]:
			if isinstance(cell.value, (int, float)):
				cell.number_format = fmt
		if bold:
			for cell in ws[ws.max_row]:
				cell.font = Font(bold=True)

	def kpis(ws, title, items):
		row(ws, [title], bold=True)
		header(ws, ["KPI", "Value", "Status", "Compare"])
		for k in items:
			fmt = "0.00" if k["kind"] == "ratio" else ("0.00\\%" if k["kind"] == "percent" else money)
			compare = ", ".join(f"{c['label']}: {fmt_any(c['value'], c.get('kind') or k['kind'])}" for c in k["compare"])
			row(ws, [k["label"], k["value"], STATUS_TEXT.get(k["status"] or "", ""), compare], fmt=fmt)
		ws.append([])

	def bridge_table(ws, title, bars, fmt=money):
		row(ws, [title], bold=True)
		header(ws, ["Step", "Amount"])
		for b in bars:
			row(ws, [b["label"], b["value"]], bold=b.get("total"), fmt=fmt)
		ws.append([])

	def notes(ws, items):
		row(ws, ["CFO – Executive Summary"], bold=True)
		for n in items:
			ws.append([n])
		ws.append([])

	# 1 Executive
	ex = d["executive"]
	ws = sheet("1 Executive Summary", "Executive Summary for CFO")
	kpis(ws, "Income Statement", ex["income_kpis"])
	kpis(ws, "Balance Sheet", ex["balance_kpis"])
	kpis(ws, "Cash Flow Statement", ex["cash_kpis"])
	bridge_table(ws, "Income Statement Bridge", ex["income_bridge"])
	bridge_table(ws, "Balance Sheet Bridge", ex["balance_bridge"])
	bridge_table(ws, "Cash Flow Bridge", ex["cash_bridge"])
	notes(ws, ex["notes"])

	# 2 YTD
	ws = sheet("2 YTD Performance", "YTD Performance Review")
	header(ws, ["Metric", "PY", "Actual", "Budget", "Status"])
	for c in d["ytd"]["charts"]:
		row(ws, [c["label"], c["py"], c["actual"], c["budget"], STATUS_TEXT.get(c["status"], "")])
	ws.append([])
	row(ws, ["CFO Brief"], bold=True)
	for b in d["ytd"]["brief"]:
		ws.append([f"[{STATUS_TEXT.get(b['status'], '')}] {b['text']}"])

	# 3 Variance
	v = d["variance"]
	ws = sheet("3 Variance & Drivers", f"Variance and Driver Analysis – {v['metric_label']} by {v['dimension']}")
	kpis(ws, v["metric_label"], v["kpis"])
	header(ws, [v["dimension"], "CY", "PY", "vs PY", "vs PY %", "Status"])
	for r in v["rows"]:
		row(ws, [r["name"], r["cy"], r["py"], r["delta"], r["delta_pct"], STATUS_TEXT.get(r["status"], "")])
	ws.append([])
	bridge_table(ws, "Contribution Bridge (PY → CY)", v["bridge"])

	# 4 Income statement matrix
	m = d["income_statement"]
	ws = sheet("4 Income Statement", "Income Statement Analysis (FTM vs Period vs Full Year)")
	subs = (("actual", "Actual"), ("py", "PY"), ("vs_py", "vs PY"), ("budget", "Budget"), ("vs_budget", "vs Budget"))
	header(ws, ["Particulars"] + [f"{g['label']} ({g['period']}) {label}" for g in m["groups"] for _k, label in subs])
	for r in m["rows"]:
		row(ws, [r["label"]] + [r[g["key"]][k] for g in m["groups"] for k, _l in subs], bold=r["bold"])

	# 5 Balance sheet
	b = d["balance_sheet"]
	ws = sheet("5 Balance Sheet", "Detailed Balance Sheet Analysis")
	kpis(ws, "Ratios", b["cards"])
	header(ws, ["Particulars", "Actual", f"Opening ({b['opening_label']})", "Diff"])
	for r in b["table"]:
		if r.get("section"):
			row(ws, [r["section"]], bold=True)
		else:
			row(ws, [r["label"], r["actual"], r["opening"], r["diff"]], bold=r.get("bold"))
	ws.append([])
	bridge_table(ws, "Balance Sheet Contribution (Opening → Closing Net Assets)", b["bridge"])
	notes(ws, b["notes"])

	# 6 ROE
	r6 = d["roe"]
	ws = sheet("6 Return on Equity", "Return on Equity Analysis (DuPont)")
	header(ws, ["Component", "Current", "PY", "Status"])
	for blk in r6["blocks"]:
		row(ws, [blk["label"], blk["value"], blk["py"], STATUS_TEXT.get(blk["status"], "")], fmt="0.00")
	ws.append([])
	bridge_table(ws, "ROE Movement (percentage points)", r6["bridge"], fmt="0.00")
	notes(ws, r6["notes"])

	# 7 Cash flow
	c7 = d["cash_flow"]
	ws = sheet("7 Cash Flow", "Detailed Cash Flow Statement Analysis")
	kpis(ws, "Cash Flow KPIs", c7["cards"])
	header(ws, ["Particulars", "Actual", "PY", "Diff"])
	for r in c7["table"]:
		if r.get("section"):
			row(ws, [r["section"]], bold=True)
		else:
			row(ws, [r["label"], r["actual"], r["py"], r["diff"]], bold=r.get("bold"))
	ws.append([])
	bridge_table(ws, "Cash Flow Movement", c7["bridge"])
	notes(ws, c7["notes"])

	# 8 Liquidity
	lq = d["liquidity"]
	ws = sheet("8 Liquidity", "Detailed Liquidity Analysis")
	header(ws, ["Month", "DSCR", "OPEX Coverage"])
	for label, a, o in zip(lq["labels"], lq["dscr"], lq["opex_coverage"]):
		row(ws, [label, a, o], fmt="0.00")
	ws.append([])
	header(ws, ["Quarter", "Free Cash Flow", "Net Debt", "Available Liquidity", "Total Borrowings"])
	for q in lq["quarters"]:
		row(ws, [q["label"], q["fcf"], q["net_debt"], q["liquidity"], q["borrowings"]])
	ws.append([])
	notes(ws, lq["notes"])

	out = BytesIO()
	wb.save(out)
	scope = meta["companies"][0] if len(meta["companies"]) == 1 else "All Companies"
	frappe.response["filename"] = f"CFO Dashboard - {scope} - {meta['from_date']} to {meta['to_date']}.xlsx"
	frappe.response["filecontent"] = out.getvalue()
	frappe.response["type"] = "binary"


def fmt_any(v, kind):
	if v is None:
		return "—"
	if kind == "ratio":
		return fmt_ratio(v)
	if kind == "percent":
		return fmt_pct(v)
	return fmt(v)
