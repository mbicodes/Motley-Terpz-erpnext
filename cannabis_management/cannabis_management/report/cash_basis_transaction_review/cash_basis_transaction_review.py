# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Cash Basis Transaction Review.

Every Bank / Cash ledger movement of TSBC Ranch, Motley Terpz and Master Touch
Manufacturing, and how cannabis_management.cash_basis.engine classified it:
P&L (with the head and the company it belongs to), Balance Sheet,
Intercompany, Bank / Cash transfer, or Unclassified - review. A line split
across several heads shows one row per piece; the pieces add up to the line.

"Reconciliation by Cash Account" shows, per Bank / Cash account, the ledger
count and value next to what was allocated to each class: the Difference
column is the proof that every movement is covered.
"""

import collections

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.cash_basis.engine import (
	BS,
	COMPANIES,
	INTERCOMPANY,
	PL,
	TRANSFER,
	UNCLASSIFIED,
	classify,
)
from cannabis_management.cannabis_management.report.reconciled_cash_basis_profit_and_loss.reconciled_cash_basis_profit_and_loss import (
	allowed_companies,
)

RECONCILIATION = "Reconciliation by Cash Account"


def execute(filters=None):
	f = frappe._dict(filters or {})
	if not (f.from_date and f.to_date):
		frappe.throw(_("Set From Date and To Date."))
	frappe.has_permission("GL Entry", throw=True)
	allowed = set(allowed_companies())
	if f.company and f.company not in allowed:
		frappe.throw(_("Not permitted for {0}").format(f.company), frappe.PermissionError)
	scope = {f.company} if f.company else allowed

	out, cash = classify(f.from_date, f.to_date)
	# A movement shows when its ledger or the company it was attributed to is in
	# scope, and neither is a company the user may not see.
	out = [o for o in out if o.cash_company in allowed and o.company in allowed
	       and (o.cash_company in scope or o.company in scope)]
	cash = [c for c in cash if c.company in scope]
	if f.cash_account:
		out = [o for o in out if o.cash_account == f.cash_account]
		cash = [c for c in cash if c.account == f.cash_account]

	summary = get_summary(out, cash)
	if f.view == RECONCILIATION:
		return reconciliation_columns(), reconciliation_rows(out, cash, scope), None, None, summary

	if f.classification:
		out = [o for o in out if o.cls == f.classification]
	if f.review_only:
		out = [o for o in out if o.review or o.cls == UNCLASSIFIED]
	rows = [
		{
			"posting_date": o.posting_date,
			"voucher_type": o.voucher_type,
			"voucher_no": o.voucher_no,
			"cash_account": o.cash_account,
			"cash_company": o.cash_company,
			"against": o.against,
			"amount": flt(o.amount, 2),
			"classification": o.cls,
			"company": o.company,
			"section": o.section,
			"head": o.head,
			"pl_amount": flt(o.pl_amount, 2) if o.cls == PL else None,
			"partner": o.partner,
			"party": o.party,
			"via_type": o.via_type,
			"via": o.via,
			"reason": o.reason,
			"review": o.review or (1 if o.cls == UNCLASSIFIED else 0),
			"remark": o.remark,
		}
		for o in sorted(out, key=lambda o: (o.posting_date, o.voucher_no, o.cash_gl))
	]
	return allocation_columns(), rows, None, None, summary


def allocation_columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "voucher_no", "label": _("Voucher"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
		{"fieldname": "cash_account", "label": _("Bank / Cash Account"), "fieldtype": "Link", "options": "Account", "width": 210},
		{"fieldname": "cash_company", "label": _("Ledger Company"), "fieldtype": "Link", "options": "Company", "width": 170},
		{"fieldname": "against", "label": _("Against Account (GL)"), "fieldtype": "Data", "width": 200},
		{"fieldname": "amount", "label": _("Amount (+ in / - out)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "classification", "label": _("Classification"), "fieldtype": "Data", "width": 160},
		{"fieldname": "company", "label": _("Attributed To"), "fieldtype": "Link", "options": "Company", "width": 170},
		{"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 80},
		{"fieldname": "head", "label": _("P&L Head"), "fieldtype": "Data", "width": 260},
		{"fieldname": "pl_amount", "label": _("P&L Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "partner", "label": _("Other Side Account"), "fieldtype": "Link", "options": "Account", "width": 230},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 170},
		{"fieldname": "via_type", "label": _("Traced To Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "via", "label": _("Traced To"), "fieldtype": "Dynamic Link", "options": "via_type", "width": 170},
		{"fieldname": "reason", "label": _("How It Was Read"), "fieldtype": "Data", "width": 420},
		{"fieldname": "review", "label": _("Needs Review"), "fieldtype": "Check", "width": 90},
		{"fieldname": "remark", "label": _("Remark"), "fieldtype": "Data", "width": 260},
	]


def reconciliation_columns():
	cur = lambda name, label, w=130: {"fieldname": name, "label": label, "fieldtype": "Currency", "width": w}  # noqa: E731
	return [
		{"fieldname": "cash_account", "label": _("Bank / Cash Account"), "fieldtype": "Link", "options": "Account", "width": 230},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 170},
		{"fieldname": "lines", "label": _("Ledger Lines"), "fieldtype": "Int", "width": 100},
		cur("ledger_in", _("Ledger In")),
		cur("ledger_out", _("Ledger Out")),
		cur("ledger_net", _("Ledger Net")),
		cur("pl", _("P&L")),
		cur("bs", _("Balance Sheet")),
		cur("ic", _("Intercompany")),
		cur("transfer", _("Transfers")),
		cur("unclassified", _("Unclassified")),
		{"fieldname": "unclassified_count", "label": _("Unclassified #"), "fieldtype": "Int", "width": 110},
		cur("allocated", _("Allocated Net")),
		cur("difference", _("Difference"), 110),
	]


def reconciliation_rows(out, cash, scope):
	key = {PL: "pl", BS: "bs", INTERCOMPANY: "ic", TRANSFER: "transfer", UNCLASSIFIED: "unclassified"}
	rows = {}
	for c in cash:
		r = rows.setdefault(c.account, collections.defaultdict(float, cash_account=c.account, company=c.company))
		r["lines"] += 1
		r["ledger_in"] += flt(c.debit)
		r["ledger_out"] += flt(c.credit)
	for o in out:
		if o.cash_account not in rows:
			continue
		r = rows[o.cash_account]
		r[key[o.cls]] += o.amount
		r["allocated"] += o.amount
		if o.cls == UNCLASSIFIED:
			r["unclassified_count"] += 1
	data = []
	for name in sorted(rows, key=lambda a: (rows[a]["company"], a)):
		r = rows[name]
		r["ledger_net"] = r["ledger_in"] - r["ledger_out"]
		r["difference"] = r["allocated"] - r["ledger_net"]
		data.append({k: (flt(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
	if data:
		total = collections.defaultdict(float, cash_account=_("Total"), bold=1)
		for r in data:
			for k, v in r.items():
				if isinstance(v, (int, float)) and k not in ("bold",):
					total[k] += v
		data.append({k: (flt(v, 2) if isinstance(v, float) else v) for k, v in total.items()})
	return data


def get_summary(out, cash):
	unclassified = [o for o in out if o.cls == UNCLASSIFIED]
	flagged = [o for o in out if o.review and o.cls != UNCLASSIFIED]
	ledger = sum(flt(c.debit) - flt(c.credit) for c in cash)
	allocated = sum(o.amount for o in out if o.cash_gl in {c.name for c in cash})
	return [
		{"value": len(cash), "label": _("Bank / Cash Ledger Lines"), "datatype": "Int"},
		{"value": flt(allocated - ledger, 2), "label": _("Unallocated Difference"), "datatype": "Currency",
		 "indicator": "Green" if abs(allocated - ledger) < 0.01 else "Red"},
		{"value": len(unclassified), "label": _("Unclassified Movements"), "datatype": "Int",
		 "indicator": "Red" if unclassified else "Green"},
		{"value": sum(abs(o.amount) for o in unclassified), "label": _("Unclassified Value"), "datatype": "Currency",
		 "indicator": "Red" if unclassified else "Green"},
		{"value": len(flagged), "label": _("In P&L, Head Approximated"), "datatype": "Int", "indicator": "Orange"},
	]
