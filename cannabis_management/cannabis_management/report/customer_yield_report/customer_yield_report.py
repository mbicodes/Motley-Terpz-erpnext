import frappe
from frappe.utils import flt

GROUP_KEYS = {
	"By Item": ("item_code",),
	"By Customer": ("customer",),
	"By Sales Order": ("sales_order", "customer"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	group_by = filters.get("group_by") or "Detail"

	if group_by == "Detail":
		columns, data = detail_columns(), rows
	else:
		columns, data = group_columns(group_by), group_rows(rows, GROUP_KEYS[group_by])

	return columns, data, None, None, summary(rows)


def get_rows(filters):
	conditions = ["iy.parenttype = 'Customer Yield Feedback'"]
	conditions.append("cyf.docstatus < 2" if filters.include_drafts else "cyf.docstatus = 1")
	if filters.from_date:
		conditions.append("cyf.date >= %(from_date)s")
	if filters.to_date:
		conditions.append("cyf.date <= %(to_date)s")
	for field in ("customer", "sales_order", "company"):
		if filters.get(field):
			conditions.append(f"cyf.{field} = %({field})s")
	if filters.item_code:
		conditions.append("iy.item_code = %(item_code)s")
	if filters.item_group:
		lft, rgt = frappe.db.get_value("Item Group", filters.item_group, ["lft", "rgt"])
		conditions.append(
			f"i.item_group IN (SELECT name FROM `tabItem Group` WHERE lft >= {lft} AND rgt <= {rgt})"
		)

	return frappe.db.sql(
		f"""
		SELECT cyf.name AS feedback, cyf.date, cyf.docstatus, cyf.customer, cyf.customer_name,
			cyf.sales_order, cyf.company, iy.item_code, i.item_name, i.item_group, iy.project,
			iy.yield_source, iy.quantity, iy.hash_qty, iy.yield_percentage, iy.rosin_qty, iy.hash_to_rosin,
			iy.rosin_yield, iy.remarks
		FROM `tabItem Yield` iy
		INNER JOIN `tabCustomer Yield Feedback` cyf ON cyf.name = iy.parent
		LEFT JOIN `tabItem` i ON i.name = iy.item_code
		WHERE {" AND ".join(conditions)}
		ORDER BY cyf.date DESC, cyf.name DESC, iy.idx
		""",
		filters,
		as_dict=True,
	)


def weighted(rows, pct_field, weight_field):
	pairs = [(flt(r[pct_field]), flt(r[weight_field])) for r in rows if flt(r[pct_field])]
	if not pairs:
		return None
	total_weight = sum(w for _, w in pairs)
	if total_weight:
		return sum(p * w for p, w in pairs if w) / sum(w for p, w in pairs if w)
	return sum(p for p, _ in pairs) / len(pairs)


def group_rows(rows, keys):
	groups = {}
	for r in rows:
		groups.setdefault(tuple(r[k] for k in keys), []).append(r)

	data = []
	for key, members in groups.items():
		first = members[0]
		data.append({
			"item_code": first.item_code,
			"item_name": first.item_name,
			"customer": first.customer,
			"customer_name": first.customer_name,
			"sales_order": first.sales_order,
			"reports": len({m.feedback for m in members}),
			"lines": len(members),
			"last_date": max(m.date for m in members),
			"quantity": sum(flt(m.quantity) for m in members),
			"hash_qty": sum(flt(m.hash_qty) for m in members),
			"rosin_qty": sum(flt(m.rosin_qty) for m in members),
			"yield_percentage": weighted(members, "yield_percentage", "quantity"),
			"hash_to_rosin": weighted(members, "hash_to_rosin", "hash_qty"),
			"rosin_yield": weighted(members, "rosin_yield", "quantity"),
			"min_yield": min((flt(m.yield_percentage) for m in members if flt(m.yield_percentage)), default=None),
			"max_yield": max((flt(m.yield_percentage) for m in members if flt(m.yield_percentage)), default=None),
		})
	data.sort(key=lambda d: d["last_date"], reverse=True)
	return data


def summary(rows):
	if not rows:
		return []
	return [
		{"label": "Yield Reports", "value": len({r.feedback for r in rows}), "datatype": "Int"},
		{"label": "Customers", "value": len({r.customer for r in rows}), "datatype": "Int"},
		{"label": "LBS Reported", "value": sum(flt(r.quantity) for r in rows), "datatype": "Float"},
		{"label": "Avg Yield To Hash %", "value": weighted(rows, "yield_percentage", "quantity") or 0,
			"datatype": "Percent", "indicator": "Blue"},
		{"label": "Avg Hash to Rosin %", "value": weighted(rows, "hash_to_rosin", "hash_qty") or 0,
			"datatype": "Percent", "indicator": "Green"},
		{"label": "Avg Rosin Yield %", "value": weighted(rows, "rosin_yield", "quantity") or 0,
			"datatype": "Percent", "indicator": "Orange"},
	]

YIELD_COLUMNS = [
	{"label": "Qty (LBS)", "fieldname": "quantity", "fieldtype": "Float", "width": 100},
	{"label": "Hash (g)", "fieldname": "hash_qty", "fieldtype": "Float", "width": 100},
	{"label": "Yield To Hash %", "fieldname": "yield_percentage", "fieldtype": "Percent", "width": 130},
	{"label": "Rosin (g)", "fieldname": "rosin_qty", "fieldtype": "Float", "width": 100},
	{"label": "Hash to Rosin %", "fieldname": "hash_to_rosin", "fieldtype": "Percent", "width": 130},
	{"label": "Rosin Yield %", "fieldname": "rosin_yield", "fieldtype": "Percent", "width": 120},
]


def detail_columns():
	return [
		{"label": "Yield Report", "fieldname": "feedback", "fieldtype": "Link", "options": "Customer Yield Feedback", "width": 150},
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
		{"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 150},
		{"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
		{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": "Batch", "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": "Source", "fieldname": "yield_source", "fieldtype": "Data", "width": 90},
		*YIELD_COLUMNS,
		{"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 200},
	]


def group_columns(group_by):
	lead = {
		"By Item": [
			{"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 120},
			{"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		],
		"By Customer": [
			{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 200},
		],
		"By Sales Order": [
			{"label": "Sales Order", "fieldname": "sales_order", "fieldtype": "Link", "options": "Sales Order", "width": 160},
			{"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		],
	}[group_by]
	return [
		*lead,
		{"label": "Reports", "fieldname": "reports", "fieldtype": "Int", "width": 80},
		{"label": "Last Received", "fieldname": "last_date", "fieldtype": "Date", "width": 110},
		*YIELD_COLUMNS,
		{"label": "Min Yield To Hash %", "fieldname": "min_yield", "fieldtype": "Percent", "width": 140},
		{"label": "Max Yield To Hash %", "fieldname": "max_yield", "fieldtype": "Percent", "width": 140},
	]
