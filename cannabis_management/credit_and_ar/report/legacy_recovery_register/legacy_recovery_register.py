"""Legacy Recovery Register (§12).

Everything invoiced before the policy effective date. Collected on its original
terms — **no finance charges apply, ever** — and excluded from the new-book AR
cap, DSO and CEI.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from cannabis_management.credit_and_ar import utils
from cannabis_management.credit_and_ar.report import report_utils


def execute(filters=None):
	filters = frappe._dict(filters or {})
	effective_date = utils.policy_effective_date()

	if not effective_date:
		return (
			get_columns(),
			[],
			_(
				"<b>Policy Effective Date is not set.</b> Until Finance sets it in Credit "
				"Policy Settings there is no Legacy/New Book split, so this register is empty."
			),
			None,
		)

	data = get_data(filters, effective_date)
	return get_columns(), data, get_message(data, effective_date), get_chart(data)


def get_data(filters, effective_date):
	conditions = ["si.docstatus = 1", "si.posting_date < %(effective_date)s"]
	values = {"effective_date": effective_date}

	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters["company"]
	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters["customer"]
	if not filters.get("include_settled"):
		conditions.append("si.outstanding_amount > 0")

	rows = frappe.db.sql(
		f"""
		SELECT si.name, si.customer, si.company, si.posting_date, si.due_date,
		       si.base_grand_total, si.outstanding_amount, si.conversion_rate,
		       si.custom_ledger, si.custom_ar_case
		FROM `tabSales Invoice` si
		WHERE {" AND ".join(conditions)}
		ORDER BY si.posting_date ASC
		""",
		values,
		as_dict=True,
	)

	excluded = set(report_utils.excluded_customers())
	rows = [row for row in rows if row.customer not in excluded]
	if not rows:
		return []

	recovered = _recovered_this_week([row.name for row in rows])
	today = getdate(nowdate())

	data = []
	for row in rows:
		outstanding = flt(row.outstanding_amount) * flt(row.conversion_rate or 1)
		invoiced = flt(row.base_grand_total)
		data.append(
			{
				"invoice": row.name,
				"customer": row.customer,
				"company": row.company,
				"posting_date": row.posting_date,
				"due_date": row.due_date,
				"invoiced": invoiced,
				"recovered_total": invoiced - outstanding,
				"recovered_this_week": flt(recovered.get(row.name)),
				"outstanding": outstanding,
				"days_past_due": (today - getdate(row.due_date)).days if row.due_date else 0,
				"ledger": row.custom_ledger or utils.LEDGER_LEGACY,
				"ar_case": row.custom_ar_case,
				"finance_charges": _("Never — original terms"),
			}
		)

	return data


def _recovered_this_week(invoice_names: list[str]) -> dict:
	"""Cash actually collected against these invoices since Monday."""
	if not invoice_names:
		return {}

	from cannabis_management.credit_and_ar.metrics import receivable_accounts

	accounts = receivable_accounts()
	if not accounts:
		return {}

	today = getdate(nowdate())
	week_start = add_days(today, -today.weekday())

	result: dict[str, float] = {}
	chunk = 500
	for start in range(0, len(invoice_names), chunk):
		names = invoice_names[start : start + chunk]
		rows = frappe.db.sql(
			"""
			SELECT against_voucher AS invoice, SUM(credit - debit) AS recovered
			FROM `tabGL Entry`
			WHERE is_cancelled = 0
			  AND party_type = 'Customer'
			  AND against_voucher_type = 'Sales Invoice'
			  AND against_voucher IN %(invoices)s
			  AND account IN %(accounts)s
			  AND posting_date >= %(week_start)s
			GROUP BY against_voucher
			""",
			{"invoices": names, "accounts": accounts, "week_start": week_start},
			as_dict=True,
		)
		for row in rows:
			result[row.invoice] = flt(row.recovered)

	return result


def get_message(data, effective_date):
	if not data:
		return _("No legacy invoices before {0}.").format(
			frappe.format(effective_date, {"fieldtype": "Date"})
		)

	outstanding = sum(row["outstanding"] for row in data)
	this_week = sum(row["recovered_this_week"] for row in data)
	invoiced = sum(row["invoiced"] for row in data)

	settings = utils.get_settings()
	cap = flt(settings.total_ar_cap)

	return _(
		"Invoices dated before <b>{effective}</b> &nbsp;·&nbsp; "
		"originally invoiced <b>{invoiced}</b> &nbsp;·&nbsp; "
		"still outstanding <b>{outstanding}</b> &nbsp;·&nbsp; "
		"recovered this week <b>{week}</b><br>"
		"<span style='color:#666'>Collected on original terms — <b>no finance charges apply "
		"to any of these</b>. Legacy is reported separately and does <b>not</b> count toward "
		"the {cap} new-book AR cap.</span>"
	).format(
		effective=frappe.format(effective_date, {"fieldtype": "Date"}),
		invoiced=utils.fmt_currency(invoiced),
		outstanding=utils.fmt_currency(outstanding),
		week=utils.fmt_currency(this_week),
		cap=utils.fmt_currency(cap),
	)


def get_chart(data):
	if not data:
		return None

	by_customer: dict[str, float] = {}
	for row in data:
		by_customer[row["customer"]] = by_customer.get(row["customer"], 0.0) + row["outstanding"]

	top = sorted(by_customer.items(), key=lambda item: item[1], reverse=True)[:10]
	return {
		"data": {
			"labels": [name for name, _amount in top],
			"datasets": [{"name": _("Legacy Outstanding"), "values": [amount for _n, amount in top]}],
		},
		"type": "bar",
		"colors": ["#8b5cf6"],
	}


def get_columns():
	return [
		{"label": _("Invoice"), "fieldname": "invoice", "fieldtype": "Link",
		 "options": "Sales Invoice", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
		 "options": "Customer", "width": 190},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link",
		 "options": "Company", "width": 150},
		{"label": _("Posted"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Due"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Days Past Due"), "fieldname": "days_past_due", "fieldtype": "Int",
		 "width": 120},
		{"label": _("Invoiced"), "fieldname": "invoiced", "fieldtype": "Currency", "width": 120},
		{"label": _("Recovered"), "fieldname": "recovered_total", "fieldtype": "Currency",
		 "width": 120},
		{"label": _("Recovered This Week"), "fieldname": "recovered_this_week",
		 "fieldtype": "Currency", "width": 160},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency",
		 "width": 130},
		{"label": _("Ledger"), "fieldname": "ledger", "fieldtype": "Data", "width": 100},
		{"label": _("Finance Charges"), "fieldname": "finance_charges", "fieldtype": "Data",
		 "width": 170},
		{"label": _("AR Case"), "fieldname": "ar_case", "fieldtype": "Link",
		 "options": "AR Case", "width": 150},
	]
