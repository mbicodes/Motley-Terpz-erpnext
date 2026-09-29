"""Shared test helpers.

The tests run against a copy of production where the companies' real
Dispatch Company Settings records exist. Every test that replaces one takes a
snapshot first and puts the original back afterwards -- never just deletes it.
"""

import copy

import frappe

CHILD_TABLES = ("Dispatch Team Member", "Dispatch Reminder Rule")


def snapshot_settings(companies):
	snap = {}
	for company in companies:
		if frappe.db.exists("Dispatch Company Settings", company):
			snap[company] = copy.deepcopy(frappe.get_doc("Dispatch Company Settings", company).as_dict())
	return snap


def restore_settings(snap, companies):
	for company in companies:
		frappe.db.delete("Dispatch Company Settings", {"company": company})
		for child in CHILD_TABLES:
			frappe.db.delete(child, {"parent": company, "parenttype": "Dispatch Company Settings"})
		if company in snap:
			doc = frappe.get_doc(snap[company])
			doc.flags.ignore_validate = True
			doc.db_insert()
			for row in doc.get_all_children():
				row.db_insert()
	frappe.local.mt_dispatch_cfg = {}
	frappe.clear_document_cache("Dispatch Company Settings")


def existing_log_rows(sales_order):
	return set(frappe.get_all("Dispatch Stage Log", filters={"parent": sales_order, "parenttype": "Sales Order"}, pluck="name"))


def delete_new_log_rows(sales_order, keep):
	"""Remove only the stage log rows a test added. A real order's own
	history is never touched."""
	for name in existing_log_rows(sales_order) - set(keep or ()):
		frappe.db.delete("Dispatch Stage Log", {"name": name})
