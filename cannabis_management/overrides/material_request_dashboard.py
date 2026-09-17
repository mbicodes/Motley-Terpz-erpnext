"""Job Card on the Material Request Connections tab.

A Job Card has no link to a Material Request. It hangs off a Work Order, and it is
the Work Order that carries `material_request`. Frappe's Connections tab can only
count and filter on a field stored on the linked doctype itself, so a two-hop
MR -> Work Order -> Job Card lookup is not something the dashboard can express.

So we give Job Card the missing hop as a stored field: `custom_material_request`,
fetched from `work_order.material_request`. The dashboard then works through the
ordinary `non_standard_fieldnames` mechanism, the same way `sales_order_dashboard`
points Stock Entry at `custom_sales_order`.

Both halves are re-applied from `after_migrate` (see hooks.py): `install()` creates
the field idempotently and backfills Job Cards that predate it -- including submitted
and completed ones, which are never re-saved and so would never trigger the fetch.
"""

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
	# Job Card sits alongside Work Order in the Manufacturing group.
	for section in data.get("transactions", []):
		if section.get("label") == _("Manufacturing"):
			if "Job Card" not in section["items"]:
				section["items"].append("Job Card")
			break

	# Job Card has no `material_request` field -- look it up via the fetched one.
	non_standard = data.setdefault("non_standard_fieldnames", {})
	non_standard["Job Card"] = "custom_material_request"

	return data


def install():
	create_custom_fields({"Job Card": JOB_CARD_FIELDS}, ignore_validate=True)
	return backfill()


def backfill():
	"""Fill custom_material_request on Job Cards that predate the field.

	Direct db updates rather than doc.save(): the target rows are mostly submitted,
	and this field carries no stock or accounting meaning -- it only drives the
	Connections tab. Cards whose Work Order has no Material Request are left alone.
	"""
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
