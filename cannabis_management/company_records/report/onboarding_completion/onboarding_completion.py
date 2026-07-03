# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.utils import cint


def execute(filters=None):
	filters = frappe._dict(filters or {})

	conditions = ["1=1"]
	values = {}
	if filters.status:
		conditions.append("op.status = %(status)s")
		values["status"] = filters.status
	else:
		conditions.append("op.status != 'Complete'")
	if filters.business_entity:
		conditions.append("op.business_entity = %(business_entity)s")
		values["business_entity"] = filters.business_entity
	if filters.min_days_open:
		conditions.append("DATEDIFF(CURDATE(), op.date_submitted) >= %(min_days_open)s")
		values["min_days_open"] = cint(filters.min_days_open)

	columns = [
		{"fieldname": "name", "label": _("Packet"), "fieldtype": "Link", "options": "Onboarding Packet", "width": 160},
		{"fieldname": "client", "label": _("Client"), "fieldtype": "Data", "width": 170},
		{"fieldname": "business_entity", "label": _("Business Entity"), "fieldtype": "Link", "options": "Business Entity", "width": 160},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "date_submitted", "label": _("Date Submitted"), "fieldtype": "Date", "width": 110},
		{"fieldname": "days_open", "label": _("Days Since Submitted"), "fieldtype": "Int", "width": 130},
		{"fieldname": "docs_received", "label": _("Required Docs Received"), "fieldtype": "Data", "width": 140},
		{"fieldname": "missing_docs", "label": _("Missing"), "fieldtype": "Data", "width": 260},
	]

	data = frappe.db.sql(
		f"""
		SELECT op.name,
			COALESCE(NULLIF(op.client_name, ''), op.prospective_client_name) AS client,
			op.business_entity, op.status, op.date_submitted,
			DATEDIFF(CURDATE(), op.date_submitted) AS days_open,
			(SELECT COUNT(*) FROM `tabOnboarding Checklist Item` ci
				WHERE ci.parent = op.name AND ci.required = 1) AS total_required,
			(SELECT COUNT(*) FROM `tabOnboarding Checklist Item` ci
				WHERE ci.parent = op.name AND ci.required = 1 AND ci.received = 1) AS total_received
		FROM `tabOnboarding Packet` op
		WHERE {" AND ".join(conditions)}
		ORDER BY op.date_submitted ASC
		""",
		values,
		as_dict=True,
	)

	for row in data:
		row.docs_received = f"{cint(row.total_received)}/{cint(row.total_required)}"
		missing = frappe.get_all(
			"Onboarding Checklist Item",
			filters={"parent": row.name, "parenttype": "Onboarding Packet", "required": 1, "received": 0},
			pluck="document_name",
		)
		row.missing_docs = ", ".join(missing)
	return columns, data
