import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

WORKBENCH_COMPANIES = ("Master Touch Manufacturing", "Motley Terpz", "TSBC Ranch")

MAX_RAW = 7
MAX_FINISHED = 3
PAGE_LENGTH = 200

QTY_EPSILON = 0.0001


def _conversion_type_options():
	field = frappe.get_meta("Conversion Entry Item").get_field("conversion_type")
	return [o.strip() for o in (field.options or "").split("\n") if o.strip()]


@frappe.whitelist()
def get_conversion_types():
	return _conversion_type_options()


@frappe.whitelist()
def get_companies():
	existing = set(frappe.get_all("Company", pluck="name"))
	return [c for c in WORKBENCH_COMPANIES if c in existing]


def _company_filter(company):
	if not company:
		frappe.throw(_("Company is required."))
	if company not in WORKBENCH_COMPANIES:
		frappe.throw(_("The Conversion Workbench runs for {0} only.")
		             .format(", ".join(WORKBENCH_COMPANIES)))
	return company


@frappe.whitelist()
def get_item_groups(company):
	company = _company_filter(company)
	rows = frappe.db.sql(
		"""
		-- aliased item_count, not items: on frappe._dict `.items` is dict's own
		-- method, so `row.items` would return the bound method, not the number.
		SELECT i.item_group AS item_group, COUNT(DISTINCT b.item_code) AS item_count
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE w.company = %(company)s
		  AND b.actual_qty > 0
		  AND i.disabled = 0
		GROUP BY i.item_group
		ORDER BY i.item_group
		""",
		{"company": company}, as_dict=True,
	)
	return {
		"groups": rows,
		"total": sum(r.item_count for r in rows),
	}


@frappe.whitelist()
def get_stock_items(company, item_group=None, warehouse=None, search=None,
                    start=0, page_length=PAGE_LENGTH):
	company = _company_filter(company)
	conds = ["w.company = %(company)s", "b.actual_qty > 0", "i.disabled = 0"]
	values = {"company": company,
	          "start": cint(start),
	          "page_length": cint(page_length) or PAGE_LENGTH}

	if item_group:
		conds.append("i.item_group = %(item_group)s")
		values["item_group"] = item_group
	if warehouse:
		conds.append("b.warehouse = %(warehouse)s")
		values["warehouse"] = warehouse
	if search:
		conds.append("(b.item_code LIKE %(search)s OR i.item_name LIKE %(search)s)")
		values["search"] = "%{0}%".format(search)

	rows = frappe.db.sql(
		"""
		SELECT b.item_code, i.item_name, i.item_group, b.warehouse,
		       i.stock_uom, b.actual_qty, b.valuation_rate
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE {conds}
		ORDER BY i.item_name, b.warehouse
		LIMIT %(start)s, %(page_length)s
		""".format(conds=" AND ".join(conds)),
		values, as_dict=True,
	)
	return {"items": rows, "page_length": values["page_length"]}


def _validate(payload, raws, finished):
	if not raws or not finished:
		frappe.throw(_("Select at least one raw material and one finished item."))

	if len(raws) > MAX_RAW or len(finished) > MAX_FINISHED:
		frappe.throw(_("A Conversion Entry supports up to 7 raw materials and 3 finished items."))

	conversion_type = "{0} to {1}".format(len(raws), len(finished))
	if conversion_type not in _conversion_type_options():
		frappe.throw(_("A conversion of {0} to {1} is not available. Choose a supported combination.")
		             .format(len(raws), len(finished)))

	source = payload.get("source_warehouse")
	target = payload.get("target_warehouse")
	if not source or not target:
		frappe.throw(_("Source Warehouse and Target Warehouse are required."))

	for r in raws:
		if r.get("warehouse") and r["warehouse"] != source:
			frappe.throw(_("All raw materials must come from the same Source Warehouse."))

	for r in raws:
		qty = flt(r.get("qty"))
		item = r.get("item_code")
		if qty <= QTY_EPSILON:
			frappe.throw(_("Enter a quantity for {0}.").format(item))
		available = _available(item, source)
		if qty - available > QTY_EPSILON:
			frappe.throw(_("Quantity for {0} cannot exceed the available {1} {2}.")
			             .format(item, flt(available, 2), _stock_uom(item)))

	raw_codes = {r.get("item_code") for r in raws}
	for f in finished:
		item = f.get("item_code")
		if flt(f.get("qty")) <= QTY_EPSILON:
			frappe.throw(_("Enter a quantity for {0}.").format(item))

		detail = frappe.db.get_value("Item", item, ["is_stock_item", "disabled"], as_dict=True)
		if not detail or not detail.is_stock_item or detail.disabled:
			frappe.throw(_("{0} cannot be used as a finished item.").format(item))

		if item in raw_codes and source == target:
			frappe.throw(_("{0} cannot be converted into itself in the same warehouse.").format(item))

	return conversion_type


def _available(item_code, warehouse):
	return flt(frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0)


def _stock_uom(item_code):
	return frappe.db.get_value("Item", item_code, "stock_uom") or ""


@frappe.whitelist()
def create_conversion(payload):
	payload = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})

	if not frappe.has_permission("Conversion Entry", "create"):
		frappe.throw(_("You are not permitted to create a Conversion Entry."),
		             frappe.PermissionError)
	if not frappe.has_permission("Conversion Entry", "submit"):
		frappe.throw(_("You are not permitted to submit a Conversion Entry."),
		             frappe.PermissionError)

	_company_filter(payload.get("company"))

	if payload.get("reasons") == "Tolling":
		if not payload.get("supplier"):
			frappe.throw(_("Supplier is required for a Tolling conversion."))
		if not payload.get("expense_account"):
			frappe.throw(_("Expense Account is required for a Tolling conversion."))

	raws = [r for r in (payload.get("raw_materials") or []) if r.get("item_code")]
	finished = [f for f in (payload.get("finished_items") or []) if f.get("item_code")]
	conversion_type = _validate(payload, raws, finished)

	row = {
		"conversion_type": conversion_type,
		"source_warehouse": payload.get("source_warehouse"),
		"target_warehouse": payload.get("target_warehouse"),
	}
	if payload.get("expense_account"):
		row["expense_account"] = payload["expense_account"]

	for n, r in enumerate(raws, start=1):
		row["raw_material_%d" % n] = r["item_code"]
		row["qty_rm_%d" % n] = flt(r.get("qty"))
		if r.get("tag"):
			row["rm_%d_tag" % n] = r["tag"]

	for n, f in enumerate(finished, start=1):
		row["finished_good_%d" % n] = f["item_code"]
		row["qty_fg_%d" % n] = flt(f.get("qty"))
		if f.get("tag"):
			row["fg_%d_tag" % n] = f["tag"]

	doc = frappe.new_doc("Conversion Entry")
	doc.posting_date = payload.get("posting_date") or nowdate()
	doc.company = payload.get("company")
	header = ["reasons", "partners", "conversion_status", "sales_order", "project", "notes"]
	header.append("supplier" if payload.get("reasons") == "Tolling" else "customer")
	for field in header:
		if payload.get(field):
			doc.set(field, payload[field])
	doc.append("items", row)

	for r in raws:
		available = _available(r["item_code"], payload.get("source_warehouse"))
		if flt(r.get("qty")) - available > QTY_EPSILON:
			frappe.throw(_("Quantity for {0} cannot exceed the available {1} {2}.")
			             .format(r["item_code"], flt(available, 2), _stock_uom(r["item_code"])))

	doc.insert()
	doc.submit()

	stock_entry = frappe.db.get_value(
		"Stock Entry", {"custom_conversion_entry_reference": doc.name, "docstatus": 0}, "name")

	return {
		"conversion_entry": doc.name,
		"conversion_type": conversion_type,
		"stock_entry": stock_entry,
	}
