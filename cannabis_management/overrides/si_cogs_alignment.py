"""Post a Delivery Note's stock GL against its Sales Invoice instead.

Requested by Finance so that revenue and its matching COGS land in the same
period. Core ERPNext posts the stock side (Inventory credit / COGS debit) on
the Delivery Note's own date and voucher; here those rows are restamped with
the linked Sales Invoice's posting date, voucher type and voucher number. The
amounts and accounts are untouched -- only where the entry is filed changes.

What this costs, so it is written down somewhere
───────────────────────────────────────────────
* The Stock Ledger Entry still sits on the Delivery Note and its own date. The
  "Stock Ledger vs General Ledger" variance report compares the two and will
  now show the gap as a difference. That is inherent to the request, not a bug
  to be fixed later.
* `repost_gle_for_stock_vouchers` finds and deletes GL rows by the *stock*
  voucher's type and number, then posts a fresh set. Restamped rows are
  invisible to that delete, so without help every valuation repost would book
  the COGS a second time. CMDeliveryNote.make_gl_entries deletes this note's
  restamped rows itself before a repost writes the new ones.
* A note submitted before its invoice has nothing to align to yet. Its rows
  are moved when the invoice is submitted, and moved back to the note if that
  invoice is cancelled (see CMSalesInvoice).
* Core's cancel path looks up GL by (doctype, name) and would therefore find
  nothing to reverse. That is why every restamped row carries the origin
  fields below -- they are what makes the document cancellable again.

The origin fields are the whole safety net. Without them a restamped row is
indistinguishable from one the Sales Invoice posted itself, and cancelling
either document would do the wrong thing.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ORIGIN_TYPE_FIELD = "custom_origin_voucher_type"
ORIGIN_NO_FIELD = "custom_origin_voucher_no"

# Finance asked for this for these companies only. Every other company keeps
# core's behaviour: stock GL on the Delivery Note's own date and voucher.
ALIGNED_COMPANIES = ("Motley Terpz", "Master Touch Manufacturing")


def install_custom_fields():
	"""Idempotent; re-asserted on every migrate via after_migrate."""
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
	"""Return the submitted Sales Invoice a Delivery Note's GL should file under.

	Returns None when the entry must stay on the Delivery Note, which is the
	safe default. Deliberately refuses to guess in two cases:

	* No invoice at all -- nothing to align to.
	* More than one invoice -- the stock GL is a single set of warehouse and
	  COGS rows covering the whole note, and splitting it across invoices by
	  value is a different (and reversible-by-nobody) decision. Finance should
	  see these rather than have them quietly apportioned.
	"""
	if doc.get("company") not in ALIGNED_COMPANIES:
		return None

	invoices = set()

	# This site bills first and ships after, so the link lives on the Delivery
	# Note row. Checked first because it is the populated one here.
	for row in doc.get("items") or []:
		si = row.get("against_sales_invoice")
		if si:
			invoices.add(si)

	# The other direction, for notes raised before their invoice.
	if not invoices:
		for si in frappe.get_all(
			"Sales Invoice Item",
			filters={"delivery_note": doc.name, "docstatus": 1},
			pluck="parent",
		):
			invoices.add(si)

	# Both billed off the Sales Order with no direct link between them.
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
	# Cross-company would move the entry into a ledger it does not belong to.
	if si.company != doc.company:
		return None
	# A return note can still point at the original invoice; filing the
	# reversal on that invoice's date would put it in the wrong period.
	if bool(si.is_return) != bool(doc.get("is_return")):
		return None

	return si


def invoice_voucher_subtype(sales_invoice):
	"""The subtype core gives a Sales Invoice's own rows (get_voucher_subtype)."""
	is_return, is_debit_note = frappe.db.get_value(
		"Sales Invoice", sales_invoice, ["is_return", "is_debit_note"]
	)
	if is_return:
		return "Credit Note"
	if is_debit_note:
		return "Debit Note"
	return "Sales Invoice"


def note_voucher_subtype(delivery_note):
	"""The subtype core gives a Delivery Note's own rows."""
	if frappe.db.get_value("Delivery Note", delivery_note, "is_return"):
		return "Sales Return"
	return "Delivery Note"


def invoices_via_sales_order(delivery_note):
	"""Invoices that billed the same Sales Order lines this note delivered.

	Only trusted when that order has no other submitted note: with two notes
	against one order there is no telling which delivery an invoice covers.
	"""
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
	"""Restamp a note's live GL rows, still filed under the note, onto `si`.

	Only posting_date, fiscal_year and the voucher change; amounts and
	accounts stay as they are. Returns the number of rows moved.
	"""
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
	"""Undo move_to_invoice for every note filed under `sales_invoice`.

	Used when the invoice is cancelled: the note is unbilled again, so its
	stock GL goes back to the note's own date and voucher, as core posts it.
	"""
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
	"""Drop a note's restamped rows ahead of a repost that rewrites them.

	Mirrors core's _delete_gl_entries, which only sees rows still filed under
	the note itself.
	"""
	frappe.db.sql(
		"DELETE FROM `tabGL Entry` WHERE `{otype}` = %s AND `{ono}` = %s AND is_cancelled = 0".format(
			otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD
		),
		(origin_type, origin_no),
	)
