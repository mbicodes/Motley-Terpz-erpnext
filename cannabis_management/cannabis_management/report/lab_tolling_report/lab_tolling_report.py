import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	report_summary = get_report_summary(data)
	return columns, data, None, None, report_summary


def get_columns():
	return [
		{
			"label": _("ID"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Rosin Recording",
			"width": 120
		},
		{
			"label": _("Tolling Partner"),
			"fieldname": "tolling_partner",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 150
		},
		{
			"label": _("Batch (Parent)"),
			"fieldname": "batch",
			"fieldtype": "Link",
			"options": "Project",
			"width": 120
		},
		{
			"label": _("Date Transferred"),
			"fieldname": "date_transferred",
			"fieldtype": "Date",
			"width": 110
		},
		{
			"label": _("Strain Name"),
			"fieldname": "strain_name",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130
		},
		{
			"label": _("Batch No (Child)"),
			"fieldname": "batch_no",
			"fieldtype": "Link",
			"options": "Project",
			"width": 120
		},
		{
			"label": _("Yield to Hash"),
			"fieldname": "yield_to_hash",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Pounds Sent"),
			"fieldname": "pounds_sent",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Pounds Ran"),
			"fieldname": "pounds_ran",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Source Bloom"),
			"fieldname": "source_bloom",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 120
		},
		# {
		# 	"label": _("Rosin Yield %"),
		# 	"fieldname": "rosin_yield_",
		# 	"fieldtype": "Percent",
		# 	"width": 100
		# },
		{
			"label": _("Run For"),
			"fieldname": "run_for",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 120
		},
		{
			"label": _("Amount Ran Grams"),
			"fieldname": "amount_ran_grams",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": _("Hash to Rosin %"),
			"fieldname": "hash_to_rosin_",
			"fieldtype": "Percent",
			"width": 120
		},
		{
			"label": _("150u Hash"),
			"fieldname": "150u_hash",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("120u Hash"),
			"fieldname": "120u_hash",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("90u Hash"),
			"fieldname": "90u_hash",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("73u Hash"),
			"fieldname": "73u_hash",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("45u Hash"),
			"fieldname": "45u_hash",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("25u Hash Copy"),
			"fieldname": "25u_hash_copy",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Total Hash"),
			"fieldname": "total_hash",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("150u Rosin"),
			"fieldname": "150u_rosin",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("120u Rosin"),
			"fieldname": "120u_rosin",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("90u Rosin"),
			"fieldname": "90u_rosin",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("73u Rosin"),
			"fieldname": "73u_rosin",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("45u Rosin"),
			"fieldname": "45u_rosin",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("25u Rosin"),
			"fieldname": "25u_rosin",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Total Rosin"),
			"fieldname": "total_rosin",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Subprime Total Tolled"),
			"fieldname": "subprime_total_tolled",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Prime Inventory Total Tolled"),
			"fieldname": "prime_inventory_total_tolled",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": _("Live Resin Produced"),
			"fieldname": "live_resin_produced",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Yield %"),
			"fieldname": "yield_",
			"fieldtype": "Percent",
			"width": 100
		},
		{
			"label": _("Actual Rosin Yield"),
			"fieldname": "actual_rosin_yield",
			"fieldtype": "Percent",
			"width": 130
		},
		{
			"label": _("Expected Rosin Yield"),
			"fieldname": "expected_rosin_yield",
			"fieldtype": "Percent",
			"width": 150
		},
		{
			"label": _("Expected Yield To Hash"),
			"fieldname": "expected__yield__to_hash",
			"fieldtype": "Percent",
			"width": 150
		},
		{
			"label": _("Expected Hash Yield"),
			"fieldname": "expected_hash_yield",
			"fieldtype": "Percent",
			"width": 150
		},
		{
			"label": _("Actual Yield To Hash"),
			"fieldname": "actual_yield_to_hash",
			"fieldtype": "Percent",
			"width": 150
		},
		{
			"label": _("Prime Strain"),
			"fieldname": "prime_strain",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130
		},
		{
			"label": _("Subprime Strain"),
			"fieldname": "subprime_strain",
			"fieldtype": "Link",
			"options": "Item",
			"width": 130
		},
		{
			"label": _("Raw Material Quantity"),
			"fieldname": "raw_material_quantity",
			"fieldtype": "Float",
			"width": 150
		}
	]


def get_data(filters):
	conditions = get_conditions(filters)
	data = frappe.db.sql(f"""
		SELECT
			rr.name,
			rr.tolling_partner,
			rr.batch,
			ltd.date_transferred,
			ltd.strain_name,
			ltd.batch_no,
			ltd.yield_to_hash,
			ltd.pounds_sent,
			ltd.pounds_ran,
			ltd.source_bloom,
			ltd.rosin_yield_,
			ltd.run_for,
			ltd.amount_ran_grams,
			ltd.hash_to_rosin_,
			ltd.150u_hash,
			ltd.120u_hash,
			ltd.90u_hash,
			ltd.73u_hash,
			ltd.45u_hash,
			ltd.25u_hash_copy,
			ltd.total_hash,
			ltd.150u_rosin,
			ltd.120u_rosin,
			ltd.90u_rosin,
			ltd.73u_rosin,
			ltd.45u_rosin,
			ltd.25u_rosin,
			ltd.total_rosin,
			ltd.subprime_total_tolled,
			ltd.prime_inventory_total_tolled,
			ltd.live_resin_produced,
			ltd.yield_,
			ltd.actual_rosin_yield,
			ltd.expected_rosin_yield,
			ltd.expected__yield__to_hash,
			ltd.expected_hash_yield,
			ltd.actual_yield_to_hash,
			ltd.prime_strain,
			ltd.subprime_strain,
			ltd.raw_material_quantity
		FROM
			`tabRosin Recording` rr
		INNER JOIN
			`tabLab Tolling Data` ltd ON ltd.parent = rr.name
		WHERE
			rr.docstatus < 2
			{conditions}
		ORDER BY
			rr.creation DESC
	""", filters, as_dict=1)
	return data


def get_conditions(filters):
	conditions = ""
	if filters.get("params"):
		# In case filters are wrapped in params (sometimes happens in JS)
		filters = filters.get("params")

	if filters.get("tolling_partner"):
		conditions += " AND rr.tolling_partner = %(tolling_partner)s"
	if filters.get("batch"):
		conditions += " AND rr.batch = %(batch)s"
	if filters.get("from_date"):
		conditions += " AND ltd.date_transferred >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND ltd.date_transferred <= %(to_date)s"

	return conditions


def get_report_summary(data):
	if not data:
		return None

	total_pounds_sent = 0
	total_pounds_ran = 0
	total_hash = 0
	total_rosin = 0
	total_rosin_yield = 0
	yield_count = 0

	for d in data:
		total_pounds_sent += flt(d.get("pounds_sent"))
		total_pounds_ran += flt(d.get("pounds_ran"))
		total_hash += flt(d.get("total_hash"))
		total_rosin += flt(d.get("total_rosin"))

		if d.get("rosin_yield_"):
			total_rosin_yield += flt(d.get("rosin_yield_"))
			yield_count += 1

	avg_rosin_yield = total_rosin_yield / yield_count if yield_count else 0

	return [
		{
			"value": total_pounds_sent,
			"indicator": "Blue",
			"label": _("Total Pounds Sent"),
			"datatype": "Float",
		},
		{
			"value": total_pounds_ran,
			"indicator": "Blue",
			"label": _("Total Pounds Ran"),
			"datatype": "Float",
		},
		{
			"value": total_hash,
			"indicator": "Green",
			"label": _("Total Hash Produced"),
			"datatype": "Float",
		},
		{
			"value": total_rosin,
			"indicator": "Green",
			"label": _("Total Rosin Produced"),
			"datatype": "Float",
		},
		{
			"value": avg_rosin_yield,
			"indicator": "Green" if avg_rosin_yield > 0 else "Red",
			"label": _("Avg Rosin Yield %"),
			"datatype": "Percent",
		},
	]
