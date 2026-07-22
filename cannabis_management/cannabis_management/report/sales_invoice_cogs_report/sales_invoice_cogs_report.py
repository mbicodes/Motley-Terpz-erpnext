# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 180},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Data", "width": 200},
		{"label": _("Receivable Account"), "fieldname": "receivable_account", "fieldtype": "Data", "width": 200},
		{"label": _("COGS Account"), "fieldname": "cogs_account", "fieldtype": "Data", "width": 300},
		{"label": _("COGS Amount"), "fieldname": "cogs_amount", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 120},
		{"label": _("Invoice Amount"), "fieldname": "invoice_amount", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 120},
		{"label": _("Stock Updated Directly"), "fieldname": "update_stock", "fieldtype": "Check", "width": 90},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	return frappe.db.sql(
		"""
		SELECT
			si.customer AS customer,
			si.customer_name AS customer_name,
			si.company AS company,
			si.name AS sales_invoice,
			si.posting_date AS posting_date,
			NULLIF(CONCAT_WS(', ',
				-- SI created FROM a Delivery Note (link stored on the invoice item)
				(
					SELECT GROUP_CONCAT(DISTINCT sii.delivery_note SEPARATOR ', ')
					FROM `tabSales Invoice Item` sii
					WHERE sii.parent = si.name
						AND sii.delivery_note IS NOT NULL
						AND sii.delivery_note != ''
				),
				-- Delivery Note created FROM this SI (shown in the invoice's Connections tab)
				(
					SELECT GROUP_CONCAT(DISTINCT dni.parent SEPARATOR ', ')
					FROM `tabDelivery Note Item` dni
					INNER JOIN `tabDelivery Note` dnote
						ON dnote.name = dni.parent AND dnote.docstatus = 1
					WHERE dni.against_sales_invoice = si.name
				)
			), '') AS delivery_note,
			si.debit_to AS receivable_account,
			(
				SELECT GROUP_CONCAT(DISTINCT CONCAT(gle.account,
					CASE WHEN gle.voucher_type = 'Delivery Note' THEN CONCAT(' (', gle.voucher_no, ')') ELSE '' END
				) SEPARATOR ' | ')
				FROM `tabGL Entry` gle
				WHERE gle.is_cancelled = 0
					AND gle.debit > 0
					AND (
						(gle.voucher_type = 'Sales Invoice' AND gle.voucher_no = si.name AND si.update_stock = 1
							AND gle.account != si.debit_to)
						OR (gle.voucher_type = 'Delivery Note' AND si.update_stock = 0 AND gle.voucher_no IN (
							SELECT sii2.delivery_note
							FROM `tabSales Invoice Item` sii2
							WHERE sii2.parent = si.name
								AND sii2.delivery_note IS NOT NULL
								AND sii2.delivery_note != ''
							UNION
							SELECT dni2.parent
							FROM `tabDelivery Note Item` dni2
							WHERE dni2.against_sales_invoice = si.name
						))
					)
			) AS cogs_account,
			(
				SELECT COALESCE(SUM(gle.debit), 0)
				FROM `tabGL Entry` gle
				WHERE gle.is_cancelled = 0
					AND gle.debit > 0
					AND (
						(gle.voucher_type = 'Sales Invoice' AND gle.voucher_no = si.name AND si.update_stock = 1
							AND gle.account != si.debit_to)
						OR (gle.voucher_type = 'Delivery Note' AND si.update_stock = 0 AND gle.voucher_no IN (
							SELECT sii3.delivery_note
							FROM `tabSales Invoice Item` sii3
							WHERE sii3.parent = si.name
								AND sii3.delivery_note IS NOT NULL
								AND sii3.delivery_note != ''
							UNION
							SELECT dni3.parent
							FROM `tabDelivery Note Item` dni3
							WHERE dni3.against_sales_invoice = si.name
						))
					)
			) AS cogs_amount,
			si.grand_total AS invoice_amount,
			si.update_stock AS update_stock,
			si.status AS status
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
			AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		ORDER BY si.customer ASC, si.posting_date ASC
		""",
		{
			"company": filters.get("company"),
			"from_date": filters.get("from_date"),
			"to_date": filters.get("to_date"),
		},
		as_dict=True,
	)
