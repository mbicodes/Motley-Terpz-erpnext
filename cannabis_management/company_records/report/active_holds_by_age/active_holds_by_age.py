# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt


import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})

	conditions = ["loi.status = %(status)s"]
	values = {"status": filters.status or "Active Hold"}
	if filters.business_entity:
		conditions.append("loi.business_entity = %(business_entity)s")
		values["business_entity"] = filters.business_entity
	if filters.min_days_held:
		conditions.append("DATEDIFF(CURDATE(), loi.hold_start_date) >= %(min_days_held)s")
		values["min_days_held"] = frappe.utils.cint(filters.min_days_held)

	columns = [
		{"fieldname": "name", "label": _("LOI / Hold"), "fieldtype": "Link", "options": "LOI Product Hold Agreement", "width": 160},
		{"fieldname": "counterparty", "label": _("Counterparty"), "fieldtype": "Data", "width": 160},
		{"fieldname": "business_entity", "label": _("Business Entity"), "fieldtype": "Link", "options": "Business Entity", "width": 160},
		{"fieldname": "material_or_product", "label": _("Material / Product"), "fieldtype": "Data", "width": 180},
		{"fieldname": "quantity", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "unit", "label": _("Unit"), "fieldtype": "Data", "width": 60},
		{"fieldname": "hold_start_date", "label": _("Hold Start"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_held", "label": _("Days Held"), "fieldtype": "Int", "width": 90},
		{"fieldname": "expected_fulfillment_date", "label": _("Expected Fulfillment"), "fieldtype": "Date", "width": 130},
	]

	data = frappe.db.sql(
		f"""
		SELECT loi.name, loi.counterparty, loi.business_entity, loi.material_or_product,
			loi.quantity, loi.unit, loi.hold_start_date,
			DATEDIFF(CURDATE(), loi.hold_start_date) AS days_held,
			loi.expected_fulfillment_date
		FROM `tabLOI Product Hold Agreement` loi
		WHERE {" AND ".join(conditions)}
		ORDER BY loi.hold_start_date ASC
		""",
		values,
		as_dict=True,
	)
	return columns, data
