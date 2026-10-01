"""Documents the flow creates: Conversion Entries, Delivery Notes, Payments.

Each builder is a transition effect, so it runs with frappe.flags.mt_dispatch
already set -- which is what lets the Delivery Note past its own insert guard.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from cannabis_management.mt_dispatch.gates import GateError, draft_delivery_note

MAX_RAW_MATERIALS = 7
MAX_FINISHED_GOODS = 3
# (grams field, its tick, the product tick, Slack label). Conversion Entry Item
# records microns as "the product was run at this size, and this many grams came
# off it", so a gram figure from Slack has to bring both ticks with it or the
# form would show a number under an unticked box.
MICRON_FIELDS = [
	("bh_grams_150u", "bh_micron_150u", "is_bubble_hash", "Bubble hash 150µ"),
	("bh_grams_120u_73u", "bh_micron_120u_73u", "is_bubble_hash", "Bubble hash 120µ - 73µ"),
	("bh_grams_45u", "bh_micron_45u", "is_bubble_hash", "Bubble hash 45µ"),
	("rosin_grams_150u", "rosin_micron_150u", "is_rosin", "Rosin 150µ"),
	("rosin_grams_120u_73u", "rosin_micron_120u_73u", "is_rosin", "Rosin 120µ - 73µ"),
	("rosin_grams_45u", "rosin_micron_45u", "is_rosin", "Rosin 45µ"),
]


# ── Conversion Entry ─────────────────────────────────────────────────────────


def conversion_types():
	"""The Select's own options, read from the doctype rather than hardcoded,
	so this can never drift from what the field will accept."""
	field = frappe.get_meta("Conversion Entry Item").get_field("conversion_type")
	return {o.strip() for o in (field.options or "").split("\n") if o.strip()}


def resolve_item(value, warehouse=None):
	"""An item code, or the item behind a Metric Tag code.

	The existing tag helpers in cannabis_management.custom.metric_tag are link
	search queries -- they answer "which tags can I pick here", not "what item
	is this code". There is no server-side code-to-item resolver to reuse, so
	this is the one, and everything that needs it calls here.
	"""
	if not value:
		return None, None
	if frappe.db.exists("Item", value):
		return value, None

	tag = frappe.db.get_value(
		"Metric Tag", {"name": value}, ["name", "item_code"], as_dict=True
	) or frappe.db.get_value(
		"Metric Tag", {"muid": value}, ["name", "item_code"], as_dict=True
	)
	if not tag or not tag.item_code:
		raise GateError(_("{0} is neither an item code nor a Metric Tag.").format(value))
	return tag.item_code, tag.name


def make_conversion_entry(so, cfg, payload):
	"""Insert a Conversion Entry from the rows the user filled in.

	conversion_type is derived from how many raw materials and finished goods
	a row actually has. The field's option list is not exhaustive -- there is
	no "2 to 3", for instance -- so a combination it does not offer is
	rejected here rather than failing on save with a Select error.
	"""
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
			item_code, tag = resolve_item(entry["item"], source_warehouse)
			values[f"raw_material_{n}"] = item_code
			values[f"qty_rm_{n}"] = flt(entry["qty"])
			if tag or entry.get("tag"):
				values[f"rm_{n}_tag"] = entry.get("tag") or tag

		for n, entry in enumerate(finished, start=1):
			item_code, tag = resolve_item(entry["item"], target_warehouse)
			values[f"finished_good_{n}"] = item_code
			values[f"qty_fg_{n}"] = flt(entry["qty"])
			if entry.get("tag"):
				values[f"fg_{n}_tag"] = entry["tag"]

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


# ── Delivery Note ────────────────────────────────────────────────────────────


def build_delivery_note(so, cfg, payload):
	"""Core's own mapper, with the Metric Tag chosen per line.

	Runs inside transition(), so frappe.flags.mt_dispatch is set and the
	before_insert guard lets this through -- which is the only way a governed
	order gets a Delivery Note at all.
	"""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	picks = payload.get("muid") or {}

	for item in dn.items:
		chosen = picks.get(item.so_detail)
		if chosen:
			item.tags = chosen

	dn.insert()
	return dn.name


def attach_manifest(so, cfg, payload):
	"""Put the manifest number and file on the draft Delivery Note."""
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
	"""Point an already-saved private File at a document.

	The Slack layer downloads from url_private_download and saves the File; by
	the time this runs the bytes are on disk, so this only creates the link.
	"""
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


# ── Payment Entry ────────────────────────────────────────────────────────────


def make_payment_entry(so, cfg, payload):
	"""Take money against the order and re-run the payment gate.

	Limited to the finance flag because this submits a Payment Entry, which
	needs those rights in the ERP too.
	"""
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
		# get_payment_entry picked the receiving account for its own default
		# mode; a different mode means different money, so a different account.
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
