# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	currency = "Company:company:default_currency"
	return [
		{"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"label": _("Sales Invoice Date"), "fieldname": "sales_invoice_date", "fieldtype": "Date", "width": 110},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 150},
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 150},
		{"label": _("Delivery Note Date"), "fieldname": "delivery_note_date", "fieldtype": "Date", "width": 110},
		{"label": _("DN Found Via"), "fieldname": "dn_source", "fieldtype": "Data", "width": 120},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 110},
		{"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("SI Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("SI Rate"), "fieldname": "rate", "fieldtype": "Currency", "options": currency, "width": 110},
		{"label": _("SI Amount"), "fieldname": "amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("DN Qty"), "fieldname": "dn_qty", "fieldtype": "Float", "width": 90},
		{"label": _("DN Rate"), "fieldname": "dn_rate", "fieldtype": "Currency", "options": currency, "width": 110},
		{"label": _("DN Amount"), "fieldname": "dn_amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency", "options": currency, "width": 110},
		{"label": _("Valuation Amount"), "fieldname": "valuation_amount", "fieldtype": "Currency", "options": currency, "width": 120},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
	]


def get_data(filters):
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"]
	# "All Company" arrives with no company key (stripped by api.report_filters)
	if filters.company:
		conditions.append("si.company = %(company)s")
	if filters.customer:
		conditions.append("si.customer = %(customer)s")
	if filters.item_code:
		conditions.append("sii.item_code = %(item_code)s")

	items = frappe.db.sql(
		f"""
		SELECT
			si.name AS sales_invoice, si.posting_date AS sales_invoice_date, si.customer,
			si.company, si.update_stock,
			sii.name AS si_detail, sii.item_code, sii.item_name, sii.qty, sii.stock_qty,
			sii.uom, sii.base_net_rate AS rate, sii.base_net_amount AS amount,
			sii.incoming_rate, sii.sales_order, sii.so_detail,
			sii.delivery_note, sii.dn_detail
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE {" AND ".join(conditions)}
		ORDER BY si.posting_date, si.name, sii.idx
		""",
		filters,
		as_dict=True,
	)
	if not items:
		return []

	invoices = list({d.sales_invoice for d in items})
	sales_orders = list({d.sales_order for d in items if d.sales_order})

	# Delivery Note rows linked either directly to the invoice or to its Sales Order
	dn_rows = frappe.db.sql(
		"""
		SELECT dni.parent AS delivery_note, dn.posting_date AS delivery_note_date,
			dni.name AS dn_detail, dni.item_code, dni.stock_qty, dni.incoming_rate,
			dni.qty, dni.base_net_amount AS amount,
			dni.against_sales_invoice, dni.si_detail, dni.against_sales_order, dni.so_detail
		FROM `tabDelivery Note Item` dni
		INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
		WHERE dni.against_sales_invoice IN %(invoices)s
			OR (dni.against_sales_order IN %(sales_orders)s)
		""",
		{"invoices": invoices, "sales_orders": sales_orders or [""]},
		as_dict=True,
	)
	by_dn_detail = {d.dn_detail: d for d in dn_rows}
	by_si_detail, by_si_item, by_so_detail, by_so_item = {}, {}, {}, {}
	for d in dn_rows:
		if d.against_sales_invoice:
			by_si_detail.setdefault(d.si_detail, []).append(d)
			by_si_item.setdefault((d.against_sales_invoice, d.item_code), []).append(d)
		if d.against_sales_order:
			by_so_detail.setdefault(d.so_detail, []).append(d)
			by_so_item.setdefault((d.against_sales_order, d.item_code), []).append(d)

	# Delivery Note rows referenced from the invoice item but not fetched above
	missing = {d.dn_detail for d in items if d.delivery_note and d.dn_detail and d.dn_detail not in by_dn_detail}
	missing_dn_rows = {
		d.dn_detail: d
		for d in frappe.db.sql(
			"""
			SELECT dni.name AS dn_detail, dn.posting_date AS delivery_note_date,
				dni.qty, dni.base_net_amount AS amount
			FROM `tabDelivery Note Item` dni
			INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent AND dn.docstatus = 1
			WHERE dni.name IN %(names)s
			""",
			{"names": list(missing)},
			as_dict=True,
		)
	} if missing else {}
	missing_dn_dates = dict(
		frappe.get_all("Delivery Note", filters={"name": ["in", list({d.delivery_note for d in items if d.dn_detail in missing})]},
			fields=["name", "posting_date"], as_list=True)
	) if missing else {}

	data, stock_keys = [], set()
	for row in items:
		dns, source = find_delivery_notes(row, by_dn_detail, by_si_detail, by_si_item, by_so_detail, by_so_item)
		if not dns and row.delivery_note:
			dn_row = missing_dn_rows.get(row.dn_detail) or frappe._dict()
			dns = [frappe._dict(delivery_note=row.delivery_note,
				delivery_note_date=dn_row.delivery_note_date or missing_dn_dates.get(row.delivery_note),
				dn_detail=row.dn_detail, incoming_rate=None, qty=dn_row.qty, amount=dn_row.amount)]
			source = "Invoice Item"

		# Delivery Note's own qty / rate / amount, summed across every DN row matched to this line
		dn_qty = sum(flt(d.qty) for d in dns)
		dn_amount = sum(flt(d.amount) for d in dns)

		if row.update_stock:
			voucher_type, voucher_no, voucher_detail = "Sales Invoice", row.sales_invoice, row.si_detail
		elif dns:
			voucher_type, voucher_no, voucher_detail = "Delivery Note", dns[0].delivery_note, dns[0].dn_detail
		else:
			voucher_type = voucher_no = voucher_detail = None

		row.update(
			delivery_note=", ".join(dict.fromkeys(d.delivery_note for d in dns)) or None,
			delivery_note_date=min((d.delivery_note_date for d in dns if d.delivery_note_date), default=None),
			dn_source=source,
			dn_qty=dn_qty if dns else None,
			dn_amount=dn_amount if dns else None,
			dn_rate=(dn_amount / dn_qty if dn_qty else None) if dns else None,
			voucher_type=voucher_type,
			voucher_no=voucher_no,
			_voucher_detail=voucher_detail,
			_fallback_rate=(dns[0].incoming_rate if dns and not row.update_stock else row.incoming_rate),
		)
		if voucher_detail:
			stock_keys.add((voucher_no, voucher_detail))
		data.append(row)

	valuation = get_sle_valuation(stock_keys)
	for row in data:
		rate = valuation.get((row.voucher_no, row._voucher_detail))
		row.valuation_rate = flt(rate if rate is not None else row._fallback_rate)
		row.valuation_amount = flt(row.valuation_rate * flt(row.stock_qty or row.qty))
		for key in ("_voucher_detail", "_fallback_rate", "si_detail", "so_detail", "dn_detail",
				"incoming_rate", "update_stock", "stock_qty"):
			row.pop(key, None)
	return data


def find_delivery_notes(row, by_dn_detail, by_si_detail, by_si_item, by_so_detail, by_so_item):
	"""Invoice's own DN link first, then DNs made from the invoice, then DNs of its Sales Order."""
	if row.dn_detail and row.dn_detail in by_dn_detail:
		return [by_dn_detail[row.dn_detail]], "Invoice Item"
	if by_si_detail.get(row.si_detail):
		return by_si_detail[row.si_detail], "Invoice Connection"
	if by_si_item.get((row.sales_invoice, row.item_code)):
		return by_si_item[(row.sales_invoice, row.item_code)], "Invoice Connection"
	if row.sales_order:
		if row.so_detail and by_so_detail.get(row.so_detail):
			return by_so_detail[row.so_detail], "Sales Order"
		if by_so_item.get((row.sales_order, row.item_code)):
			return by_so_item[(row.sales_order, row.item_code)], "Sales Order"
	return [], None


def get_sle_valuation(keys):
	"""Actual valuation rate booked in the Stock Ledger for each voucher line."""
	if not keys:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT voucher_no, voucher_detail_no,
			SUM(stock_value_difference) AS value, SUM(actual_qty) AS qty,
			AVG(valuation_rate) AS valuation_rate
		FROM `tabStock Ledger Entry`
		WHERE is_cancelled = 0 AND voucher_no IN %(vouchers)s
		GROUP BY voucher_no, voucher_detail_no
		""",
		{"vouchers": list({k[0] for k in keys})},
		as_dict=True,
	)
	result = {}
	for r in rows:
		if (r.voucher_no, r.voucher_detail_no) in keys:
			# Outgoing rate = value moved / qty moved; fall back to running valuation rate
			result[(r.voucher_no, r.voucher_detail_no)] = (
				abs(flt(r.value) / flt(r.qty)) if flt(r.qty) else flt(r.valuation_rate)
			)
	return result
