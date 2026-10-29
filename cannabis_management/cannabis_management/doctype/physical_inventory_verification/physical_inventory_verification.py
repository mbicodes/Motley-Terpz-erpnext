import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PhysicalInventoryVerification(Document):
	pass


@frappe.whitelist()
def get_rosin_recording_data(tolling_partner, batch):
	if not tolling_partner or not batch:
		return []

	rosin_docs = frappe.get_all(
		"Rosin Recording",
		filters={
			"tolling_partner": tolling_partner,
			"batch": batch,
			"docstatus": 1
		},
		pluck="name"
	)

	if not rosin_docs:
		return []

	results = []
	for doc_name in rosin_docs:
		child_rows = frappe.get_all(
			"Lab Tolling Data",
			filters={"parent": doc_name},
			fields=[
				"prime_strain",
				"subprime_strain",
				"subprime_total_tolled",
				"prime_inventory_total_tolled"
			]
		)
		for row in child_rows:
			results.append({
				"prime_strain": row.get("prime_strain"),
				"subprime_strain": row.get("subprime_strain"),
				"subprime_total_tolled": flt(row.get("subprime_total_tolled")),
				"prime_inventory_total_tolled": flt(row.get("prime_inventory_total_tolled")),
			})

	return results
