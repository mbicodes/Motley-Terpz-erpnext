import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import getdate

ORIGIN_TYPE_FIELD = "custom_origin_voucher_type"
ORIGIN_NO_FIELD = "custom_origin_voucher_no"

ALIGNED_COMPANIES = ("Motley Terpz", "Master Touch Manufacturing")

ALIGN_UNTIL = "2026-09-24"


def install_custom_fields():
	create_custom_fields(
		{
			"GL Entry": [
				{
					"fieldname": ORIGIN_TYPE_FIELD,
					"label": "Origin Voucher Type",
					"fieldtype": "Data",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "voucher_no",
					"description": (
						"Set when this entry was posted by one document but filed under "
						"another -- a Delivery Note's stock entry filed under its Sales "
						"Invoice. Blank means the voucher above really did post it."
					),
				},
				{
					"fieldname": ORIGIN_NO_FIELD,
					"label": "Origin Voucher No",
					"fieldtype": "Data",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": ORIGIN_TYPE_FIELD,
					"search_index": 1,
				},
			]
		},
		ignore_validate=True,
	)


def get_linked_sales_invoice(doc):
	if doc.get("company") not in ALIGNED_COMPANIES:
		return None
	if not doc.get("posting_date") or getdate(doc.get("posting_date")) > getdate(ALIGN_UNTIL):
		return None

	invoices = set()

	for row in doc.get("items") or []:
		si = row.get("against_sales_invoice")
		if si:
			invoices.add(si)

	if not invoices:
		for si in frappe.get_all(
			"Sales Invoice Item",
			filters={"delivery_note": doc.name, "docstatus": 1},
			pluck="parent",
		):
			invoices.add(si)

	if not invoices:
		invoices = invoices_via_sales_order(doc.name)

	if len(invoices) != 1:
		return None

	si_name = invoices.pop()
	si = frappe.db.get_value(
		"Sales Invoice",
		si_name,
		["name", "posting_date", "docstatus", "company", "is_return"],
		as_dict=True,
	)
	if not si or si.docstatus != 1:
		return None
	if si.company != doc.company:
		return None
	if bool(si.is_return) != bool(doc.get("is_return")):
		return None

	return si


def invoice_voucher_subtype(sales_invoice):
	is_return, is_debit_note = frappe.db.get_value(
		"Sales Invoice", sales_invoice, ["is_return", "is_debit_note"]
	)
	if is_return:
		return "Credit Note"
	if is_debit_note:
		return "Debit Note"
	return "Sales Invoice"


def note_voucher_subtype(delivery_note):
	if frappe.db.get_value("Delivery Note", delivery_note, "is_return"):
		return "Sales Return"
	return "Delivery Note"


def invoices_via_sales_order(delivery_note):
	rows = frappe.get_all(
		"Delivery Note Item",
		filters={"parent": delivery_note},
		fields=["so_detail", "against_sales_order"],
	)
	lines = [r.so_detail for r in rows if r.so_detail]
	orders = list({r.against_sales_order for r in rows if r.against_sales_order})
	if not lines or not orders:
		return set()

	other_notes = frappe.get_all(
		"Delivery Note Item",
		filters={
			"against_sales_order": ("in", orders),
			"docstatus": 1,
			"parent": ("!=", delivery_note),
		},
		pluck="parent",
		limit=1,
	)
	if other_notes:
		return set()

	return set(
		frappe.get_all(
			"Sales Invoice Item",
			filters={"so_detail": ("in", lines), "docstatus": 1},
			pluck="parent",
		)
	)


def move_to_invoice(delivery_note, si):
	from erpnext.accounts.utils import get_fiscal_year

	names = frappe.get_all(
		"GL Entry",
		filters={
			"voucher_type": "Delivery Note",
			"voucher_no": delivery_note,
			"is_cancelled": 0,
			ORIGIN_NO_FIELD: ("is", "not set"),
		},
		pluck="name",
	)
	if not names:
		return 0

	company = frappe.db.get_value("Sales Invoice", si.name, "company")
	frappe.db.sql(
		"""
		UPDATE `tabGL Entry`
		SET posting_date = %(posting_date)s,
		    fiscal_year  = %(fiscal_year)s,
		    voucher_type = 'Sales Invoice',
		    voucher_no   = %(voucher_no)s,
		    voucher_subtype = %(voucher_subtype)s,
		    `{otype}`    = 'Delivery Note',
		    `{ono}`      = %(origin_no)s
		WHERE name IN %(names)s
		""".format(otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD),
		{
			"posting_date": si.posting_date,
			"fiscal_year": get_fiscal_year(si.posting_date, company=company)[0],
			"voucher_no": si.name,
			"voucher_subtype": invoice_voucher_subtype(si.name),
			"origin_no": delivery_note,
			"names": tuple(names),
		},
	)
	return len(names)


def move_back_to_delivery_notes(sales_invoice):
	from erpnext.accounts.utils import get_fiscal_year

	rows = frappe.get_all(
		"GL Entry",
		filters={
			"voucher_type": "Sales Invoice",
			"voucher_no": sales_invoice,
			"is_cancelled": 0,
			ORIGIN_TYPE_FIELD: "Delivery Note",
		},
		fields=["name", ORIGIN_NO_FIELD + " as dn", "company"],
	)
	by_note = {}
	for r in rows:
		by_note.setdefault((r.dn, r.company), []).append(r.name)

	for (dn, company), names in by_note.items():
		posting_date = frappe.db.get_value("Delivery Note", dn, "posting_date")
		frappe.db.sql(
			"""
			UPDATE `tabGL Entry`
			SET posting_date = %(posting_date)s,
			    fiscal_year  = %(fiscal_year)s,
			    voucher_type = 'Delivery Note',
			    voucher_no   = %(dn)s,
			    voucher_subtype = %(voucher_subtype)s,
			    `{otype}`    = NULL,
			    `{ono}`      = NULL
			WHERE name IN %(names)s
			""".format(otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD),
			{
				"posting_date": posting_date,
				"fiscal_year": get_fiscal_year(posting_date, company=company)[0],
				"dn": dn,
				"voucher_subtype": note_voucher_subtype(dn),
				"names": tuple(names),
			},
		)
	return sorted(dn for dn, _ in by_note)


def delete_origin_rows(origin_type, origin_no):
	frappe.db.sql(
		"DELETE FROM `tabGL Entry` WHERE `{otype}` = %s AND `{ono}` = %s AND is_cancelled = 0".format(
			otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD
		),
		(origin_type, origin_no),
	)
