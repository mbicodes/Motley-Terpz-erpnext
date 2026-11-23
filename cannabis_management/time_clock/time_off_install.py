"""after_migrate: the Full Time / Part Time field on Employee and one empty policy per category,
so HR only has to type the handbook's hours in."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def install():
	create_custom_fields({"Employee": [{
		"fieldname": "custom_time_off_category",
		"fieldtype": "Select",
		"options": "\nFull Time\nPart Time",
		"label": "Time Off Category",
		"insert_after": "status",
		"description": "Picks the PTO and Sick Time rules (Time Off Policy) for this employee",
	}]}, update=True)
	for category in ("Full Time", "Part Time"):
		if not frappe.db.exists("Time Off Policy", category):
			frappe.get_doc({"doctype": "Time Off Policy", "category": category}).insert(ignore_permissions=True)
