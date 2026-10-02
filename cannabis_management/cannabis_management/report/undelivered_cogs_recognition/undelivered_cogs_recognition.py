# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from cannabis_management.api.undelivered_cogs import get_lines


def execute(filters=None):
	filters = frappe._dict(filters or {})
	lines = get_lines(filters.company, filters.from_date, filters.to_date)
	if filters.only_gaps:
		lines = [l for l in lines if l.status != "Fully Covered"]
	return get_columns(), lines


def get_columns():
	return [
		{"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 160},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 140},
		{"label": _("Update Stock"), "fieldname": "update_stock", "fieldtype": "Check", "width": 70},
		{"label": _("Invoiced Qty"), "fieldname": "invoiced_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Delivered Qty"), "fieldname": "delivered_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Delivered Through"), "fieldname": "delivery_source", "fieldtype": "Data", "width": 200},
		{"label": _("Already Posted Qty"), "fieldname": "recognized_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Undelivered Qty"), "fieldname": "remaining_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Currency", "width": 100},
		{"label": _("Rate Source"), "fieldname": "rate_source", "fieldtype": "Data", "width": 200},
		{"label": _("COGS To Post"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("COGS Account"), "fieldname": "cogs_account", "fieldtype": "Link", "options": "Account", "width": 180},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
	]
