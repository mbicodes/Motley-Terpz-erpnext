"""Inventory Movements page (/app/inventory-movements).

Port of the "Inventory Movements" claude.ai dashboard: every submitted Stock Ledger Entry of a
company, classified into a movement row (purchases, yield, production, issued, sales, adjust,
transfer) and a unit group (LBS / Grams / Grains / Nos). The page builds the monthly tables and
the drill-down from these lines.
"""

import json
import math

import frappe
from frappe import _
from frappe.utils import getdate

DASHBOARD_ORDER = ["Motley Terpz", "TSBC Ranch", "Master Touch Manufacturing"]

LEDGER_COLUMNS = [
	"name", "date", "uom", "stock_uom", "cat", "qty", "value",
	"item_code", "warehouse", "voucher_type", "voucher_no", "entry_type",
]


@frappe.whitelist()
def get_companies():
	allowed = frappe.get_list("Company", pluck="name", order_by="name asc")
	ordered = [c for c in DASHBOARD_ORDER if c in allowed]
	return ordered + [c for c in allowed if c not in ordered]


def _check_company(company):
	if company not in get_companies():
		frappe.throw(_("You do not have access to company {0}.").format(company), frappe.PermissionError)


def _js_round(x, digits):
	f = 10 ** digits
	v = math.floor(x * f + 0.5) / f
	return 0.0 if v == 0 else v


def _unit_group(uom):
	x = (uom or "").strip().lower()
	if x in ("lbs", "lb", "pound", "pounds"):
		return "LBS"
	if x in ("gram", "grams", "g", "gm", "gms"):
		return "Grams"
	if x in ("grain", "grains"):
		return "Grains"
	if x in ("nos", "no", "unit", "units", "each", "pcs", "piece", "pieces"):
		return "Nos"
	return "Other"


@frappe.whitelist()
def get_ledger(company, to_date):
	_check_company(company)
	to_date = str(getdate(to_date))

	purpose = {}
	for s in frappe.get_all(
		"Stock Entry",
		filters={"company": company, "docstatus": 1, "posting_date": ["<=", to_date]},
		fields=["name", "stock_entry_type", "purpose"],
	):
		purpose[s.name] = s.purpose or s.stock_entry_type or ""

	sle = frappe.get_all(
		"Stock Ledger Entry",
		filters={"company": company, "is_cancelled": 0, "posting_date": ["<=", to_date]},
		fields=[
			"name", "posting_date", "posting_time", "creation", "item_code", "warehouse",
			"actual_qty", "qty_after_transaction", "stock_uom", "stock_value_difference",
			"voucher_type", "voucher_no",
		],
		order_by="posting_date asc, posting_time asc, creation asc, name asc",
	)

	last_bal = {}
	rows = []
	for r in sle:
		key = (r.item_code, r.warehouse)
		qat = float(r.qty_after_transaction or 0)
		if r.voucher_type == "Stock Reconciliation":
			q = qat - last_bal.get(key, 0)
		else:
			q = float(r.actual_qty or 0)
		last_bal[key] = qat

		vt = r.voucher_type
		cat = "adjust"
		if vt in ("Purchase Receipt", "Purchase Invoice"):
			cat = "purchases"
		elif vt in ("Delivery Note", "Sales Invoice", "POS Invoice"):
			cat = "sales"
		elif vt == "Subcontracting Receipt":
			cat = "production" if q >= 0 else "issued"
		elif vt == "Stock Entry":
			p = purpose.get(r.voucher_no, "")
			if p == "Material Receipt":
				cat = "yield"
			elif p in ("Manufacture", "Repack", "Conversion", "Disassemble"):
				cat = "production" if q >= 0 else "issued"
			elif p in ("Material Issue", "Material Consumption for Manufacture"):
				cat = "issued"
			elif p in ("Material Transfer", "Material Transfer for Manufacture", "Send to Subcontractor"):
				cat = "transfer"

		rows.append([
			r.name, str(r.posting_date), _unit_group(r.stock_uom), r.stock_uom, cat,
			_js_round(q, 6), _js_round(float(r.stock_value_difference or 0), 2),
			r.item_code, r.warehouse, vt, r.voucher_no,
			purpose.get(r.voucher_no, "") if vt == "Stock Entry" else "",
		])

	item_codes = list({r[7] for r in rows})
	names = dict(frappe.get_all(
		"Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name"], as_list=True,
	)) if item_codes else {}

	return {"columns": LEDGER_COLUMNS, "rows": rows, "item_names": names, "to_date": to_date}


def _rows(doctype, child, fields, company, where, values):
	if not where:
		return []
	sql = f"""
		select {", ".join(fields)}
		from `tab{child}` c join `tab{doctype}` p on p.name = c.parent
		where p.docstatus = 1 and p.company = %(company)s and ({" or ".join(where)})
		order by p.name asc, c.idx asc
	"""
	return frappe.db.sql(sql, {"company": company, **values}, as_dict=True)


def _clean(values):
	return sorted({v for v in values if v})


@frappe.whitelist()
def get_linked_sales(company, delivery_notes=None, sales_invoices=None):
	"""Sales Order / Sales Invoice / Delivery Note lines the linked view needs for these documents.

	Returns every line the page's matching can reach (own lines, direct links, and the
	through-the-Sales-Order fallback), so the page matches them exactly as the dashboard did.
	"""
	_check_company(company)
	dns = _clean(json.loads(delivery_notes) if isinstance(delivery_notes, str) else (delivery_notes or []))
	sis = _clean(json.loads(sales_invoices) if isinstance(sales_invoices, str) else (sales_invoices or []))

	so_fields = ["p.name", "p.transaction_date", "c.name as `row`", "c.item_code", "c.stock_qty", "c.base_net_amount"]
	si_fields = ["p.name", "p.posting_date", "c.name as `row`", "c.item_code", "c.stock_qty", "c.base_net_amount",
		"c.sales_order", "c.so_detail", "c.delivery_note", "c.dn_detail"]
	dn_fields = ["p.name", "p.posting_date", "c.name as `row`", "c.item_code", "c.stock_qty", "c.base_net_amount",
		"c.against_sales_order", "c.so_detail", "c.against_sales_invoice", "c.si_detail"]

	own_dn = _rows("Delivery Note", "Delivery Note Item", dn_fields, company,
		["p.name in %(dns)s"] if dns else [], {"dns": dns})
	own_si = _rows("Sales Invoice", "Sales Invoice Item", si_fields, company,
		["p.name in %(sis)s"] if sis else [], {"sis": sis})

	v = {
		"dn_si_detail": _clean(r.si_detail for r in own_dn),
		"dn_rows": _clean(r.row for r in own_dn),
		"dn_so_detail": _clean(r.so_detail for r in own_dn),
		"dn_so": _clean(r.against_sales_order for r in own_dn),
		"si_dn_detail": _clean(r.dn_detail for r in own_si),
		"si_rows": _clean(r.row for r in own_si),
		"si_so_detail": _clean(r.so_detail for r in own_si),
		"si_so": _clean(r.sales_order for r in own_si),
		"so_rows": _clean([r.so_detail for r in own_dn] + [r.so_detail for r in own_si]),
		"dns": dns, "sis": sis,
	}

	def cond(pairs):
		return [expr for expr, key in pairs if v[key]]

	si_rows = _rows("Sales Invoice", "Sales Invoice Item", si_fields, company, cond([
		("p.name in %(sis)s", "sis"),
		("c.name in %(dn_si_detail)s", "dn_si_detail"),
		("c.dn_detail in %(dn_rows)s", "dn_rows"),
		("c.so_detail in %(dn_so_detail)s", "dn_so_detail"),
		("c.sales_order in %(dn_so)s", "dn_so"),
	]), v)
	dn_rows = _rows("Delivery Note", "Delivery Note Item", dn_fields, company, cond([
		("p.name in %(dns)s", "dns"),
		("c.name in %(si_dn_detail)s", "si_dn_detail"),
		("c.si_detail in %(si_rows)s", "si_rows"),
		("c.so_detail in %(si_so_detail)s", "si_so_detail"),
		("c.against_sales_order in %(si_so)s", "si_so"),
	]), v)
	so_rows = _rows("Sales Order", "Sales Order Item", so_fields, company,
		cond([("c.name in %(so_rows)s", "so_rows")]), v)

	return {"so_items": so_rows, "si_items": si_rows, "dn_items": dn_rows}
