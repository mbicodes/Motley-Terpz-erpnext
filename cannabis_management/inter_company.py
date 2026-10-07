# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Inter-company counterparts: a sale to an internal customer raises the matching
purchase document in the buying company.

    Sales Order    -> Purchase Order
    Sales Invoice  -> Purchase Invoice
    Delivery Note  -> Purchase Receipt

ERPNext already knows how to map these (make_inter_company_*), including
picking the Supplier that represents the selling company, so that is driven
rather than reimplemented. What this adds is the Company / Warehouse / Project
the buying side needs, collected in a dialog before submit.

Called from the selling document's client-side on_submit, which means it runs
in its own request: if the counterpart fails to build, the sale stays submitted
and the error is reported, rather than the whole submit rolling back.
"""

import frappe
from frappe import _

# source doctype -> (target doctype, ERPNext maker)
COUNTERPARTS = {
	"Sales Order": (
		"Purchase Order",
		"erpnext.selling.doctype.sales_order.sales_order.make_inter_company_purchase_order",
	),
	"Sales Invoice": (
		"Purchase Invoice",
		"erpnext.accounts.doctype.sales_invoice.sales_invoice.make_inter_company_purchase_invoice",
	),
	"Delivery Note": (
		"Purchase Receipt",
		"erpnext.stock.doctype.delivery_note.delivery_note.make_inter_company_purchase_receipt",
	),
}


@frappe.whitelist()
def is_internal_customer(customer):
	"""Used by the client to decide whether to show the dialog at all."""
	if not customer:
		return {"internal": False}
	row = frappe.db.get_value(
		"Customer", customer, ["is_internal_customer", "represents_company"], as_dict=True
	) or {}
	return {
		"internal": bool(row.get("is_internal_customer")),
		"represents_company": row.get("represents_company"),
	}


@frappe.whitelist()
def create_counterpart(doctype, name, company, warehouse, project):
	if doctype not in COUNTERPARTS:
		frappe.throw(_("{0} has no inter-company counterpart.").format(doctype))

	for label, value in (("Company", company), ("Warehouse", warehouse), ("Project", project)):
		if not value:
			frappe.throw(_("{0} is required to raise the inter-company document.").format(label))

	source = frappe.get_doc(doctype, name)
	if not frappe.db.get_value("Customer", source.customer, "is_internal_customer"):
		frappe.throw(_("{0} is not an internal customer.").format(source.customer))

	target_doctype, maker = COUNTERPARTS[doctype]

	# Don't raise a second one for the same source document.
	existing = _existing_counterpart(target_doctype, doctype, name)
	if existing:
		return {"doctype": target_doctype, "name": existing, "already_existed": True}

	target = frappe.get_attr(maker)(name)

	target.company = company
	if target.meta.has_field("project"):
		target.project = project
	if target.meta.has_field("set_warehouse"):
		target.set_warehouse = warehouse

	# ERPNext's mapper does not carry a delivery date across to the Purchase
	# Order's "Reqd by Date", which is mandatory — fill it from the sale.
	fallback_date = (
		source.get("delivery_date")
		or source.get("schedule_date")
		or source.get("posting_date")
		or source.get("transaction_date")
		or frappe.utils.nowdate()
	)
	if target.meta.has_field("schedule_date") and not target.get("schedule_date"):
		target.schedule_date = fallback_date

	for row in target.get("items") or []:
		if row.meta.has_field("schedule_date") and not row.get("schedule_date"):
			row.schedule_date = (
				source.get("items")[0].get("delivery_date")
				if source.get("items") and source.get("items")[0].get("delivery_date")
				else fallback_date
			)
		if row.meta.has_field("warehouse"):
			row.warehouse = warehouse
		if row.meta.has_field("project"):
			row.project = project
		# Cost centre and expense account are company-scoped; clearing lets
		# ERPNext refill them for the company chosen in the dialog.
		for field in ("cost_center", "expense_account"):
			if row.meta.has_field(field):
				row.set(field, None)

	target.flags.ignore_permissions = True
	target.insert()
	target.submit()

	_link_back(source, target)

	frappe.msgprint(
		_("{0} {1} created and submitted.").format(
			_(target_doctype), frappe.utils.get_link_to_form(target_doctype, target.name)
		),
		title=_("Inter-company document raised"),
		indicator="green",
	)
	return {"doctype": target_doctype, "name": target.name, "already_existed": False}


def _existing_counterpart(target_doctype, source_doctype, source_name):
	"""ERPNext stamps the originating document on the target's items."""
	field = {
		"Sales Order": "sales_order",
		"Sales Invoice": "sales_invoice",     # Purchase Invoice Item
		"Delivery Note": "delivery_note_item",
	}
	child = f"{target_doctype} Item"
	link = "inter_company_order_reference" if target_doctype == "Purchase Order" else None

	if link and frappe.get_meta(target_doctype).has_field(link):
		return frappe.db.get_value(
			target_doctype, {link: source_name, "docstatus": ["<", 2]}, "name"
		)

	ref = "inter_company_invoice_reference"
	if frappe.get_meta(target_doctype).has_field(ref):
		return frappe.db.get_value(
			target_doctype, {ref: source_name, "docstatus": ["<", 2]}, "name"
		)
	return None


# Reference field pairs, by document family.
_REF_FIELD = {
	"Sales Order": "inter_company_order_reference",
	"Sales Invoice": "inter_company_invoice_reference",
	"Delivery Note": "inter_company_reference",
}


def _link_back(source, target):
	"""Point the selling document at the purchase document it raised.

	ERPNext only fills one side. Its update_linked_doc passes the *current*
	doctype when writing the reverse reference (see sales_invoice.py:2101), so
	it tries to update e.g. a Purchase Order whose name is a Sales Order's — no
	such row, no error, no link. Setting it here gives both documents a
	reference to each other, which is what makes the Connections tab work from
	either side.
	"""
	field = _REF_FIELD.get(source.doctype)
	if not field or not source.meta.has_field(field):
		return
	if source.get(field):
		return
	frappe.db.set_value(source.doctype, source.name, field, target.name, update_modified=False)
