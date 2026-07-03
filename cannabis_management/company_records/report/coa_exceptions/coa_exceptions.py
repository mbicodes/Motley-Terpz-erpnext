# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt


import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})

	conditions = []
	values = {}
	if filters.result_status:
		conditions.append("coa.result_status = %(result_status)s")
		values["result_status"] = filters.result_status
	else:
		conditions.append("coa.result_status IN ('Fail', 'Pending')")
	if filters.business_entity:
		conditions.append("coa.business_entity = %(business_entity)s")
		values["business_entity"] = filters.business_entity
	if filters.product_category:
		conditions.append("coa.product_category = %(product_category)s")
		values["product_category"] = filters.product_category
	if filters.from_date:
		conditions.append("coa.sample_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.to_date:
		conditions.append("coa.sample_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	columns = [
		{"fieldname": "product_category", "label": _("Product Category"), "fieldtype": "Data", "width": 130},
		{"fieldname": "name", "label": _("COA"), "fieldtype": "Link", "options": "Certificate of Analysis", "width": 160},
		{"fieldname": "product_name", "label": _("Product"), "fieldtype": "Data", "width": 170},
		{"fieldname": "batch_or_sku", "label": _("Batch / SKU"), "fieldtype": "Data", "width": 140},
		{"fieldname": "test_type", "label": _("Test Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "testing_lab", "label": _("Testing Lab"), "fieldtype": "Data", "width": 130},
		{"fieldname": "result_status", "label": _("Result"), "fieldtype": "Data", "width": 100},
		{"fieldname": "sample_date", "label": _("Sample Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "result_date", "label": _("Result Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "business_entity", "label": _("Business Entity"), "fieldtype": "Link", "options": "Business Entity", "width": 150},
	]

	data = frappe.db.sql(
		f"""
		SELECT coa.product_category, coa.name, coa.product_name, coa.batch_or_sku,
			coa.test_type, coa.testing_lab, coa.result_status, coa.sample_date,
			coa.result_date, coa.business_entity
		FROM `tabCertificate of Analysis` coa
		WHERE {" AND ".join(conditions)}
		ORDER BY coa.product_category ASC, coa.result_status ASC, coa.sample_date ASC
		""",
		values,
		as_dict=True,
	)
	return columns, data
