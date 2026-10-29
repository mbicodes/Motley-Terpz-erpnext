from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

JOB_CARD_FIELDS = [
	{
		"fieldname": "custom_material_request",
		"fieldtype": "Link",
		"label": "Material Request",
		"options": "Material Request",
		"insert_after": "work_order",
		"fetch_from": "work_order.material_request",
		"read_only": 1,
		"no_copy": 1,
		"description": (
			"The Material Request this card's Work Order was raised against. "
			"Set automatically from the Work Order."
		),
	},
]


def get_data(data):
	for section in data.get("transactions", []):
		if section.get("label") == _("Manufacturing"):
			if "Job Card" not in section["items"]:
				section["items"].append("Job Card")
			break

	non_standard = data.setdefault("non_standard_fieldnames", {})
	non_standard["Job Card"] = "custom_material_request"

	return data


def install():
	create_custom_fields({"Job Card": JOB_CARD_FIELDS}, ignore_validate=True)
	return backfill()


def backfill():
	import frappe

	rows = frappe.db.sql(
		"""
		select jc.name, wo.material_request
		from `tabJob Card` jc
		inner join `tabWork Order` wo on wo.name = jc.work_order
		where ifnull(wo.material_request, '') != ''
		  and ifnull(jc.custom_material_request, '') != wo.material_request
		""",
		as_dict=True,
	)
	for row in rows:
		frappe.db.set_value(
			"Job Card",
			row.name,
			"custom_material_request",
			row.material_request,
			update_modified=False,
		)
	return len(rows)
