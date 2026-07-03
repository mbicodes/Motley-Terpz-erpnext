# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt


import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})

	conditions = ["rr.status != 'Locked'"]
	values = {}
	if filters.business_entity:
		conditions.append("rr.business_entity = %(business_entity)s")
		values["business_entity"] = filters.business_entity
	if filters.reconciliation_type:
		conditions.append("rr.reconciliation_type = %(reconciliation_type)s")
		values["reconciliation_type"] = filters.reconciliation_type
	if filters.status:
		conditions.append("rr.status = %(status)s")
		values["status"] = filters.status
	if filters.from_date:
		conditions.append("rr.period_end >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.to_date:
		conditions.append("rr.period_end <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.only_with_variance:
		conditions.append("rr.variance != 0")

	columns = [
		{"fieldname": "name", "label": _("Reconciliation"), "fieldtype": "Link", "options": "Reconciliation Record", "width": 170},
		{"fieldname": "reconciliation_type", "label": _("Type"), "fieldtype": "Data", "width": 150},
		{"fieldname": "business_entity", "label": _("Business Entity"), "fieldtype": "Link", "options": "Business Entity", "width": 160},
		{"fieldname": "counterparty", "label": _("Counterparty"), "fieldtype": "Data", "width": 150},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "period_end", "label": _("Period End"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_open", "label": _("Days Since Period End"), "fieldtype": "Int", "width": 110},
		{"fieldname": "source_balance", "label": _("Source Balance"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "target_balance", "label": _("Target Balance"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Currency", "width": 130},
	]

	data = frappe.db.sql(
		f"""
		SELECT rr.name, rr.reconciliation_type, rr.business_entity, rr.counterparty,
			rr.status, rr.period_end, DATEDIFF(CURDATE(), rr.period_end) AS days_open,
			rr.source_balance, rr.target_balance, rr.variance
		FROM `tabReconciliation Record` rr
		WHERE {" AND ".join(conditions)}
		ORDER BY rr.period_end ASC
		""",
		values,
		as_dict=True,
	)
	return columns, data
