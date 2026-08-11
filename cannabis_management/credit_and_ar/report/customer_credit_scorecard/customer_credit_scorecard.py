"""Customer Credit Scorecard — the MD's single source of truth for approving
credit lines.

One row per customer: how they pay, what they buy, what they owe, and what
they are allowed to owe. Intercompany accounts are excluded throughout.
"""

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_and_ar import utils
from cannabis_management.credit_and_ar.report import report_utils

POUND_COMPANIES = utils.POUND_REPORTING_COMPANIES

SCORE_COLOURS = [
	(750, "green"),
	(700, "blue"),
	(650, "orange"),
	(600, "orange"),
	(0, "red"),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(filters), data, None, get_chart(data)


def get_data(filters):
	customers = frappe.get_all(
		"Customer",
		filters=report_utils.customer_filters(filters),
		fields=[
			"name",
			"customer_name",
			"customer_group",
			"custom_payment_score",
			"custom_score_band",
			"custom_avg_days_to_pay",
			"custom_on_time_percent",
			"custom_weekly_volume_g",
			"custom_weekly_volume_lbs",
			"custom_approved_credit_limit",
			"custom_credit_status",
			"custom_credit_terms_template",
			"custom_terms_valid_until",
			"custom_active_credit_application",
			"custom_credit_group_parent",
			"custom_hold_type",
		],
		order_by="custom_payment_score desc, name asc",
	)

	excluded = set(report_utils.excluded_customers())
	customers = [row for row in customers if row.name not in excluded]
	if not customers:
		return []

	names = [row.name for row in customers]
	ar = report_utils.ar_by_customer(company=filters.get("company"), customers=names)
	unbilled = report_utils.unbilled_terms_by_customer(names)
	paid_counts = _paid_invoice_counts(names)
	legal_names = _legal_buyer_names(names)

	# TSBC reports in pounds; Motley and Master Touch in grams. With no company
	# filter both columns are shown so the MD can compare like for like.
	company = filters.get("company")

	rows = []
	for customer in customers:
		bucket = ar.get(customer.name, {})
		outstanding = flt(bucket.get("outstanding"))
		exposure = outstanding + flt(unbilled.get(customer.name))
		limit = flt(customer.custom_approved_credit_limit)
		available = limit - exposure

		rows.append(
			{
				"customer": customer.name,
				"legal_buyer": legal_names.get(customer.name) or customer.customer_name,
				"score": report_utils.score_or_none(customer),
				"band": customer.custom_score_band or report_utils.NO_SCORE_BAND,
				"avg_days_to_pay": flt(customer.custom_avg_days_to_pay),
				"on_time_percent": flt(customer.custom_on_time_percent),
				"invoices_paid": paid_counts.get(customer.name, 0),
				"weekly_volume_lbs": flt(customer.custom_weekly_volume_lbs),
				"weekly_volume_g": flt(customer.custom_weekly_volume_g),
				"current_ar": outstanding,
				"past_due": flt(bucket.get("past_due")),
				"max_days_past_due": bucket.get("max_days") or 0,
				"approved_limit": limit,
				"exposure": exposure,
				"available_line": available,
				"utilisation": flt(exposure / limit * 100) if limit else 0.0,
				"credit_status": customer.custom_credit_status or utils.STATUS_COD,
				"hold_type": customer.custom_hold_type or utils.HOLD_NONE,
				"terms": customer.custom_credit_terms_template,
				"terms_valid_until": customer.custom_terms_valid_until,
				"credit_application": customer.custom_active_credit_application,
				"credit_group_parent": customer.custom_credit_group_parent,
			}
		)

	if filters.get("only_with_terms"):
		rows = [row for row in rows if row["terms"]]

	if company in POUND_COMPANIES:
		for row in rows:
			row["weekly_volume_g"] = None

	return rows


def _paid_invoice_counts(customers: list[str]) -> dict:
	rows = frappe.db.sql(
		"""
		SELECT customer, COUNT(*) AS paid
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND is_return = 0
		  AND outstanding_amount <= 0
		  AND IFNULL(custom_is_finance_charge, 0) = 0
		  AND customer IN %(customers)s
		GROUP BY customer
		""",
		{"customers": customers},
		as_dict=True,
	)
	return {row.customer: row.paid for row in rows}


def _legal_buyer_names(customers: list[str]) -> dict:
	"""The exact legal buyer from the live credit file, where there is one."""
	if not frappe.db.exists("DocType", "Credit Application"):
		return {}

	rows = frappe.get_all(
		"Credit Application",
		filters={"customer": ("in", customers), "docstatus": 1, "workflow_state": "Approved"},
		fields=["customer", "exact_legal_buyer"],
		order_by="modified desc",
	)
	result = {}
	for row in rows:
		result.setdefault(row.customer, row.exact_legal_buyer)
	return result


def get_chart(data):
	"""Score distribution — where the book actually sits."""
	if not data:
		return None

	bands = ["Excellent", "Good", "Fair", "Watch", "COD Only", report_utils.NO_SCORE_BAND]
	counts = {band: 0 for band in bands}
	for row in data:
		counts[row["band"]] = counts.get(row["band"], 0) + 1

	return {
		"data": {
			"labels": bands,
			"datasets": [{"name": _("Customers"), "values": [counts[band] for band in bands]}],
		},
		"type": "bar",
		"colors": ["#22c55e", "#3b82f6", "#f59e0b", "#f97316", "#ef4444", "#94a3b8"],
		"barOptions": {"stacked": 0},
	}


def get_columns(filters):
	company = filters.get("company")

	columns = [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
		 "options": "Customer", "width": 200},
		{"label": _("Legal Buyer"), "fieldname": "legal_buyer", "fieldtype": "Data", "width": 190},
		{"label": _("Score"), "fieldname": "score", "fieldtype": "Int", "width": 80},
		{"label": _("Band"), "fieldname": "band", "fieldtype": "Data", "width": 130},
		{"label": _("Avg Days to Pay"), "fieldname": "avg_days_to_pay", "fieldtype": "Float",
		 "precision": 1, "width": 130},
		{"label": _("On-Time %"), "fieldname": "on_time_percent", "fieldtype": "Percent",
		 "width": 100},
		{"label": _("Invoices Paid"), "fieldname": "invoices_paid", "fieldtype": "Int", "width": 110},
	]

	if company in POUND_COMPANIES or not company:
		columns.append(
			{"label": _("Weekly Volume (lbs)"), "fieldname": "weekly_volume_lbs",
			 "fieldtype": "Float", "precision": 2, "width": 150}
		)
	if company not in POUND_COMPANIES:
		columns.append(
			{"label": _("Weekly Volume (g)"), "fieldname": "weekly_volume_g",
			 "fieldtype": "Float", "precision": 2, "width": 150}
		)

	columns += [
		{"label": _("Current AR"), "fieldname": "current_ar", "fieldtype": "Currency", "width": 120},
		{"label": _("Past Due"), "fieldname": "past_due", "fieldtype": "Currency", "width": 120},
		{"label": _("Max Days Past Due"), "fieldname": "max_days_past_due", "fieldtype": "Int",
		 "width": 140},
		{"label": _("Approved Limit"), "fieldname": "approved_limit", "fieldtype": "Currency",
		 "width": 130},
		{"label": _("Exposure"), "fieldname": "exposure", "fieldtype": "Currency", "width": 120},
		{"label": _("Available Line"), "fieldname": "available_line", "fieldtype": "Currency",
		 "width": 130},
		{"label": _("Utilisation %"), "fieldname": "utilisation", "fieldtype": "Percent",
		 "width": 110},
		{"label": _("Credit Status"), "fieldname": "credit_status", "fieldtype": "Data",
		 "width": 120},
		{"label": _("Hold"), "fieldname": "hold_type", "fieldtype": "Data", "width": 110},
		{"label": _("Terms"), "fieldname": "terms", "fieldtype": "Link",
		 "options": "Payment Terms Template", "width": 130},
		{"label": _("Terms Valid Until"), "fieldname": "terms_valid_until", "fieldtype": "Date",
		 "width": 130},
		{"label": _("Credit Application"), "fieldname": "credit_application", "fieldtype": "Link",
		 "options": "Credit Application", "width": 170},
		{"label": _("Credit Group"), "fieldname": "credit_group_parent", "fieldtype": "Link",
		 "options": "Customer", "width": 160},
	]

	return columns
