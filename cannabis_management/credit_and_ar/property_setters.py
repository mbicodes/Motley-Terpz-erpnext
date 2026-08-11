"""Property Setters for the Sales Order gate.

Two jobs:

1. Make the payment mode mandatory, so no Sales Order can be saved without
   declaring whether it is COD or Terms.
2. Put ``payment_terms_template`` and ``payment_schedule`` behind **permlevel 1**
   so Sales cannot set a customer's terms (§1). Only Credit Finance and the
   Managing Director hold permlevel 1.
"""

import frappe

from cannabis_management.credit_and_ar import utils

PROPERTY_SETTERS = [
	# ── payment mode: mandatory, defaults to COD ─────────────────────────
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "custom_mode_of_payment",
		"property": "reqd",
		"property_type": "Check",
		"value": "1",
	},
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "custom_mode_of_payment",
		"property": "default",
		"property_type": "Text",
		"value": utils.MODE_COD,
	},
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "custom_mode_of_payment",
		"property": "in_standard_filter",
		"property_type": "Check",
		"value": "1",
	},
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "custom_mode_of_payment",
		"property": "in_list_view",
		"property_type": "Check",
		"value": "1",
	},
	# ── approval status: add "Not Required" to the existing options ──────
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "custom_approval_status",
		"property": "options",
		"property_type": "Text",
		"value": "\nNot Required\nPending Approval\nApproved\nRejected",
	},
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "custom_approval_status",
		"property": "in_standard_filter",
		"property_type": "Check",
		"value": "1",
	},
	# ── terms behind permlevel 1 ─────────────────────────────────────────
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "payment_terms_template",
		"property": "permlevel",
		"property_type": "Int",
		"value": "1",
	},
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "payment_terms_template",
		"property": "depends_on",
		"property_type": "Data",
		"value": f"eval:doc.custom_mode_of_payment=='{utils.MODE_TERMS}'",
	},
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "payment_terms_template",
		"property": "mandatory_depends_on",
		"property_type": "Data",
		"value": f"eval:doc.custom_mode_of_payment=='{utils.MODE_TERMS}'",
	},
	{
		"doctype_or_field": "DocField",
		"doc_type": "Sales Order",
		"field_name": "payment_schedule",
		"property": "permlevel",
		"property_type": "Int",
		"value": "1",
	},
]


def install_property_setters():
	for spec in PROPERTY_SETTERS:
		name = frappe.db.get_value(
			"Property Setter",
			{
				"doc_type": spec["doc_type"],
				"field_name": spec["field_name"],
				"property": spec["property"],
			},
			"name",
		)
		if name:
			frappe.db.set_value("Property Setter", name, "value", spec["value"])
			continue

		frappe.get_doc({"doctype": "Property Setter", **spec}).insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Sales Order")
