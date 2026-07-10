# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import flt

ALLOWED_ROLES = {"System Manager", "Director", "Accounting Team", "Super Admin"}


def _check_access():
	if not ALLOWED_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_model():
	"""Return the saved input set (or None so the client seeds defaults)."""
	_check_access()
	raw = frappe.db.get_single_value("Unit Economics Model", "inputs_json")
	return json.loads(raw) if raw else None


@frappe.whitelist()
def save_model(inputs):
	_check_access()
	if isinstance(inputs, str):
		inputs = json.loads(inputs)  # validate it parses
	doc = frappe.get_doc("Unit Economics Model")
	doc.inputs_json = json.dumps(inputs, indent=1)
	doc.save(ignore_permissions=True)
	return {"saved": True, "modified": str(doc.modified)}


@frappe.whitelist()
def erp_snapshot(from_date=None):
	"""Live ERP numbers for comparison against the model's blue cells.

	Grouped by Company so Matt can eyeball each segment's inputs against
	what ERPNext actually has booked. from_date defaults to Oct 1, 2025
	(the model period start).
	"""
	_check_access()
	from_date = from_date or "2025-10-01"

	snapshot = {"from_date": from_date, "companies": {}}

	def bucket(company):
		return snapshot["companies"].setdefault(company, {
			"booked_revenue": 0, "ar_outstanding": 0, "ap_outstanding": 0,
			"inventory_value": 0, "customer_deposits": 0,
		})

	for row in frappe.db.sql(
		"""SELECT company, SUM(base_net_total) AS revenue
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND is_return = 0 AND posting_date >= %(from_date)s
		GROUP BY company""",
		{"from_date": from_date}, as_dict=True,
	):
		bucket(row.company)["booked_revenue"] = flt(row.revenue, 2)

	for row in frappe.db.sql(
		"""SELECT company, SUM(outstanding_amount) AS outstanding
		FROM `tabSales Invoice`
		WHERE docstatus = 1 AND outstanding_amount > 0.01
		GROUP BY company""",
		as_dict=True,
	):
		bucket(row.company)["ar_outstanding"] = flt(row.outstanding, 2)

	for row in frappe.db.sql(
		"""SELECT company, SUM(outstanding_amount) AS outstanding
		FROM `tabPurchase Invoice`
		WHERE docstatus = 1 AND outstanding_amount > 0.01
		GROUP BY company""",
		as_dict=True,
	):
		bucket(row.company)["ap_outstanding"] = flt(row.outstanding, 2)

	for row in frappe.db.sql(
		"""SELECT w.company, SUM(b.stock_value) AS stock_value
		FROM `tabBin` b
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE b.stock_value > 0
		GROUP BY w.company""",
		as_dict=True,
	):
		bucket(row.company)["inventory_value"] = flt(row.stock_value, 2)

	# unallocated advances received from customers (pre-sold product deposits)
	for row in frappe.db.sql(
		"""SELECT company, SUM(unallocated_amount) AS advances
		FROM `tabPayment Entry`
		WHERE docstatus = 1 AND party_type = 'Customer'
			AND payment_type = 'Receive' AND unallocated_amount > 0.01
		GROUP BY company""",
		as_dict=True,
	):
		bucket(row.company)["customer_deposits"] = flt(row.advances, 2)

	totals = {k: 0 for k in
	          ("booked_revenue", "ar_outstanding", "ap_outstanding", "inventory_value", "customer_deposits")}
	for values in snapshot["companies"].values():
		for key in totals:
			totals[key] += values[key]
	snapshot["totals"] = {k: flt(v, 2) for k, v in totals.items()}
	return snapshot
