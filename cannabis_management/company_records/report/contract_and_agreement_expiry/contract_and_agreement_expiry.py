# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt


import frappe
from frappe import _
from frappe.utils import cint


def execute(filters=None):
	filters = frappe._dict(filters or {})
	window = cint(filters.expiring_within) or 90

	columns = [
		{"fieldname": "record_type", "label": _("Record Type"), "fieldtype": "Data", "width": 140},
		{"fieldname": "record", "label": _("Record"), "fieldtype": "Dynamic Link", "options": "record_type", "width": 170},
		{"fieldname": "detail", "label": _("Type / Fee Structure"), "fieldtype": "Data", "width": 130},
		{"fieldname": "counterparty", "label": _("Counterparty / Partner"), "fieldtype": "Data", "width": 170},
		{"fieldname": "business_entity", "label": _("Business Entity"), "fieldtype": "Link", "options": "Business Entity", "width": 160},
		{"fieldname": "expires_on", "label": _("Expires On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_to_expiry", "label": _("Days to Expiry"), "fieldtype": "Int", "width": 110},
		{"fieldname": "bucket", "label": _("Bucket"), "fieldtype": "Data", "width": 100},
	]

	values = {"window": window}
	status_cond = "cc.status != 'Terminated'" if filters.include_expired else "cc.status NOT IN ('Expired', 'Terminated')"

	contract_conditions = [status_cond,
		"cc.expiry_date <= DATE_ADD(CURDATE(), INTERVAL %(window)s DAY)"]
	if not filters.include_expired:
		contract_conditions.append("cc.expiry_date >= CURDATE()")
	if filters.business_entity:
		contract_conditions.append("cc.business_entity = %(business_entity)s")
		values["business_entity"] = filters.business_entity
	if filters.contract_type:
		contract_conditions.append("cc.contract_type = %(contract_type)s")
		values["contract_type"] = filters.contract_type

	data = frappe.db.sql(
		f"""
		SELECT 'Company Contract' AS record_type, cc.name AS record,
			cc.contract_type AS detail, cc.counterparty, cc.business_entity,
			cc.expiry_date AS expires_on,
			DATEDIFF(cc.expiry_date, CURDATE()) AS days_to_expiry
		FROM `tabCompany Contract` cc
		WHERE {" AND ".join(contract_conditions)}
		""",
		values,
		as_dict=True,
	)

	# Tolling agreements have no contract_type; skip them when that filter is set
	if cint(filters.include_tolling if filters.include_tolling is not None else 1) and not filters.contract_type:
		tolling_conditions = ["ta.active_to <= DATE_ADD(CURDATE(), INTERVAL %(window)s DAY)"]
		if not filters.include_expired:
			tolling_conditions.append("ta.active_to >= CURDATE()")
		if filters.business_entity:
			tolling_conditions.append("ta.business_entity = %(business_entity)s")
		data += frappe.db.sql(
			f"""
			SELECT 'Tolling Agreement' AS record_type, ta.name AS record,
				ta.fee_structure AS detail, ta.tolling_partner AS counterparty,
				ta.business_entity, ta.active_to AS expires_on,
				DATEDIFF(ta.active_to, CURDATE()) AS days_to_expiry
			FROM `tabTolling Agreement` ta
			WHERE {" AND ".join(tolling_conditions)}
			""",
			values,
			as_dict=True,
		)

	for row in data:
		days = cint(row.days_to_expiry)
		if days < 0:
			row.bucket = _("Overdue")
		elif days <= 30:
			row.bucket = _("0-30 Days")
		elif days <= 60:
			row.bucket = _("31-60 Days")
		elif days <= 90:
			row.bucket = _("61-90 Days")
		else:
			row.bucket = _("90+ Days")

	data.sort(key=lambda row: cint(row.days_to_expiry))
	return columns, data
