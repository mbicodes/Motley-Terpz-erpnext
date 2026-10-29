import json

import frappe
from frappe.desk.query_report import export_query as _original_export_query
from frappe.desk.query_report import run as _original_run

ALL_COMPANIES = "All Company"


def _strip(filters):
	if not filters:
		return filters

	if isinstance(filters, str):
		try:
			parsed = json.loads(filters)
		except (ValueError, TypeError):
			return filters
		cleaned = _strip(parsed)
		return json.dumps(cleaned)

	if isinstance(filters, dict) and filters.get("company") == ALL_COMPANIES:
		cleaned = dict(filters)
		cleaned.pop("company", None)
		return cleaned

	return filters


@frappe.whitelist()
def run(
	report_name,
	filters=None,
	user=None,
	ignore_prepared_report=False,
	custom_columns=None,
	is_tree=False,
	parent_field=None,
	are_default_filters=True,
):
	return _original_run(
		report_name,
		filters=_strip(filters),
		user=user,
		ignore_prepared_report=ignore_prepared_report,
		custom_columns=custom_columns,
		is_tree=is_tree,
		parent_field=parent_field,
		are_default_filters=are_default_filters,
	)


@frappe.whitelist()
def export_query():
	if frappe.form_dict.get("filters"):
		frappe.form_dict["filters"] = _strip(frappe.form_dict["filters"])

	return _original_export_query()
