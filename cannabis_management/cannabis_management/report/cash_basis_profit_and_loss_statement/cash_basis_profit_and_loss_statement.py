# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Cash Basis Profit and Loss Statement.

The cash-basis P&L of TSBC Ranch, Motley Terpz, Master Touch Manufacturing or
all three consolidated, laid out like ERPNext's Profit and Loss Statement:
Cash Income, Cash Cost of Goods Sold, Gross Profit, Operating Expenses and Net
Cash-Basis Profit, each head under its group in the Chart of Accounts.

Every figure comes from cannabis_management.cash_basis.engine, the same
allocations behind "Reconciled Cash Basis Profit and Loss" and "Cash Basis
Transaction Review"; the rules are listed in RULES and shown on the report.
Movements the engine leaves Unclassified are not part of the P&L; "Show
reconciliation to Bank / Cash" adds the block that accounts for them and ties
the result to the ledgers.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from cannabis_management.cash_basis.engine import COMPANIES, PL, classify
from cannabis_management.cannabis_management.report.reconciled_cash_basis_profit_and_loss.reconciled_cash_basis_profit_and_loss import (
	CONSOLIDATED,
	allowed_companies,
	build_rows,
	get_buckets,
)

SECTIONS = (
	("Income", _("Cash Income"), _("Total Cash Income")),
	("COGS", _("Cash Cost of Goods Sold"), _("Total Cash COGS")),
	("Opex", _("Operating Expenses"), _("Total Operating Expenses")),
)
COMPANY_ORDER = {c: i for i, c in enumerate(COMPANIES)}
NOT_RECORDED = _("Head not recorded")

RULES = _(
	"<b>Cash basis:</b> every Bank and Cash movement in the period, Nikki's, Jamie's and Matt's petty cash included. "
	"Customer receipts are income under the heads of the invoices they paid; receipts on opening invoices or not "
	"tied to an invoice have their own lines. Supplier payments count for the expense heads on the bills they paid; "
	"inventory, work in progress, assets and deposits are Balance Sheet. Money moved between the companies or "
	"between own accounts is left out, and a cost one company paid for another shows in the company it belongs to. "
	"Wages show under each employee's head. Expense-tracker spending counts when the tracker pays it; funding or "
	"reimbursing it does not. Movements still under review are left out (see Cash Basis Transaction Review)."
)


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not (f.from_date and f.to_date):
		frappe.throw(_("Set From Date and To Date."))
	if getdate(f.from_date) > getdate(f.to_date):
		frappe.throw(_("From Date must be before To Date."))
	frappe.has_permission("GL Entry", throw=True)
	allowed = allowed_companies()
	if f.company in (None, "", CONSOLIDATED):
		if set(allowed) != set(COMPANIES):
			frappe.throw(_("The consolidated view needs access to all three companies."), frappe.PermissionError)
		scope = list(COMPANIES)
	elif f.company in allowed:
		scope = [f.company]
	else:
		frappe.throw(_("Not permitted for {0}").format(f.company), frappe.PermissionError)

	out, cash = classify(f.from_date, f.to_date)
	buckets = get_buckets(f, scope)
	keys = [b["key"] for b in buckets]
	data, totals = build_statement(out, buckets, scope)
	if f.show_reconciliation:
		data += reconciliation_block(out, cash, buckets, scope)

	columns = [{"fieldname": "account", "label": _("Account"), "fieldtype": "Data", "width": 380}] + [
		{"fieldname": b["key"], "label": b["label"], "fieldtype": "Currency", "width": 150} for b in buckets
	]
	return columns, data, RULES, get_chart(totals, buckets), get_summary(totals, keys[-1])


def build_statement(out, buckets, scope):
	"""Tree rows: section > Chart of Accounts group > head, then the totals."""
	keys = [b["key"] for b in buckets]
	values = {s: {} for s, _l, _t in SECTIONS}       # section -> head -> {bucket: value}
	company_of = {}
	for o in out:
		if o.cls != PL or o.company not in scope:
			continue
		company_of[o.head] = o.company
		for b in buckets:
			if o.company in b["companies"] and b["from"] <= getdate(o.posting_date) <= b["to"]:
				v = values[o.section].setdefault(o.head, {})
				v[b["key"]] = v.get(b["key"], 0.0) + o.pl_amount

	all_heads = [h for s in values.values() for h in s]
	accounts = {a.name: a for a in frappe.get_all(
		"Account", filters={"name": ["in", all_heads or [""]]}, fields=["name", "parent_account"])}
	abbr = dict(frappe.get_all("Company", filters={"name": ["in", list(COMPANIES)]}, fields=["name", "abbr"],
	                           as_list=True))

	def group_of(head):
		a = accounts.get(head)
		if a and a.parent_account:
			return a.parent_account
		return f"{NOT_RECORDED} - {abbr.get(company_of.get(head), '')}"

	def row(row_id, label, vals=None, indent=0, parent=None, bold=0, kind=None, head=None):
		r = {"account": row_id, "account_name": label, "parent_account": parent, "indent": indent,
		     "bold": bold, "kind": kind, "head": head}
		for k in keys:
			r[k] = flt((vals or {}).get(k, 0.0), 2)
		return r

	def add(*parts):
		res = {}
		for sign, vals in parts:
			for k in keys:
				res[k] = res.get(k, 0.0) + sign * vals.get(k, 0.0)
		return res

	data, totals = [], {}
	for section, title, total_label in SECTIONS:
		heads = {h: v for h, v in values[section].items() if any(abs(v.get(k, 0.0)) >= 0.005 for k in keys)}
		groups = {}
		for h in heads:
			groups.setdefault(group_of(h), []).append(h)
		section_total = add(*[(1, v) for v in heads.values()])
		totals[section] = section_total
		data.append(row(section, title, section_total, bold=1, kind="section"))
		for g in sorted(groups, key=lambda g: (COMPANY_ORDER.get(company_of.get(groups[g][0]), 9), g.lower())):
			gid = f"{section}::{g}"
			data.append(row(gid, g, add(*[(1, heads[h]) for h in groups[g]]), indent=1, parent=section,
			                bold=1, kind="group"))
			for h in sorted(groups[g], key=str.lower):
				data.append(row(f"{section}::{h}", h, heads[h], indent=2, parent=gid, kind="head", head=h))
		data.append(row(f"total::{section}", total_label, section_total, bold=1, kind="total"))
		if section == "COGS":
			totals["Gross"] = add((1, totals["Income"]), (-1, section_total))
			data.append(row("gross_profit", _("Gross Profit"), totals["Gross"], bold=1, kind="profit"))
		data.append({})
	totals["Net"] = add((1, totals["Income"]), (-1, totals["COGS"]), (-1, totals["Opex"]))
	data.append(row("net_profit", _("Net Cash-Basis Profit / (Loss)"), totals["Net"], bold=1, kind="net"))
	return data, totals


def reconciliation_block(out, cash, buckets, scope):
	"""The reconciled report's tie-out to the ledgers, as tree rows."""
	rows = build_rows(out, cash, buckets, scope)
	start = next(i for i, r in enumerate(rows) if r.get("account") == _("Reconciliation to the Bank / Cash ledgers"))
	data = [{}]
	for i, r in enumerate(rows[start:]):
		r = dict(r, account_name=r["account"], kind="unclassified" if r.get("kind") == "unclassified" else r.get("kind"))
		if i == 0:
			r.update(account="reconciliation", parent_account=None, indent=0, bold=1, kind="section")
		elif r.get("indent"):
			r.update(account=f"reconciliation::{i}", parent_account="reconciliation", indent=1)
		else:
			r.update(account=f"reconciliation::{i}", parent_account=None, indent=0)
		data.append(r)
	return data


def get_chart(totals, buckets):
	cols = buckets[:-1] if len(buckets) > 1 else buckets
	expenses = {k: totals["COGS"].get(k, 0.0) + totals["Opex"].get(k, 0.0) for k in totals["Net"]}
	return {
		"data": {
			"labels": [b["label"] for b in cols],
			"datasets": [
				{"name": _("Cash Income"), "values": [flt(totals["Income"].get(b["key"], 0.0), 2) for b in cols]},
				{"name": _("Cash Expenses"), "values": [flt(expenses.get(b["key"], 0.0), 2) for b in cols]},
				{"name": _("Net Cash Profit"), "values": [flt(totals["Net"].get(b["key"], 0.0), 2) for b in cols]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}


def get_summary(totals, key):
	net = flt(totals["Net"].get(key, 0.0), 2)
	return [
		{"value": flt(totals["Income"].get(key, 0.0), 2), "label": _("Total Cash Income"), "datatype": "Currency"},
		{"value": flt(totals["COGS"].get(key, 0.0), 2), "label": _("Total Cash COGS"), "datatype": "Currency"},
		{"value": flt(totals["Gross"].get(key, 0.0), 2), "label": _("Gross Profit"), "datatype": "Currency"},
		{"value": flt(totals["Opex"].get(key, 0.0), 2), "label": _("Operating Expenses"), "datatype": "Currency"},
		{"value": net, "label": _("Net Cash-Basis Profit / (Loss)"), "datatype": "Currency",
		 "indicator": "Green" if net >= 0 else "Red"},
	]
