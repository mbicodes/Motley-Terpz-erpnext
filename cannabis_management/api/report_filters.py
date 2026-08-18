"""`All Company` support for report filters.

The custom reports each guard their company clause with `if filters.get("company")`,
so an absent company already means "every company". What was missing was a way
for a user to *say* that: a Link filter can only offer real Company records, and
clearing it looks like an unset filter rather than a deliberate choice.

The reports now offer an explicit `All Company` entry (see
`public/js/company_filter.js`). This strips that sentinel out of the filters
before the report body runs, so **no report's Python had to change** — each one's
existing "no company means all companies" branch does the work.

Wrapping the two whitelisted entry points rather than editing twelve reports
also means any report added later gets the behaviour for free.
"""

import json

import frappe
from frappe.desk.query_report import export_query as _original_export_query
from frappe.desk.query_report import run as _original_run

ALL_COMPANIES = "All Company"


def _strip(filters):
	"""Drop the sentinel wherever it appears, preserving the original type."""
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
		# Copy rather than mutate: the caller's dict may be reused (prepared
		# reports hand the same payload around).
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
	"""Exports read the filters straight off `frappe.form_dict`, so clean it there.

	Without this an export would still be scoped to one company while the screen
	showed every company — the kind of mismatch nobody checks until it is wrong.
	"""
	if frappe.form_dict.get("filters"):
		frappe.form_dict["filters"] = _strip(frappe.form_dict["filters"])

	return _original_export_query()
