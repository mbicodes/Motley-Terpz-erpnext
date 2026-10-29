import frappe
from frappe import _
from frappe.utils import flt

STATUS_COMPLETE = "Complete"
STATUS_NO_DN = "Invoice not delivered"
STATUS_NO_SI = "Delivery not invoiced"
STATUS_NO_SO = "No Sales Order"

LINK_STATUSES = [STATUS_COMPLETE, STATUS_NO_DN, STATUS_NO_SI, STATUS_NO_SO]

LINKED_DIRECT = "Direct"
LINKED_VIA_SO = "Via Sales Order"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = _build_rows(filters)
	return get_columns(), rows


def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
		 "options": "Customer", "width": 200},
		{"label": _("Sales Order"), "fieldname": "sales_order", "fieldtype": "Link",
		 "options": "Sales Order", "width": 150},
		{"label": _("SO Date"), "fieldname": "so_date", "fieldtype": "Date", "width": 95},
		{"label": _("SO Status"), "fieldname": "so_status", "fieldtype": "Data", "width": 110},
		{"label": _("SO Qty"), "fieldname": "so_qty", "fieldtype": "Float",
		 "precision": 2, "width": 90},
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link",
		 "options": "Delivery Note", "width": 150},
		{"label": _("DN Date"), "fieldname": "dn_date", "fieldtype": "Date", "width": 95},
		{"label": _("DN Status"), "fieldname": "dn_status", "fieldtype": "Data", "width": 110},
		{"label": _("DN Qty"), "fieldname": "dn_qty", "fieldtype": "Float",
		 "precision": 2, "width": 90},
		{"label": _("Sales Invoice"), "fieldname": "sales_invoice", "fieldtype": "Link",
		 "options": "Sales Invoice", "width": 150},
		{"label": _("SI Date"), "fieldname": "si_date", "fieldtype": "Date", "width": 95},
		{"label": _("SI Status"), "fieldname": "si_status", "fieldtype": "Data", "width": 110},
		{"label": _("SI Qty"), "fieldname": "si_qty", "fieldtype": "Float",
		 "precision": 2, "width": 90},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
		{"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Linked Via"), "fieldname": "linked_via", "fieldtype": "Data", "width": 120},
		{"label": _("Link Status"), "fieldname": "link_status", "fieldtype": "Data", "width": 160},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link",
		 "options": "Company", "width": 160},
	]


def _docstatus_list(filters):
	allowed = [1]
	if filters.get("include_draft"):
		allowed.append(0)
	if filters.get("include_cancelled"):
		allowed.append(2)
	return allowed


def _build_rows(filters):
	docstatuses = _docstatus_list(filters)

	invoices = _fetch_invoices(filters, docstatuses)
	deliveries = _fetch_deliveries(filters, docstatuses)
	orders = {}

	si_cache = dict(invoices)
	dn_cache = dict(deliveries)

	si_to_dn, dn_to_si = _dn_si_links(docstatuses)
	si_to_so = _si_so_links(docstatuses)
	dn_to_so = _dn_so_links(docstatuses)

	so_to_dn = _invert(dn_to_so)
	so_to_si = _invert(si_to_so)

	rows = []
	seen = set()
	covered_dns = set()

	for si_name, si in invoices.items():
		sos = set(si_to_so.get(si_name, set()))
		pairs = _counterparts(si_to_dn.get(si_name), sos, so_to_dn)

		for dn, how in pairs:
			row_sos = set(sos)
			if dn:
				row_sos |= dn_to_so.get(dn, set())
				covered_dns.add(dn)
			for so in (sorted(row_sos) or [None]):
				key = (so, dn, si_name)
				if key in seen:
					continue
				seen.add(key)
				rows.append(_make_row(si, _delivery(dn_cache, dn), _order(orders, so),
				                      so, dn, si_name, how))

	for dn_name, dn in deliveries.items():
		if dn_name in covered_dns:
			continue
		sos = set(dn_to_so.get(dn_name, set()))
		pairs = _counterparts(dn_to_si.get(dn_name), sos, so_to_si)

		for si_name, how in pairs:
			si = _invoice(si_cache, si_name) if si_name else None
			row_sos = set(sos)
			if si_name:
				row_sos |= si_to_so.get(si_name, set())
			for so in (sorted(row_sos) or [None]):
				key = (so, dn_name, si_name)
				if key in seen:
					continue
				seen.add(key)
				rows.append(_make_row(si, dn, _order(orders, so), so, dn_name, si_name, how))

	if filters.get("sales_order"):
		rows = [r for r in rows if r["sales_order"] == filters.sales_order]
	rows = _apply_link_status_filter(rows, filters)
	_attach_quantities(rows)
	rows.sort(key=lambda r: (r.get("si_date") or r.get("dn_date") or "", r.get("sales_invoice") or ""),
	          reverse=True)
	return rows


def _counterparts(direct, sos, so_map):
	if direct:
		return [(name, LINKED_DIRECT) for name in sorted(direct)]

	via = set()
	for so in sos:
		via |= so_map.get(so, set())
	if via:
		return [(name, LINKED_VIA_SO) for name in sorted(via)]

	return [(None, "")]


def _invert(mapping):
	out = {}
	for key, values in mapping.items():
		for value in values:
			out.setdefault(value, set()).add(key)
	return out


def _attach_quantities(rows):
	for name_field, qty_field, child_dt in (
		("sales_order", "so_qty", "Sales Order Item"),
		("delivery_note", "dn_qty", "Delivery Note Item"),
		("sales_invoice", "si_qty", "Sales Invoice Item"),
	):
		totals = _qty_totals(child_dt, sorted({r[name_field] for r in rows if r.get(name_field)}))
		for r in rows:
			r[qty_field] = totals.get(r.get(name_field))


def _qty_totals(child_dt, names):
	if not names:
		return {}
	out = {}
	CHUNK = 500
	for i in range(0, len(names), CHUNK):
		part = tuple(names[i:i + CHUNK])
		for r in frappe.db.sql(
			"""select parent, sum(qty) as qty from `tab{0}`
			   where parent in %(names)s group by parent""".format(child_dt),
			{"names": part}, as_dict=True,
		):
			out[r.parent] = flt(r.qty)
	return out


def _order(cache, name):
	if not name:
		return None
	if name not in cache:
		cache[name] = frappe.db.get_value(
			"Sales Order", name,
			["name", "transaction_date", "status", "customer", "company"], as_dict=True
		)
	return cache[name]


def _delivery(cache, name):
	if not name:
		return None
	if name not in cache:
		cache[name] = frappe.db.get_value(
			"Delivery Note", name,
			["name", "posting_date", "status", "customer", "company"], as_dict=True
		)
	return cache[name]


def _invoice(cache, name):
	if not name:
		return None
	if name not in cache:
		cache[name] = frappe.db.get_value(
			"Sales Invoice", name,
			["name", "posting_date", "status", "customer", "company",
			 "grand_total", "outstanding_amount"], as_dict=True
		)
	return cache[name]


def _make_row(si, dn, so, so_name, dn_name, si_name, linked_via=""):
	if si_name and dn_name:
		link_status = STATUS_COMPLETE if so_name else STATUS_NO_SO
	elif si_name:
		link_status = STATUS_NO_DN
	else:
		link_status = STATUS_NO_SI

	source = si or dn or so or {}
	return {
		"customer": (si or {}).get("customer") or (dn or {}).get("customer") or (so or {}).get("customer"),
		"sales_order": so_name,
		"so_date": (so or {}).get("transaction_date"),
		"so_status": (so or {}).get("status"),
		"delivery_note": dn_name,
		"dn_date": (dn or {}).get("posting_date"),
		"dn_status": (dn or {}).get("status"),
		"sales_invoice": si_name,
		"si_date": (si or {}).get("posting_date"),
		"si_status": (si or {}).get("status"),
		"grand_total": flt((si or {}).get("grand_total")),
		"outstanding_amount": flt((si or {}).get("outstanding_amount")),
		"linked_via": linked_via,
		"link_status": link_status,
		"company": source.get("company"),
	}


def _apply_link_status_filter(rows, filters):
	wanted = filters.get("link_status")
	if not wanted:
		return rows
	return [r for r in rows if r["link_status"] == wanted]


def _common_conditions(filters, docstatuses, date_field):
	conds = ["docstatus in %(docstatuses)s"]
	values = {"docstatuses": tuple(docstatuses)}

	if filters.get("company"):
		conds.append("company = %(company)s")
		values["company"] = filters.company
	if filters.get("customer"):
		conds.append("customer = %(customer)s")
		values["customer"] = filters.customer
	if filters.get("from_date"):
		conds.append(f"{date_field} >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conds.append(f"{date_field} <= %(to_date)s")
		values["to_date"] = filters.to_date
	return conds, values


def _fetch_invoices(filters, docstatuses):
	conds, values = _common_conditions(filters, docstatuses, "posting_date")
	if filters.get("sales_invoice"):
		conds.append("name = %(sales_invoice)s")
		values["sales_invoice"] = filters.sales_invoice

	rows = frappe.db.sql(
		"""select name, customer, company, posting_date, status, docstatus,
		          grand_total, outstanding_amount
		   from `tabSales Invoice` where {0}""".format(" and ".join(conds)),
		values, as_dict=True,
	)
	return {r.name: r for r in rows}


def _fetch_deliveries(filters, docstatuses):
	conds, values = _common_conditions(filters, docstatuses, "posting_date")
	if filters.get("delivery_note"):
		conds.append("name = %(delivery_note)s")
		values["delivery_note"] = filters.delivery_note

	rows = frappe.db.sql(
		"""select name, customer, company, posting_date, status, docstatus
		   from `tabDelivery Note` where {0}""".format(" and ".join(conds)),
		values, as_dict=True,
	)
	return {r.name: r for r in rows}


def _dn_si_links(docstatuses):
	si_to_dn, dn_to_si = {}, {}

	for r in frappe.db.sql(
		"""select distinct parent as si, delivery_note as dn
		   from `tabSales Invoice Item`
		   where ifnull(delivery_note,'') <> '' and docstatus in %(ds)s""",
		{"ds": tuple(docstatuses)}, as_dict=True,
	):
		si_to_dn.setdefault(r.si, set()).add(r.dn)
		dn_to_si.setdefault(r.dn, set()).add(r.si)

	for r in frappe.db.sql(
		"""select distinct parent as dn, against_sales_invoice as si
		   from `tabDelivery Note Item`
		   where ifnull(against_sales_invoice,'') <> '' and docstatus in %(ds)s""",
		{"ds": tuple(docstatuses)}, as_dict=True,
	):
		si_to_dn.setdefault(r.si, set()).add(r.dn)
		dn_to_si.setdefault(r.dn, set()).add(r.si)

	return si_to_dn, dn_to_si


def _si_so_links(docstatuses):
	out = {}
	for r in frappe.db.sql(
		"""select distinct parent as si, sales_order as so
		   from `tabSales Invoice Item`
		   where ifnull(sales_order,'') <> '' and docstatus in %(ds)s""",
		{"ds": tuple(docstatuses)}, as_dict=True,
	):
		out.setdefault(r.si, set()).add(r.so)
	return out


def _dn_so_links(docstatuses):
	out = {}
	for r in frappe.db.sql(
		"""select distinct parent as dn, against_sales_order as so
		   from `tabDelivery Note Item`
		   where ifnull(against_sales_order,'') <> '' and docstatus in %(ds)s""",
		{"ds": tuple(docstatuses)}, as_dict=True,
	):
		out.setdefault(r.dn, set()).add(r.so)
	return out
