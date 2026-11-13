# Sales Operation Board (/app/sales-operation-board): API for the page (Board, By Owner, Calendar, List).
# All rules (probability, weighted value, stage log, attention flags, stock) live in Python; the page only renders.

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from cannabis_management import sales_ops

DT = sales_ops.DEAL

FIELDS = [
	"name", "account", "stage", "deal_owner", "priority", "contact_name", "phone", "email",
	"location_address", "license_number", "customer", "lead", "next_step_due", "sample_date",
	"expected_close", "delivery_pickup", "stage_changed_on", "product_line", "tier", "form",
	"total_grams", "price_per_gram", "value_override", "deal_value", "probability", "weighted_value",
	"timeline", "status_detail", "samples", "copack", "hardware", "size_per_strain", "strain_profiles",
	"buyer_notes", "deal_notes", "next_steps", "fulfillment_notes", "ops_notes", "payment_terms",
	"lead_source", "lost_reason", "creation", "modified", "modified_by",
]

# Fields the page may change directly (drag and drop, inline edit, panel selectors, requirement prompts).
EDITABLE = {
	"stage", "deal_owner", "priority", "next_step_due", "sample_date", "expected_close",
	"delivery_pickup", "lost_reason", "customer", "samples",
}
DATE_FIELDS = {"next_step_due", "sample_date", "expected_close", "delivery_pickup"}

# Export column order = Pipeline sheet of Matt's workbook.
EXPORT_COLUMNS = [
	("Account", "account"), ("Stage", "stage"), ("Owner", "owner_name"), ("Product Line", "product_line"),
	("Tier", "tier"), ("Form", "form"), ("Total Grams", "total_grams"), ("Price per Gram", "price_per_gram"),
	("Value Override", "value_override"), ("Deal Value", "deal_value"), ("Timeline", "timeline"),
	("Status Detail", "status_detail"), ("Samples", "samples"), ("Copack", "copack"), ("Hardware", "hardware"),
	("Size per Strain", "size_per_strain"), ("Strain Profiles", "strain_profiles"),
	("Buyer Notes / Requests", "buyer_notes"), ("Deal Notes", "deal_notes"), ("Next Steps to Close", "next_steps"),
	("Last Updated", "modified"), ("Lost Reason", "lost_reason"), ("Priority", "priority"),
	("Contact Name", "contact_name"), ("Phone", "phone"), ("Email", "email"),
	("Location / Address", "location_address"), ("License #", "license_number"), ("Customer", "customer"),
	("Win Probability %", "probability"), ("Weighted Value", "weighted_value"), ("Next Follow-up", "next_step_due"),
	("Sample Date", "sample_date"), ("Expected Close", "expected_close"), ("Delivery / Pickup", "delivery_pickup"),
	("Fulfillment Notes", "fulfillment_notes"), ("Ops Notes", "ops_notes"), ("Payment Terms", "payment_terms"),
	("Lead Source", "lead_source"), ("ID", "name"),
]


def _settings_payload(s):
	return {
		"stages": s.stages,
		"first_stage": s.first_stage,
		"owners": [o for o in s.owners if o.active],
		"all_owners": s.owners,
		"product_lines": s.product_line_names,
		"lists": s.lists,
		"hide_closed_after_days": s.hide_closed_after_days,
	}


@frappe.whitelist()
def get_form_settings():
	frappe.has_permission(DT, "read", throw=True)
	s = sales_ops.get_settings()
	return {"stages": s.stages, "first_stage": s.first_stage}


@frappe.whitelist()
def get_board():
	frappe.has_permission(DT, "read", throw=True)
	s = sales_ops.get_settings()
	if not s.stages:
		frappe.throw(_("Set up stages in Sales Pipeline Settings first."))
	today = getdate(nowdate())
	stock = sales_ops.stock_map(s)
	deals = frappe.get_list(DT, fields=FIELDS, order_by="creation asc", limit_page_length=0)
	for d in deals:
		sales_ops.enrich(d, s, today, stock)
	user = frappe.session.user
	return {
		"today": str(today),
		"user": user,
		"is_manager": sales_ops.is_manager(user),
		"is_owner": any(o.user == user and o.active for o in s.owners),
		"settings": _settings_payload(s),
		"deals": deals,
		"can_write": bool(frappe.has_permission(DT, "write")),
		"can_create": bool(frappe.has_permission(DT, "create")),
		"can_quote": bool(frappe.has_permission("Quotation", "create")),
		"can_settings": sales_ops.is_manager(user) and bool(frappe.has_permission(sales_ops.SETTINGS, "write")),
	}


@frappe.whitelist()
def update_deal(name, values):
	"""Apply a small change from the page; the deal's validate() enforces every rule."""
	if isinstance(values, str):
		values = json.loads(values)
	bad = set(values) - EDITABLE
	if bad:
		frappe.throw(_("These fields cannot be changed from the board: {0}").format(", ".join(sorted(bad))))
	doc = frappe.get_doc(DT, name)
	doc.check_permission("write")
	for key, value in values.items():
		if isinstance(value, str):
			value = value.strip()
		if value in ("", None):
			value = None
		elif key in DATE_FIELDS:
			value = str(getdate(value))
		doc.set(key, value)
	doc.save()
	return doc.name


@frappe.whitelist()
def add_note(name, note):
	doc = frappe.get_doc(DT, name)
	doc.check_permission("read")
	note = (note or "").strip()
	if not note:
		frappe.throw(_("Please type a note first."))
	doc.add_comment("Comment", frappe.utils.escape_html(note).replace("\n", "<br>"))
	sales_ops.publish_board_update(name)
	return name


@frappe.whitelist()
def get_activity(name):
	doc = frappe.get_doc(DT, name)
	doc.check_permission("read")
	comments = frappe.get_all(
		"Comment",
		filters={"reference_doctype": DT, "reference_name": name, "comment_type": ("in", ["Comment", "Info"])},
		fields=["name", "comment_type", "content", "owner", "creation"],
		order_by="creation desc",
		limit_page_length=200,
	)
	items = [
		{"kind": "comment" if c.comment_type == "Comment" else "info", "content": c.content,
		 "by": frappe.utils.get_fullname(c.owner), "on": str(c.creation)}
		for c in comments
	]
	for r in doc.get("stage_log") or []:
		items.append({
			"kind": "stage", "from_stage": r.from_stage, "to_stage": r.to_stage,
			"days": flt(r.days_in_previous), "by": frappe.utils.get_fullname(r.changed_by), "on": str(r.changed_on),
		})
	items.sort(key=lambda x: x["on"], reverse=True)
	return items


@frappe.whitelist()
def make_quotation(name):
	"""Unsaved Quotation for the deal's Customer: item from Product Line + Tier, qty = grams, rate = price per gram."""
	doc = frappe.get_doc(DT, name)
	doc.check_permission("read")
	frappe.has_permission("Quotation", "create", throw=True)
	if not doc.customer:
		frappe.throw(_("Link a Customer to this deal before creating a Quotation."))
	s = sales_ops.get_settings()
	row = sales_ops.product_row(s, doc.product_line, doc.tier)
	q = frappe.new_doc("Quotation")
	q.quotation_to = "Customer"
	q.party_name = doc.customer
	message = None
	if row and row.quotation_item and flt(doc.total_grams):
		q.append("items", {"item_code": row.quotation_item, "qty": flt(doc.total_grams), "rate": flt(doc.price_per_gram)})
	elif not (row and row.quotation_item):
		message = _("No Quotation Item is set for {0} in Sales Pipeline Settings. Add the item on the Quotation.").format(
			" ".join(x for x in (doc.product_line, doc.tier) if x) or _("this deal"))
	q.run_method("set_missing_values")
	for it in q.get("items") or []:
		it.rate = flt(doc.price_per_gram)
	q.run_method("calculate_taxes_and_totals")
	out = q.as_dict(convert_dates_to_str=True)
	out["__islocal"] = 1
	for it in out.get("items") or []:
		it["__islocal"] = 1
		it["parent"] = None
		it["name"] = None
	return {"doc": out, "message": message}


@frappe.whitelist()
def export_xlsx(names):
	from frappe.utils.xlsxutils import make_xlsx

	if isinstance(names, str):
		names = json.loads(names)
	frappe.has_permission(DT, "read", throw=True)
	s = sales_ops.get_settings()
	rows = frappe.get_list(DT, fields=FIELDS, filters={"name": ("in", names or [""])}, limit_page_length=0)
	order = {n: i for i, n in enumerate(names or [])}
	rows.sort(key=lambda r: order.get(r.name, 0))
	data = [[c[0] for c in EXPORT_COLUMNS]]
	for r in rows:
		st = sales_ops.stage_info(s, r.stage)
		r.probability = st.probability if st else 0
		r.weighted_value = flt(r.deal_value) * flt(r.probability) / 100.0
		r.owner_name = sales_ops.owner_label(s, r.deal_owner) if r.deal_owner else ""
		line = []
		for _label, key in EXPORT_COLUMNS:
			v = r.get(key)
			if key == "modified" and v:
				v = frappe.utils.format_datetime(v)
			elif key in DATE_FIELDS and v:
				v = getdate(v)
			line.append("" if v is None else v)
		data.append(line)
	xlsx = make_xlsx(data, "Pipeline")
	frappe.response["filename"] = "Sales_Pipeline_{0}.xlsx".format(nowdate())
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"
