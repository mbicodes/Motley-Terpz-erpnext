"""Re-file already-posted Delivery Note stock GL under its Sales Invoice.

The companion to overrides/si_cogs_alignment.py, which does this for new
documents. This one rewrites history: entries already sitting on a Delivery
Note's date and voucher are moved onto the linked Sales Invoice's date and
voucher, so revenue and its COGS report in the same period.

Amounts, accounts, cost centres and dimensions are untouched. Only
posting_date, fiscal_year, voucher_type and voucher_no change, plus the origin
stamps that record where the row actually came from.

Run it, from the bench directory:

    # see what it would do -- changes nothing
    bench --site <site> execute \
        cannabis_management.patches.align_dn_gl_to_sales_invoice.execute

    # do it
    bench --site <site> execute \
        cannabis_management.patches.align_dn_gl_to_sales_invoice.execute \
        --kwargs "{'apply': True}"

Read this before running it with apply=True
───────────────────────────────────────────
* GL Entry is append-only in ERPNext. Everything else cancels and re-posts;
  this edits submitted rows in place, which is what was asked for and which no
  ERPNext feature will undo. Every affected row is written to a JSON backup
  first -- keep it.
* The Stock Ledger Entry stays on the Delivery Note and its own date. After
  this runs, the Inventory account balance at a date no longer matches the
  Stock Ledger at that date, and the "Stock Ledger vs General Ledger" variance
  report will show the gap permanently.
* Rows are only moved when exactly one submitted Sales Invoice is linked, in
  the same company. Anything else is reported and left alone -- splitting one
  note's stock GL across several invoices is a judgement call, not a migration.
* Run the dry run, hand the summary to Finance, and only then apply.
"""

import json
import os

import frappe

from cannabis_management.overrides.si_cogs_alignment import (
	ALIGNED_COMPANIES,
	ORIGIN_NO_FIELD,
	ORIGIN_TYPE_FIELD,
	invoice_voucher_subtype,
	invoices_via_sales_order,
)

DEFAULT_FROM = "2026-01-01"
DEFAULT_TO = "2026-06-30"


def execute(from_date=DEFAULT_FROM, to_date=DEFAULT_TO, apply=False, backup_dir=None):
	apply = bool(apply)

	rows = frappe.db.sql(
		"""
		SELECT name, voucher_no, posting_date, account, debit, credit, company, fiscal_year
		FROM `tabGL Entry`
		WHERE voucher_type = 'Delivery Note'
		  AND is_cancelled = 0
		  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND IFNULL(`{origin}`, '') = ''
		  AND company IN %(companies)s
		ORDER BY voucher_no, name
		""".format(origin=ORIGIN_NO_FIELD),
		{"from_date": from_date, "to_date": to_date, "companies": ALIGNED_COMPANIES},
		as_dict=True,
	)

	print(
		"Delivery Note GL entries in {0} .. {1} for {2}: {3}".format(
			from_date, to_date, ", ".join(ALIGNED_COMPANIES), len(rows)
		)
	)
	if not rows:
		print("Nothing to do.")
		return

	planned, skipped = [], []
	invoice_cache = {}

	for row in rows:
		target = _resolve_invoice(row.voucher_no, invoice_cache)
		if isinstance(target, str):
			skipped.append((row.voucher_no, row.name, target))
			continue
		if target.company != row.company:
			skipped.append((row.voucher_no, row.name, "invoice belongs to another company"))
			continue
		planned.append((row, target))

	_report(planned, skipped)

	if not planned:
		return

	if not apply:
		print("\nDry run -- nothing was changed. Re-run with --kwargs \"{'apply': True}\".")
		return

	backup_path = _write_backup(planned, backup_dir)
	print("\nBackup of the original rows: {0}".format(backup_path))

	from erpnext.accounts.utils import get_fiscal_year

	moved = 0
	for row, si in planned:
		fiscal_year = get_fiscal_year(si.posting_date, company=row.company)[0]
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
			WHERE name = %(name)s
			""".format(otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD),
			{
				"posting_date": si.posting_date,
				"fiscal_year": fiscal_year,
				"voucher_no": si.name,
				"voucher_subtype": invoice_voucher_subtype(si.name),
				"origin_no": row.voucher_no,
				"name": row.name,
			},
		)
		moved += 1

	frappe.db.commit()
	print("\nMoved {0} GL entries onto their Sales Invoices.".format(moved))
	print("The Stock Ledger still sits on the Delivery Note dates -- the stock/GL")
	print("variance report will show that gap from now on.")


def _resolve_invoice(delivery_note, cache):
	"""Return the target invoice, or a string explaining why the row stays put."""
	if delivery_note in cache:
		return cache[delivery_note]

	invoices = set(
		frappe.get_all(
			"Delivery Note Item",
			filters={"parent": delivery_note, "against_sales_invoice": ("is", "set")},
			pluck="against_sales_invoice",
		)
	)
	if not invoices:
		invoices = set(
			frappe.get_all(
				"Sales Invoice Item",
				filters={"delivery_note": delivery_note, "docstatus": 1},
				pluck="parent",
			)
		)

	if not invoices:
		invoices = invoices_via_sales_order(delivery_note)

	if not invoices:
		result = "no Sales Invoice linked"
	elif len(invoices) > 1:
		result = "linked to {0} invoices -- needs a manual decision".format(len(invoices))
	else:
		si = frappe.db.get_value(
			"Sales Invoice", invoices.pop(), ["name", "posting_date", "docstatus", "company", "is_return"],
			as_dict=True,
		)
		is_return = frappe.db.get_value("Delivery Note", delivery_note, "is_return")
		if not si:
			result = "linked invoice no longer exists"
		elif si.docstatus != 1:
			result = "linked invoice is not submitted"
		elif bool(si.is_return) != bool(is_return):
			result = "return note linked to a non-return invoice (or the reverse)"
		else:
			result = si

	cache[delivery_note] = result
	return result


def _report(planned, skipped):
	notes = {r.voucher_no for r, _ in planned}
	print("\nWould move: {0} rows across {1} delivery notes".format(len(planned), len(notes)))

	# Month-on-month effect is what Finance actually needs to see, and only the
	# COGS leg moves the P&L -- the inventory leg is its mirror image, so
	# counting both nets every line to zero and says nothing.
	cogs_accounts = set(
		frappe.get_all("Account", filters={"account_type": "Cost of Goods Sold"}, pluck="name")
	)

	shifts = {}
	for row, si in planned:
		a, b = str(row.posting_date)[:7], str(si.posting_date)[:7]
		if a == b or row.account not in cogs_accounts:
			continue
		key = (a, b)
		shifts.setdefault(key, [0, 0.0])
		shifts[key][0] += 1
		shifts[key][1] += float(row.debit or 0) - float(row.credit or 0)

	if shifts:
		print("\nCOGS crossing a month end (P&L effect):")
		per_month = {}
		for (a, b), (n, amt) in sorted(shifts.items()):
			print("  {0} -> {1}   {2:4d} rows   {3:>14,.2f}".format(a, b, n, amt))
			per_month[a] = per_month.get(a, 0.0) - amt
			per_month[b] = per_month.get(b, 0.0) + amt
		print("\n  Net change in COGS by month:")
		for month in sorted(per_month):
			print("    {0}   {1:>14,.2f}".format(month, per_month[month]))

	if skipped:
		print("\nLeft alone: {0} rows".format(len(skipped)))
		seen = {}
		for dn, _name, reason in skipped:
			seen.setdefault(reason, set()).add(dn)
		for reason, dns in sorted(seen.items()):
			sample = ", ".join(sorted(dns)[:5])
			more = "" if len(dns) <= 5 else " (+{0} more)".format(len(dns) - 5)
			print("  {0}: {1} notes -- {2}{3}".format(reason, len(dns), sample, more))


def _write_backup(planned, backup_dir):
	backup_dir = backup_dir or frappe.get_site_path("private", "files")
	os.makedirs(backup_dir, exist_ok=True)
	path = os.path.join(
		backup_dir,
		"gl_dn_to_si_backup_{0}.json".format(frappe.utils.now().replace(" ", "_").replace(":", "")),
	)

	names = [row.name for row, _ in planned]
	original = frappe.db.sql(
		"SELECT * FROM `tabGL Entry` WHERE name IN %(names)s", {"names": names}, as_dict=True
	)
	with open(path, "w") as fh:
		json.dump(original, fh, indent=1, default=str)
	return path
