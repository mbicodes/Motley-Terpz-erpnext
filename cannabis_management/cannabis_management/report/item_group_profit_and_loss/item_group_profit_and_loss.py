# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Profit and Loss with one column per Item Group.

The stock Profit and Loss Statement puts periods across the top. This puts
ITEM GROUPS there instead: the same account tree down the left, and for each
account the money attributable to each item group.

How an amount is attributed
---------------------------
A GL Entry carries no item, so the split is taken from the documents that
produced it. Every item row on an invoice, delivery note or stock entry
already names both the P&L account it posts to (income_account /
expense_account) and the item — and therefore the item group. Summing those
rows by (account, item group) gives the split directly, with no apportioning
or guesswork.

Anything with no item behind it — journal entries, opening balances, a
manually posted expense — cannot belong to an item group. Rather than hide it
or spread it around, each account's GL total is taken from the ledger and the
remainder lands in an "Unallocated" column. That is what makes the Total
column reconcile exactly with the stock Profit and Loss Statement: the row
always adds up, and anything unattributable is visible rather than silently
dropped.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Item rows that name the P&L account they post to, per voucher type.
# (child doctype, account field on the row, amount field)
ITEM_SOURCES = [
	("Sales Invoice", "Sales Invoice Item", "income_account", "base_net_amount"),
	("Purchase Invoice", "Purchase Invoice Item", "expense_account", "base_net_amount"),
	("Delivery Note", "Delivery Note Item", "expense_account", "base_net_amount"),
	("Purchase Receipt", "Purchase Receipt Item", "expense_account", "base_net_amount"),
	("Stock Entry", "Stock Entry Detail", "expense_account", "amount"),
]

UNALLOCATED = "__unallocated__"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Select a Company."))

	_resolve_period(filters)

	accounts = _pl_accounts(filters.company)
	if not accounts:
		return [], []

	totals = _gl_totals(filters, accounts)
	by_group = _item_group_amounts(filters, accounts)

	groups = _visible_groups(filters, by_group)
	columns = _columns(groups)
	data = _rows(accounts, totals, by_group, groups)

	if not filters.get("show_zero_values"):
		data = _drop_empty_rows(data, columns)

	return columns, data


def _resolve_period(filters):
	"""Fiscal Year or Date Range, same choice the core report offers."""
	if filters.get("filter_based_on") == "Fiscal Year":
		if not (filters.get("from_fiscal_year") and filters.get("to_fiscal_year")):
			frappe.throw(_("Select a start and end Fiscal Year."))
		filters.from_date = frappe.db.get_value(
			"Fiscal Year", filters.from_fiscal_year, "year_start_date")
		filters.to_date = frappe.db.get_value(
			"Fiscal Year", filters.to_fiscal_year, "year_end_date")
	else:
		filters.from_date = filters.get("period_start_date") or filters.get("from_date")
		filters.to_date = filters.get("period_end_date") or filters.get("to_date")

	if not (filters.from_date and filters.to_date):
		frappe.throw(_("Select a date range."))
	if filters.from_date > filters.to_date:
		frappe.throw(_("End date cannot be before start date."))


def _as_list(value):
	"""MultiSelectList arrives as a list, or as JSON when it comes over HTTP."""
	if not value:
		return []
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except Exception:
			value = [value]
	return [v for v in (value if isinstance(value, list) else [value]) if v]


def _drop_empty_rows(data, columns):
	"""Hide accounts with nothing in them, unless 'Show zero values' is on.

	A parent is kept when any descendant survives, so the tree never loses its
	structure — an account with money under it stays reachable.
	"""
	amount_fields = [c["fieldname"] for c in columns if c["fieldtype"] == "Currency"]

	def has_money(row):
		return any(flt(row.get(f)) for f in amount_fields)

	keep = [False] * len(data)
	for i, row in enumerate(data):
		if not has_money(row):
			continue
		keep[i] = True
		# Walk back up to the root, marking every ancestor.
		indent = row.get("indent", 0)
		for j in range(i - 1, -1, -1):
			if data[j].get("indent", 0) < indent:
				keep[j] = True
				indent = data[j].get("indent", 0)
				if indent == 0:
					break
	return [row for row, k in zip(data, keep) if k]


# ── Accounts ─────────────────────────────────────────────────────────────────

def _pl_accounts(company):
	"""Income and Expense accounts for the company, parents included."""
	rows = frappe.db.sql(
		"""
		select name, account_name, parent_account, is_group, root_type, lft, rgt
		from `tabAccount`
		where company = %(company)s and root_type in ('Income', 'Expense')
		order by lft
		""",
		{"company": company}, as_dict=True,
	)
	return rows


def _sign(root_type):
	# Income is credit-balanced, Expense debit-balanced; both shown positive.
	return -1 if root_type == "Income" else 1


# ── Ledger totals (the Total column, and what Unallocated is measured against) ─

def _gl_totals(filters, accounts):
	conds, values = _gl_conditions(filters)
	rows = frappe.db.sql(
		"""
		select gle.account, sum(gle.debit) - sum(gle.credit) as amount
		from `tabGL Entry` gle
		where {0}
		group by gle.account
		""".format(" and ".join(conds)),
		values, as_dict=True,
	)
	root = {a.name: a.root_type for a in accounts}
	return {
		r.account: flt(r.amount) * _sign(root.get(r.account, "Expense"))
		for r in rows if r.account in root
	}


def _gl_conditions(filters):
	conds = [
		"gle.company = %(company)s",
		"gle.is_cancelled = 0",
		"gle.posting_date between %(from_date)s and %(to_date)s",
	]
	values = {
		"company": filters.company,
		"from_date": filters.from_date,
		"to_date": filters.to_date,
	}
	for field in ("cost_center", "project"):
		selected = _as_list(filters.get(field))
		if selected:
			conds.append(f"gle.{field} in %({field})s")
			values[field] = selected

	# Same finance-book handling as the core statements: with "Include Default
	# FB Entries" on, rows with no book are counted alongside the chosen one.
	if filters.get("finance_book"):
		if filters.get("include_default_book_entries"):
			conds.append("(gle.finance_book in (%(finance_book)s, '') or gle.finance_book is null)")
		else:
			conds.append("gle.finance_book = %(finance_book)s")
		values["finance_book"] = filters.finance_book
	elif not filters.get("include_default_book_entries"):
		conds.append("(gle.finance_book = '' or gle.finance_book is null)")

	for dimension in _accounting_dimensions():
		selected = _as_list(filters.get(dimension))
		if selected:
			conds.append(f"gle.{dimension} in %({dimension})s")
			values[dimension] = selected

	return conds, values


def _accounting_dimensions():
	"""Dimension fieldnames that exist as columns on GL Entry."""
	names = [
		frappe.scrub(d.fieldname or d.document_type)
		for d in frappe.get_all("Accounting Dimension",
		                        fields=["fieldname", "document_type"], filters={"disabled": 0})
	]
	columns = set(frappe.db.get_table_columns("GL Entry"))
	return [n for n in names if n in columns]


# ── The item-group split ─────────────────────────────────────────────────────

def _item_group_amounts(filters, accounts):
	"""{account: {item_group: amount}} from the item rows themselves."""
	root = {a.name: a.root_type for a in accounts}
	out = {}

	for parent_dt, child_dt, account_field, amount_field in ITEM_SOURCES:
		conds = [
			"p.company = %(company)s",
			"p.docstatus = 1",
			f"ifnull(c.{account_field}, '') <> ''",
		]
		values = {
			"company": filters.company,
			"from_date": filters.from_date,
			"to_date": filters.to_date,
		}
		date_field = "posting_date"
		conds.append(f"p.{date_field} between %(from_date)s and %(to_date)s")

		for field in ("cost_center", "project"):
			selected = _as_list(filters.get(field))
			if selected and frappe.get_meta(child_dt).has_field(field):
				conds.append(f"c.{field} in %({field})s")
				values[field] = selected

		rows = frappe.db.sql(
			"""
			select c.{acct} as account, ifnull(i.item_group, '') as item_group,
			       sum(ifnull(c.{amt}, 0)) as amount
			from `tab{child}` c
			inner join `tab{parent}` p on p.name = c.parent
			left join `tabItem` i on i.name = c.item_code
			where {conds}
			group by c.{acct}, i.item_group
			""".format(acct=account_field, amt=amount_field, child=child_dt,
			           parent=parent_dt, conds=" and ".join(conds)),
			values, as_dict=True,
		)

		for r in rows:
			if r.account not in root:
				continue
			group = r.item_group or _("Unknown Item Group")
			bucket = out.setdefault(r.account, {})
			bucket[group] = bucket.get(group, 0.0) + flt(r.amount)

	return out


def _visible_groups(filters, by_group):
	"""Item groups that actually carry money, in a stable order.

	Item Group has no company field, so "the company's item groups" is taken to
	mean the ones with activity in this company and period — 60 empty columns
	would be unreadable.
	"""
	seen = set()
	for groups in by_group.values():
		seen.update(groups.keys())

	if filters.get("item_group"):
		wanted = _descendants(filters.item_group)
		seen = {g for g in seen if g in wanted}

	return sorted(seen)


def _descendants(item_group):
	row = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
	if not row:
		return {item_group}
	return {
		r.name for r in frappe.db.sql(
			"""select name from `tabItem Group` where lft >= %(lft)s and rgt <= %(rgt)s""",
			{"lft": row.lft, "rgt": row.rgt}, as_dict=True)
	}


# ── Presentation ─────────────────────────────────────────────────────────────

def _columns(groups):
	cols = [{
		"label": _("Account"), "fieldname": "account", "fieldtype": "Link",
		"options": "Account", "width": 320,
	}]
	for group in groups:
		cols.append({
			"label": group, "fieldname": frappe.scrub(group),
			"fieldtype": "Currency", "width": 150,
		})
	cols.append({"label": _("Unallocated"), "fieldname": "unallocated",
	             "fieldtype": "Currency", "width": 150})
	cols.append({"label": _("Total"), "fieldname": "total",
	             "fieldtype": "Currency", "width": 160})
	return cols


def _rows(accounts, totals, by_group, groups):
	"""Account tree, each leaf carrying its split; parents roll their children up."""
	by_name = {a.name: a for a in accounts}
	children = {}
	for a in accounts:
		children.setdefault(a.parent_account, []).append(a)

	values = {}          # account -> {fieldname: amount}

	def compute(account):
		own = {frappe.scrub(g): 0.0 for g in groups}
		own["unallocated"] = 0.0
		own["total"] = 0.0

		if not account.is_group:
			split = by_group.get(account.name, {})
			allocated = 0.0
			# Item amounts are already positive on both sides — a sale's
			# base_net_amount and a cost's are both stated as money, not as a
			# debit/credit. The ledger sign is only needed where debit and
			# credit are subtracted (see _gl_totals), not here.
			for group, amount in split.items():
				if group in groups:
					own[frappe.scrub(group)] += amount
				allocated += amount
			own["total"] = flt(totals.get(account.name, 0.0), 2)
			own["unallocated"] = flt(own["total"] - allocated, 2)
		else:
			for child in children.get(account.name, []):
				child_values = compute(child)
				for key, amount in child_values.items():
					own[key] = own.get(key, 0.0) + amount

		own = {k: flt(v, 2) for k, v in own.items()}
		values[account.name] = own
		return own

	roots = [a for a in accounts if not a.parent_account or a.parent_account not in by_name]
	for r in roots:
		compute(r)

	data = []

	def emit(account, indent):
		row = {"account": account.name, "indent": indent}
		row.update(values.get(account.name, {}))
		data.append(row)
		for child in sorted(children.get(account.name, []), key=lambda c: c.lft):
			emit(child, indent + 1)

	for r in sorted(roots, key=lambda a: (a.root_type != "Income", a.lft)):
		emit(r, 0)

	return data
