"""Terms & Credit Line Register.

Every account that holds terms, with the paperwork behind it. If a line is live
but the agreement is not on file, this report is where that shows up.
"""

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_and_ar import utils
from cannabis_management.credit_and_ar.report import report_utils


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, get_message(data), get_chart(data)


def get_data(filters):
	if not frappe.db.exists("DocType", "Credit Application"):
		return []

	conditions = {"docstatus": 1, "workflow_state": "Approved"}
	if filters.get("customer"):
		conditions["customer"] = filters["customer"]

	applications = frappe.get_all(
		"Credit Application",
		filters=conditions,
		fields=[
			"name",
			"customer",
			"exact_legal_buyer",
			"approved_limit",
			"approved_terms",
			"agreement_signed_date",
			"credit_agreement_document",
			"onboarding_form_document",
			"onboarding_form_complete",
			"ap_contact_name",
			"ap_contact_phone",
			"ap_contact_email",
			"approved_by",
			"approved_on",
			"credit_group_parent",
		],
		order_by="approved_on desc",
	)

	excluded = set(report_utils.excluded_customers())
	applications = [row for row in applications if row.customer not in excluded]
	if not applications:
		return []

	customers = [row.customer for row in applications]
	ar = report_utils.ar_by_customer(customers=customers)
	unbilled = report_utils.unbilled_terms_by_customer(customers)

	rows = []
	for app in applications:
		bucket = ar.get(app.customer, {})
		exposure = flt(bucket.get("outstanding")) + flt(unbilled.get(app.customer))
		limit = flt(app.approved_limit)

		rows.append(
			{
				"customer": app.customer,
				"legal_buyer": app.exact_legal_buyer,
				"approved_limit": limit,
				"terms": app.approved_terms,
				"agreement_signed_date": app.agreement_signed_date,
				"agreement": report_utils.attachment_link(
					app.credit_agreement_document, _("Agreement")
				),
				"onboarding": report_utils.attachment_link(
					app.onboarding_form_document, _("Form")
				)
				or (_("Confirmed") if app.onboarding_form_complete else ""),
				"ap_contact_name": app.ap_contact_name,
				"ap_contact_phone": app.ap_contact_phone,
				"ap_contact_email": app.ap_contact_email,
				"exposure": exposure,
				"available_line": limit - exposure,
				"utilisation": flt(exposure / limit * 100) if limit else 0.0,
				"past_due": flt(bucket.get("past_due")),
				"approved_by": app.approved_by,
				"approved_on": app.approved_on,
				"credit_application": app.name,
				"credit_group_parent": app.credit_group_parent,
			}
		)

	return rows


def get_message(data):
	if not data:
		return _("No live credit lines. Every account is COD.")

	total_limit = sum(row["approved_limit"] for row in data)
	total_exposure = sum(row["exposure"] for row in data)

	parts = [
		_("<b>{0}</b> live credit line(s)").format(len(data)),
		_("total approved <b>{0}</b>").format(utils.fmt_currency(total_limit)),
		_("drawn <b>{0}</b>").format(utils.fmt_currency(total_exposure)),
	]

	return " &nbsp;·&nbsp; ".join(parts)


def get_chart(data):
	if not data:
		return None

	rows = sorted(data, key=lambda row: row["utilisation"], reverse=True)[:10]
	return {
		"data": {
			"labels": [row["customer"] for row in rows],
			"datasets": [
				{"name": _("Exposure"), "values": [row["exposure"] for row in rows]},
				{"name": _("Approved Limit"), "values": [row["approved_limit"] for row in rows]},
			],
		},
		"type": "bar",
		"colors": ["#f97316", "#3b82f6"],
	}


def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
		 "options": "Customer", "width": 190},
		{"label": _("Legal Buyer"), "fieldname": "legal_buyer", "fieldtype": "Data", "width": 190},
		{"label": _("Approved Limit"), "fieldname": "approved_limit", "fieldtype": "Currency",
		 "width": 130},
		{"label": _("Terms"), "fieldname": "terms", "fieldtype": "Link",
		 "options": "Payment Terms Template", "width": 130},
		{"label": _("Exposure"), "fieldname": "exposure", "fieldtype": "Currency", "width": 120},
		{"label": _("Available Line"), "fieldname": "available_line", "fieldtype": "Currency",
		 "width": 130},
		{"label": _("Utilisation %"), "fieldname": "utilisation", "fieldtype": "Percent",
		 "width": 110},
		{"label": _("Past Due"), "fieldname": "past_due", "fieldtype": "Currency", "width": 110},
		{"label": _("Signed"), "fieldname": "agreement_signed_date", "fieldtype": "Date",
		 "width": 110},
		{"label": _("Agreement"), "fieldname": "agreement", "fieldtype": "HTML", "width": 100},
		{"label": _("Onboarding"), "fieldname": "onboarding", "fieldtype": "HTML", "width": 110},
		{"label": _("AP Contact"), "fieldname": "ap_contact_name", "fieldtype": "Data",
		 "width": 150},
		{"label": _("AP Direct Line"), "fieldname": "ap_contact_phone", "fieldtype": "Data",
		 "width": 140},
		{"label": _("AP Email"), "fieldname": "ap_contact_email", "fieldtype": "Data",
		 "width": 200},
		{"label": _("Approved By"), "fieldname": "approved_by", "fieldtype": "Link",
		 "options": "User", "width": 160},
		{"label": _("Approved On"), "fieldname": "approved_on", "fieldtype": "Datetime",
		 "width": 160},
		{"label": _("Credit Application"), "fieldname": "credit_application", "fieldtype": "Link",
		 "options": "Credit Application", "width": 175},
	]
