"""Accounts Receivable Report page (/app/receivable-ledgers).

Port of the claude.ai "Accounts Receivable Report — Live ERP" dashboard. The server returns the
same rows the dashboard's datasets read (Sales Invoice Collection Register, Accounts Receivable
Summary, receipts, journal-entry payment ledger lines, inter-company bank receipts, and SO/SI/DN
lines); the page builds the ledgers and the strain tables from them exactly as the dashboard did.
"""

import json

import frappe
from frappe import _
from frappe.desk.query_report import run as run_report
from frappe.utils import add_days, getdate

COMPANIES = ["TSBC Ranch", "Master Touch Manufacturing", "Motley Terpz"]

IC_PAYABLE_ACCOUNTS = [
	"IC Payable - MTM - TSBC", "IC Payable MT - TSBC", "IC Payable - TSBC - MTM",
	"IC Payable - Motley Terpz - MTM", "Inter Company Payable MT - MTM", "Inter-Company Payable - MT",
]

COLLECTION_FIELDS = [
	"posting_date", "invoice", "customer", "status", "due_date", "return_against",
	"invoice_amount", "paid_amount", "credit_note_adjusted", "outstanding", "receivable_account",
]


@frappe.whitelist()
def get_companies():
	allowed = set(frappe.get_list("Company", pluck="name"))
	return [c for c in COMPANIES if c in allowed]


def _companies(companies):
	if isinstance(companies, str):
		companies = json.loads(companies) if companies.startswith("[") else [companies]
	allowed = get_companies()
	for c in companies:
		if c not in allowed:
			frappe.throw(_("You do not have access to company {0}.").format(c), frappe.PermissionError)
	return list(companies)


def _range(from_date, to_date):
	f, t = getdate(from_date), getdate(to_date)
	if t < f:
		f, t = t, f
	return f, t


def _num(v):
	try:
		return float(v or 0)
	except (TypeError, ValueError):
		return 0.0


@frappe.whitelist()
def get_ledger_data(companies, from_date, to_date):
	cos = _companies(companies)
	f, t = _range(from_date, to_date)
	opening_date = add_days(f, -1)
	win_to = add_days(t, 90)

	collection, opening = [], []
	for co in cos:
		r = run_report("Sales Invoice Collection Register",
			filters={"company": co, "from_date": str(f), "to_date": str(t)}, ignore_prepared_report=True)
		for x in r.get("result") or []:
			if not isinstance(x, dict):
				continue
			row = {k: x.get(k) for k in COLLECTION_FIELDS}
			for k in ("invoice_amount", "paid_amount", "credit_note_adjusted", "outstanding"):
				row[k] = _num(row[k])
			for k in ("posting_date", "due_date"):
				row[k] = str(row[k]) if row[k] else None
			row["return_against"] = row["return_against"] or None
			row["company"] = co
			collection.append(row)

		o = run_report("Accounts Receivable Summary",
			filters={"company": co, "report_date": str(opening_date), "ageing_based_on": "Posting Date"},
			ignore_prepared_report=True)
		for x in o.get("result") or []:
			if isinstance(x, dict) and x.get("party"):
				opening.append({"company": co, "party": x["party"], "outstanding": _num(x.get("outstanding"))})

	payments = frappe.db.sql("""
		select pe.name, pe.company, pe.posting_date, pe.mode_of_payment, pe.paid_to, pe.party,
			pe.unallocated_amount, r.reference_name as ref, r.reference_doctype as ref_type,
			r.allocated_amount as alloc
		from `tabPayment Entry` pe
		left join `tabPayment Entry Reference` r on r.parent = pe.name and r.parenttype = 'Payment Entry'
		where pe.company in %(cos)s and pe.docstatus = 1 and pe.party_type = 'Customer'
			and pe.payment_type = 'Receive' and pe.posting_date between %(f)s and %(t)s
		order by pe.posting_date asc, pe.name asc, r.idx asc
	""", {"cos": cos, "f": f, "t": t}, as_dict=True)

	jv = frappe.db.sql("""
		select posting_date, company, voucher_no, account, party, against_voucher_type,
			against_voucher_no, amount
		from `tabPayment Ledger Entry`
		where company in %(cos)s and delinked = 0 and party_type = 'Customer'
			and voucher_type = 'Journal Entry' and posting_date between %(f)s and %(t)s
		order by posting_date asc, creation asc, name asc
	""", {"cos": cos, "f": f, "t": t}, as_dict=True)

	bank = frappe.db.sql("""
		select posting_date, company, voucher_no, account, credit, against
		from `tabGL Entry`
		where account in %(accts)s and company in %(all_cos)s and credit > 0 and is_cancelled = 0
			and voucher_type = 'Journal Entry' and posting_date between %(f)s and %(t)s
		order by posting_date asc, creation asc, name asc
	""", {"accts": IC_PAYABLE_ACCOUNTS, "all_cos": get_companies() or [""], "f": opening_date, "t": win_to}, as_dict=True)

	def clean(rows, money):
		for r in rows:
			r["posting_date"] = str(r["posting_date"]) if r.get("posting_date") else None
			for k in money:
				r[k] = _num(r.get(k))
		return rows

	return {
		"companies": cos,
		"from_date": str(f),
		"to_date": str(t),
		"collection": collection,
		"opening": opening,
		"payments": clean(payments, ["unallocated_amount", "alloc"]),
		"jv": clean(jv, ["amount"]),
		"bank": clean(bank, ["credit"]),
	}


@frappe.whitelist()
def get_sales_lines(company, from_date, to_date, customer=None):
	_companies([company])
	f, t = _range(from_date, to_date)
	win_from, win_to = add_days(f, -180), add_days(t, 90)
	cust_cond = " and p.customer = %(cust)s" if customer else ""
	args = {"co": company, "f": f, "t": t, "wf": win_from, "wt": win_to, "cust": customer}

	si = frappe.db.sql(f"""
		select p.name, p.customer, p.posting_date, c.item_name, c.qty, c.uom, c.amount,
			c.sales_order, c.so_detail
		from `tabSales Invoice` p join `tabSales Invoice Item` c on c.parent = p.name
		where p.company = %(co)s and p.docstatus = 1 and p.is_return = 0
			and p.posting_date between %(f)s and %(t)s {cust_cond}
		order by p.posting_date desc, p.name, c.idx
	""", args, as_dict=True)
	so = frappe.db.sql(f"""
		select p.name, p.customer, p.transaction_date, c.name as so_detail, c.item_name, c.qty, c.uom, c.amount
		from `tabSales Order` p join `tabSales Order Item` c on c.parent = p.name
		where p.company = %(co)s and p.docstatus = 1
			and p.transaction_date between %(wf)s and %(t)s {cust_cond}
		order by p.transaction_date desc, p.name, c.idx
	""", args, as_dict=True)
	dn = frappe.db.sql(f"""
		select p.name, p.customer, p.posting_date, c.item_name, c.qty, c.uom, c.amount,
			c.so_detail, c.against_sales_order as sales_order
		from `tabDelivery Note` p join `tabDelivery Note Item` c on c.parent = p.name
		where p.company = %(co)s and p.docstatus = 1 and p.is_return = 0
			and p.posting_date between %(wf)s and %(wt)s {cust_cond}
		order by p.posting_date desc, p.name, c.idx
	""", args, as_dict=True)

	for rows, dkey in ((si, "posting_date"), (so, "transaction_date"), (dn, "posting_date")):
		for r in rows:
			r[dkey] = str(r[dkey])
			r["qty"] = _num(r["qty"])
			r["amount"] = _num(r["amount"])
	return {"si_lines": si, "so_lines": so, "dn_lines": dn}
