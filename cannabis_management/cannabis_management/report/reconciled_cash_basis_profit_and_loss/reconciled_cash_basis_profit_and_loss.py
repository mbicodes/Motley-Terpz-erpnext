# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Reconciled Cash Basis Profit and Loss.

Cash income, cash COGS, gross profit, operating expenses and net cash-basis
profit for TSBC Ranch, Motley Terpz, Master Touch Manufacturing or all three
consolidated, read from every Bank / Cash ledger movement by
cannabis_management.cash_basis.engine (see there for the rules).

Below the P&L, the reconciliation to the Bank / Cash ledgers: the movements
that are not P&L (Balance Sheet, intercompany, transfers, unclassified) added
back to the net profit give the net change in the ledgers, checked against the
GL. Every row there comes from the same allocations, so the difference is 0.00.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, formatdate, get_first_day, get_last_day, getdate

from cannabis_management.cash_basis.engine import BS, COMPANIES, INTERCOMPANY, PL, TRANSFER, UNCLASSIFIED, classify

CONSOLIDATED = "Consolidated"
SECTIONS = (
	("Income", _("Cash Income"), _("Total Cash Income")),
	("COGS", _("Cash Cost of Goods Sold"), _("Total Cash COGS")),
	("Opex", _("Operating Expenses"), _("Total Operating Expenses")),
)


def allowed_companies():
	"""The three companies, less any the user's permissions exclude."""
	return [c for c in frappe.get_list("Company", pluck="name") if c in COMPANIES]


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not (f.from_date and f.to_date):
		frappe.throw(_("Set From Date and To Date."))
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
	columns = [{"fieldname": "account", "label": _("Account"), "fieldtype": "Data", "width": 380}] + [
		{"fieldname": b["key"], "label": b["label"], "fieldtype": "Currency", "width": 150} for b in buckets
	]
	data = build_rows(out, cash, buckets, scope)
	summary = get_summary(data, buckets[-1]["key"])
	unclassified = [o for o in out if o.cls == UNCLASSIFIED and (o.company in scope or o.cash_company in scope)]
	message = _(
		"{0} Bank / Cash ledger lines analysed. {1} movements ({2}) are Unclassified and left out of the P&L: "
		"see the Cash Basis Transaction Review report."
	).format(
		len([c for c in cash if c.company in scope]),
		len(unclassified),
		frappe.format_value(sum(abs(o.amount) for o in unclassified), {"fieldtype": "Currency"}),
	)
	return columns, data, message, None, summary


def get_buckets(f, scope):
	"""Value columns: one per company plus Consolidated, or one per period plus Total."""
	start, end = getdate(f.from_date), getdate(f.to_date)
	if f.periodicity in (None, "", "Total"):
		if len(scope) > 1:
			return [
				{"key": frappe.scrub(c), "label": c, "companies": {c}, "from": start, "to": end} for c in scope
			] + [{"key": "total", "label": _("Consolidated"), "companies": set(scope), "from": start, "to": end}]
		return [{"key": "total", "label": _("Total"), "companies": set(scope), "from": start, "to": end}]
	months = 3 if f.periodicity == "Quarterly" else 1
	out, d = [], get_first_day(start)
	if months == 3:
		d = getdate(f"{d.year}-{(d.month - 1) // 3 * 3 + 1:02d}-01")
	while d <= end:
		p_end = get_last_day(add_months(d, months - 1))
		p_from, p_to = max(d, start), min(p_end, end)
		label = formatdate(d, "MMM yyyy") if months == 1 else f"Q{(d.month - 1) // 3 + 1} {d.year}"
		out.append({"key": f"p_{d.strftime('%Y_%m')}", "label": label, "companies": set(scope),
		            "from": p_from, "to": p_to})
		d = add_days(p_end, 1)
	out.append({"key": "total", "label": _("Total"), "companies": set(scope), "from": start, "to": end})
	return out


def build_rows(out, cash, buckets, scope):
	def in_bucket(b, date):
		return b["from"] <= getdate(date) <= b["to"]

	heads = {s: {} for s, _l, _t in SECTIONS}       # section -> head -> {bucket: value}
	memo = {k: {} for k in ("by_other", "for_other", BS, INTERCOMPANY, TRANSFER, UNCLASSIFIED, "gl")}

	def add(target, b, v):
		target[b["key"]] = target.get(b["key"], 0.0) + v

	for o in out:
		for b in buckets:
			if not in_bucket(b, o.posting_date):
				continue
			cos = b["companies"]
			if o.cls == PL:
				if o.company in cos:
					add(heads[o.section].setdefault(o.head, {}), b, o.pl_amount)
					if o.cash_company not in cos:
						add(memo["by_other"], b, -o.amount)
				elif o.cash_company in cos:
					add(memo["for_other"], b, o.amount)
			elif o.cash_company in cos:
				add(memo[o.cls], b, o.amount)
	for c in cash:
		for b in buckets:
			if c.company in b["companies"] and in_bucket(b, c.posting_date):
				add(memo["gl"], b, flt(c.debit) - flt(c.credit))

	keys = [b["key"] for b in buckets]

	def row(label, values=None, indent=0, bold=0, kind=None):
		r = {"account": label, "indent": indent, "bold": bold, "kind": kind}
		for k in keys:
			r[k] = flt((values or {}).get(k, 0.0), 2)
		return r

	def combine(*parts):
		out = {}
		for sign, vals in parts:
			for k in keys:
				out[k] = out.get(k, 0.0) + sign * vals.get(k, 0.0)
		return out

	data, totals = [], {}
	for section, title, total_label in SECTIONS:
		data.append(row(title, bold=1, kind="section"))
		total = {}
		for head in sorted(heads[section], key=lambda h: h.lower()):
			vals = heads[section][head]
			if all(abs(vals.get(k, 0.0)) < 0.005 for k in keys):
				continue
			data.append(row(head, vals, indent=1, kind="head"))
			total = combine((1, total), (1, vals))
		totals[section] = total
		data.append(row(total_label, total, bold=1, kind="total"))
		if section == "COGS":
			data.append(row(_("Gross Profit"), combine((1, totals["Income"]), (-1, total)), bold=1, kind="profit"))
		data.append({})
	net = combine((1, totals["Income"]), (-1, totals["COGS"]), (-1, totals["Opex"]))
	data.insert(len(data) - 1, row(_("Net Cash-Basis Profit / (Loss)"), net, bold=1, kind="net"))

	data.append(row(_("Reconciliation to the Bank / Cash ledgers"), bold=1, kind="section"))
	data.append(row(_("Net Cash-Basis Profit / (Loss)"), net, indent=1))
	lines = [
		(_("Less: P&L paid / received through another company's bank / cash"), memo["by_other"]),
		(_("Add: paid / received for another company (its P&L)"), memo["for_other"]),
		(_("Balance Sheet movements (inventory, assets, loans, owners, taxes...)"), memo[BS]),
		(_("Intercompany movements"), memo[INTERCOMPANY]),
		(_("Transfers between own Bank / Cash accounts"), memo[TRANSFER]),
		(_("Unclassified - requires review (not in the P&L)"), memo[UNCLASSIFIED]),
	]
	for label, vals in lines:
		data.append(row(label, vals, indent=1, kind="unclassified" if vals is memo[UNCLASSIFIED] else None))
	allocated = combine((1, net), *[(1, v) for _l, v in lines])
	data.append(row(_("Net change in Bank / Cash (from the allocations)"), allocated, bold=1, kind="total"))
	data.append(row(_("Net change in Bank / Cash (General Ledger)"), memo["gl"], indent=1))
	data.append(row(_("Difference"), combine((1, allocated), (-1, memo["gl"])), bold=1, kind="check"))
	return data


def get_summary(data, key):
	def value(label):
		r = next((r for r in data if r.get("account") == label), None)
		return flt(r.get(key)) if r else 0.0

	net = value(_("Net Cash-Basis Profit / (Loss)"))
	return [
		{"value": value(_("Total Cash Income")), "label": _("Total Cash Income"), "datatype": "Currency"},
		{"value": value(_("Total Cash COGS")), "label": _("Total Cash COGS"), "datatype": "Currency"},
		{"value": value(_("Gross Profit")), "label": _("Gross Profit"), "datatype": "Currency"},
		{"value": value(_("Total Operating Expenses")), "label": _("Operating Expenses"), "datatype": "Currency"},
		{"value": net, "label": _("Net Cash-Basis Profit / (Loss)"), "datatype": "Currency",
		 "indicator": "Green" if net >= 0 else "Red"},
	]
