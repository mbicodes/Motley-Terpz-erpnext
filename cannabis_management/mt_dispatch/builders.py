import frappe
from frappe import _
from frappe.utils import flt, nowdate

from cannabis_management.mt_dispatch import gates
from cannabis_management.mt_dispatch.gates import GateError, draft_delivery_note

MAX_RAW_MATERIALS = 7
MAX_FINISHED_GOODS = 3
MICRON_FIELDS = [
	("bh_grams_150u", "bh_micron_150u", "is_bubble_hash", "Bubble hash 150µ"),
	("bh_grams_120u_73u", "bh_micron_120u_73u", "is_bubble_hash", "Bubble hash 120µ - 73µ"),
	("bh_grams_45u", "bh_micron_45u", "is_bubble_hash", "Bubble hash 45µ"),
	("rosin_grams_150u", "rosin_micron_150u", "is_rosin", "Rosin 150µ"),
	("rosin_grams_120u_73u", "rosin_micron_120u_73u", "is_rosin", "Rosin 120µ - 73µ"),
	("rosin_grams_45u", "rosin_micron_45u", "is_rosin", "Rosin 45µ"),
]


def conversion_types():
	field = frappe.get_meta("Conversion Entry Item").get_field("conversion_type")
	return {o.strip() for o in (field.options or "").split("\n") if o.strip()}


def resolve_item(value, warehouse=None):
	if not value:
		return None
	if frappe.db.exists("Item", value):
		return value

	raise GateError(_("{0} is not an item code.").format(value))


def make_conversion_entry(so, cfg, payload):
	rows = payload.get("rows") or []
	if not rows:
		raise GateError(_("Add at least one conversion row."))

	valid_types = conversion_types()

	ce = frappe.new_doc("Conversion Entry")
	ce.company = so.company
	ce.customer = so.customer
	ce.sales_order = so.name
	ce.posting_date = payload.get("posting_date") or nowdate()

	for i, row in enumerate(rows, start=1):
		raw = [r for r in (row.get("raw_materials") or []) if r.get("item") and flt(r.get("qty")) > 0]
		finished = [f for f in (row.get("finished_goods") or []) if f.get("item") and flt(f.get("qty")) > 0]

		if not raw or not finished:
			raise GateError(_("Row {0}: needs at least one raw material and one finished good.").format(i))
		if len(raw) > MAX_RAW_MATERIALS or len(finished) > MAX_FINISHED_GOODS:
			raise GateError(
				_("Row {0}: at most {1} raw materials and {2} finished goods.").format(
					i, MAX_RAW_MATERIALS, MAX_FINISHED_GOODS
				)
			)

		conversion_type = f"{len(raw)} to {len(finished)}"
		if conversion_type not in valid_types:
			raise GateError(
				_("Row {0}: {1} is not a conversion type this site allows.").format(i, conversion_type)
			)

		source_warehouse = row.get("source_warehouse") or cfg.default_source_warehouse
		target_warehouse = row.get("target_warehouse") or cfg.default_target_warehouse

		values = {
			"conversion_type": conversion_type,
			"source_warehouse": source_warehouse,
			"target_warehouse": target_warehouse,
		}

		for n, entry in enumerate(raw, start=1):
			item_code = resolve_item(entry["item"], source_warehouse)
			values[f"raw_material_{n}"] = item_code
			values[f"qty_rm_{n}"] = flt(entry["qty"])

		for n, entry in enumerate(finished, start=1):
			item_code = resolve_item(entry["item"], target_warehouse)
			values[f"finished_good_{n}"] = item_code
			values[f"qty_fg_{n}"] = flt(entry["qty"])

		for grams_field, check_field, product_flag, _label in MICRON_FIELDS:
			if row.get(grams_field):
				values[grams_field] = flt(row[grams_field])
				values[check_field] = 1
				values[product_flag] = 1

		ce.append("items", values)

	ce.insert()
	if payload.get("submit"):
		ce.submit()
	return ce.name


def build_delivery_note(so, cfg, payload):
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	so_rows = {row.name: row for row in so.items}
	targets = gates.conversion_targets(so.name)

	for item in dn.items:
		row = so_rows.get(item.so_detail)
		if row:
			item.warehouse = gates.delivery_warehouse(so, row, targets)

	warehouses = {item.warehouse for item in dn.items}
	if len(warehouses) == 1:
		dn.set_warehouse = warehouses.pop()

	dn.insert()
	return dn.name


def attach_manifest(so, cfg, payload):
	dn_name = draft_delivery_note(so.name)
	if not dn_name:
		raise GateError(_("No draft Delivery Note for this order."))

	number = (payload.get("manifest_number") or "").strip()
	file_url = payload.get("file_url")

	updates = {"custom_metrc_manifest_number": number}
	if file_url:
		attach_file(file_url, "Delivery Note", dn_name)
		updates["custom_manifest"] = file_url

	frappe.db.set_value("Delivery Note", dn_name, updates, update_modified=False)
	return dn_name


def attach_file(file_url, doctype, name):
	existing = frappe.db.exists(
		"File", {"file_url": file_url, "attached_to_doctype": doctype, "attached_to_name": name}
	)
	if existing:
		return existing

	source = frappe.db.get_value("File", {"file_url": file_url}, ["name", "file_name", "is_private"], as_dict=True)
	if not source:
		raise GateError(_("That upload is no longer available. Try again."))

	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_url": file_url,
			"file_name": source.file_name,
			"is_private": source.is_private,
			"attached_to_doctype": doctype,
			"attached_to_name": name,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_payment_entry(so, cfg, payload):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	from cannabis_management.mt_dispatch.payments import refresh_payment_status

	amount = flt(payload.get("amount"))
	if amount <= 0:
		raise GateError(_("Enter an amount greater than zero."))

	pe = get_payment_entry("Sales Order", so.name)
	pe.paid_amount = amount
	pe.received_amount = amount
	mode = payload.get("mode_of_payment") or cfg.default_mode_of_payment
	if mode and mode != pe.mode_of_payment:
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

		account = (get_bank_cash_account(mode, so.company) or {}).get("account")
		if account:
			pe.paid_to = account
			pe.paid_to_account_currency = frappe.db.get_value("Account", account, "account_currency")
	pe.mode_of_payment = mode
	pe.reference_no = payload.get("reference_no")
	pe.reference_date = payload.get("reference_date") or nowdate()

	for ref in pe.references or []:
		ref.allocated_amount = min(flt(ref.outstanding_amount), amount)

	pe.insert()
	pe.submit()

	if payload.get("file_url"):
		attach_file(payload["file_url"], "Payment Entry", pe.name)

	refresh_payment_status(so.name)
	return pe.name
