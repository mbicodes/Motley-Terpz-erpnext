# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _

# Stock Entry purposes that only move stock between warehouses inside the
# same company — not a real outward movement, so excluded from this report.
INTERNAL_TRANSFER_PURPOSES = ("Material Transfer", "Material Transfer for Manufacture")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Posting Time"), "fieldname": "posting_time", "fieldtype": "Time", "width": 90},
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 140},
		{"label": _("Batch No"), "fieldname": "batch_no", "fieldtype": "Data", "width": 110},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 130},
		{"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 160},
		{"label": _("Qty Out"), "fieldname": "qty_out", "fieldtype": "Float", "width": 100},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 80},
		{"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 110},
		{"label": _("Value Out"), "fieldname": "value_out", "fieldtype": "Currency", "options": "Company:company:default_currency", "width": 120},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
	]


def get_data(filters):
	conditions, values = get_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			sle.posting_date, sle.posting_time,
			sle.item_code, it.item_name,
			sle.warehouse, sle.batch_no,
			sle.voucher_type, sle.voucher_no,
			ABS(sle.actual_qty) AS qty_out,
			sle.stock_uom,
			sle.valuation_rate,
			ABS(sle.stock_value_difference) AS value_out,
			sle.company
		FROM `tabStock Ledger Entry` sle
		LEFT JOIN `tabItem` it ON it.name = sle.item_code
		LEFT JOIN `tabStock Entry` se ON se.name = sle.voucher_no AND sle.voucher_type = 'Stock Entry'
		WHERE sle.is_cancelled = 0
			AND sle.actual_qty < 0
			AND (se.name IS NULL OR se.purpose NOT IN %(internal_transfer_purposes)s)
			{conditions}
		ORDER BY sle.posting_date DESC, sle.posting_time DESC
		""",
		{**values, "internal_transfer_purposes": INTERNAL_TRANSFER_PURPOSES},
		as_dict=True,
	)


def get_conditions(filters):
	conditions = []
	values = {}

	if filters.get("company"):
		conditions.append("AND sle.company = %(company)s")
		values["company"] = filters.company

	if filters.get("from_date"):
		conditions.append("AND sle.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append("AND sle.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	if filters.get("item_code"):
		conditions.append("AND sle.item_code = %(item_code)s")
		values["item_code"] = filters.item_code

	if filters.get("warehouse"):
		conditions.append("AND sle.warehouse = %(warehouse)s")
		values["warehouse"] = filters.warehouse

	if filters.get("voucher_type"):
		conditions.append("AND sle.voucher_type = %(voucher_type)s")
		values["voucher_type"] = filters.voucher_type

	return "\n\t\t\t".join(conditions), values
