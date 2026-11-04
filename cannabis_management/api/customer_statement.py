import json
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.cannabis_management.page.ar_dashboard.ar_dashboard import (
	TMM_GROUP_COMPANIES,
	_permitted_companies,
	_scope_companies,
)

STATEMENT_FROM_DATE = "2024-01-01"
ALLOWED_ROLES = {
	"Accounts User",
	"Accounts Manager",
	"System Manager",
	"Account Receivable",
	"AR Dashboard Viewer",
}
TEMPLATE = "cannabis_management/templates/statement/customer_statement.html"


def _money(v):
	v = flt(v, 3)
	return "{}$ {:,.3f}".format("-" if v < 0 else "", abs(v))


def _fmt_date(d):
	return getdate(d).strftime("%m-%d-%Y")


def _resolve_companies(company):
	"""Returns (companies_or_None, label). None = no company filter (everything the user may see)."""
	permitted = _permitted_companies()
	companies, label = None, "All Companies - Consolidated"

	if isinstance(company, str) and company.strip().startswith("["):
		company = json.loads(company)

	if isinstance(company, (list, tuple)):
		companies, label = list(company), " + ".join(company)
	elif company in (None, "", "__ALL__"):
		pass
	elif company == "TMM Group":
		companies, label = list(TMM_GROUP_COMPANIES), "TMM Group"
	else:
		companies, label = [company], company

	if permitted is not None:
		companies = _scope_companies(companies if companies is not None else permitted, permitted)
	return companies, label


def build_statement_context(customer, company=None, from_date=None, to_date=None):
	"""Reusable: returns the Jinja context for the statement (Customer form / bulk print can reuse it)."""
	from_date = getdate(from_date or STATEMENT_FROM_DATE)
	to_date = getdate(to_date or nowdate())
	companies, label = _resolve_companies(company)

	cond, vals = "", {"customer": customer, "from_date": from_date, "to_date": to_date}
	if companies is not None:
		cond = "AND company IN %(companies)s"
		vals["companies"] = tuple(companies) or ("__none__",)

	base = """FROM `tabGL Entry`
		WHERE party_type = 'Customer' AND party = %(customer)s AND is_cancelled = 0 {cond}""".format(cond=cond)

	opening = frappe.db.sql(
		"SELECT COALESCE(SUM(debit),0) - COALESCE(SUM(credit),0) " + base + " AND posting_date < %(from_date)s",
		vals,
	)[0][0]
	opening = flt(opening, 3)

	entries = frappe.db.sql(
		"""SELECT posting_date, company, voucher_type, voucher_no, debit, credit """
		+ base
		+ """ AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		ORDER BY posting_date, creation""",
		vals,
		as_dict=True,
	)

	if not entries and not opening:
		frappe.throw(_("No transactions found for this customer"), title=_("Print Statement"))

	rows, balance, t_debit, t_credit = [], opening, 0.0, 0.0
	for e in entries:
		balance += flt(e.debit) - flt(e.credit)
		t_debit += flt(e.debit)
		t_credit += flt(e.credit)
		rows.append(
			{
				"date": _fmt_date(e.posting_date),
				"company": e.company,
				"voucher_no": e.voucher_no,
				"voucher_type": e.voucher_type,
				"debit": _money(e.debit),
				"credit": _money(e.credit),
				"balance": _money(balance),
			}
		)

	return {
		"customer_name": frappe.db.get_value("Customer", customer, "customer_name") or customer,
		"from_date": _fmt_date(from_date),
		"to_date": _fmt_date(to_date),
		"company_label": label,
		"opening": {"debit": _money(0), "credit": _money(0), "balance": _money(opening)},
		"rows": rows,
		"total": {"debit": _money(t_debit), "credit": _money(t_credit), "balance": _money(balance - opening)},
		"closing": {"debit": _money(t_debit), "credit": _money(t_credit), "balance": _money(balance)},
		"printed_on": datetime.now().strftime("%m-%d-%Y"),
		"entry_count": len(rows),
	}


@frappe.whitelist()
def get_customer_statement(customer, company=None, from_date=None, to_date=None):
	if not ALLOWED_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You are not permitted to print customer statements"), frappe.PermissionError)

	ctx = build_statement_context(customer, company, from_date, to_date)
	html = frappe.render_template(TEMPLATE, ctx)

	from frappe.utils.pdf import get_pdf

	frappe.local.response.filename = "{}_Statement_of_Account.pdf".format(
		"".join(c if c.isalnum() else "_" for c in ctx["customer_name"])
	)
	frappe.local.response.filecontent = get_pdf(
		html,
		options={
			"page-size": "A4",
			"orientation": "Portrait",
			"margin-top": "12mm",
			"margin-bottom": "12mm",
			"margin-left": "10mm",
			"margin-right": "10mm",
			"encoding": "UTF-8",
		},
	)
	frappe.local.response.type = "pdf"
