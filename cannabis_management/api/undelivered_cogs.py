"""COGS for invoiced but undelivered quantity.

Finance wants every billed unit to carry COGS in the period it was invoiced,
whether or not it has shipped. Shipped units already have COGS through the
Delivery Note (or the invoice itself with Update Stock). For the rest this
posts a Journal Entry, dated on the invoice:

    Dr  COGS (the invoice line's expense account)
    Cr  Stock Adjustment Account (company default)

No Stock Ledger Entry is made and no stock leaves a warehouse -- the
undelivered units exist in the accounts only.

How "delivered" is worked out, per Sales Invoice line (stock UOM):

* Update Stock invoices: the line's own Stock Ledger Entries.
* Delivery Note tied to the line directly, either way round (DN made from
  the SI -> dni.si_detail, SI made from the DN -> sii.dn_detail).
* Otherwise, both raised off the same Sales Order line: that line's delivered
  quantity (on notes not tied to any invoice line directly) is handed out to
  its invoices oldest first. Invoices before the period count too, so an
  earlier invoice keeps first claim on what was shipped.

Delivery Note returns are netted off the note they return; credit notes are
netted off the invoice line they credit. Non-stock items and drop-shipped
lines are left alone.

Re-running is safe: each posted unit is recorded on its Journal Entry row
(custom_si_detail / custom_cogs_qty) and subtracted the next time.

General Ledger: the Journal Entry stays the source document (it is what gets
cancelled and what carries the tracking), but its GL rows are filed under the
Sales Invoice's own voucher -- the same restamp Delivery Note stock GL gets in
overrides/si_cogs_alignment.py, with origin stamps naming the Journal Entry.
The invoice's General Ledger then shows its revenue and all of its COGS.
Before the Journal Entry cancels, its rows are handed back to it so core's
reversal finds them.

Finance asked for this for Motley Terpz only (COMPANIES).
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import flt, get_datetime

from cannabis_management.overrides.si_cogs_alignment import (
	ORIGIN_NO_FIELD,
	ORIGIN_TYPE_FIELD,
	invoice_voucher_subtype,
)

COMPANIES = ("Motley Terpz",)

JE_INVOICE_FIELD = "custom_undelivered_cogs_invoice"
ROW_LINE_FIELD = "custom_si_detail"
ROW_QTY_FIELD = "custom_cogs_qty"

QTY_TOLERANCE = 0.0001
MANAGER_ROLES = ("Accounts Manager", "System Manager")


def install_custom_fields():
	"""Idempotent; re-asserted on every migrate via after_migrate."""
	create_custom_fields(
		{
			"Journal Entry": [
				{
					"fieldname": JE_INVOICE_FIELD,
					"label": "Undelivered COGS For Invoice",
					"fieldtype": "Link",
					"options": "Sales Invoice",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "company",
					"search_index": 1,
					"description": "Set on COGS entries for invoiced quantity that has no Stock Ledger Entry.",
				},
			],
			"Journal Entry Account": [
				{
					"fieldname": ROW_LINE_FIELD,
					"label": "Sales Invoice Item",
					"fieldtype": "Data",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": "cost_center",
					"search_index": 1,
				},
				{
					"fieldname": ROW_QTY_FIELD,
					"label": "COGS Qty",
					"fieldtype": "Float",
					"read_only": 1,
					"no_copy": 1,
					"insert_after": ROW_LINE_FIELD,
				},
			],
		},
		ignore_validate=True,
	)


# ── calculation ─────────────────────────────────────────────────────────────


def _check_company(company):
	if company not in COMPANIES:
		frappe.throw(_("Undelivered COGS is only set up for {0}").format(", ".join(COMPANIES)))


def _ensure_fields():
	"""Create the tracking fields if a deploy skipped `bench migrate`."""
	if not (
		frappe.db.has_column("Journal Entry Account", ROW_LINE_FIELD)
		and frappe.db.has_column("Journal Entry Account", ROW_QTY_FIELD)
		and frappe.db.has_column("Journal Entry", JE_INVOICE_FIELD)
	):
		install_custom_fields()
		frappe.clear_cache(doctype="Journal Entry")
		frappe.clear_cache(doctype="Journal Entry Account")


def get_lines(company, from_date, to_date):
	"""One dict per stock line of the period's invoices, with the gap worked out."""
	_check_company(company)
	_ensure_fields()
	lines = frappe.db.sql(
		"""
		SELECT si.name AS sales_invoice, si.posting_date, si.posting_time, si.update_stock,
			si.customer, si.company, sii.name AS si_detail, sii.idx, sii.item_code, sii.item_name,
			sii.stock_qty, sii.warehouse, sii.expense_account, sii.cost_center,
			sii.so_detail, sii.sales_order, sii.dn_detail, sii.delivery_note
		FROM `tabSales Invoice` si
		JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		JOIN `tabItem` item ON item.name = sii.item_code
		WHERE si.docstatus = 1 AND si.is_return = 0 AND si.company = %(company)s
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND item.is_stock_item = 1 AND IFNULL(sii.delivered_by_supplier, 0) = 0
		ORDER BY si.posting_date, si.posting_time, si.name, sii.idx
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	if not lines:
		return []

	details = [l.si_detail for l in lines]
	credited = _credited_qty(details)
	for l in lines:
		l.invoiced_qty = flt(l.stock_qty) + flt(credited.get(l.si_detail))

	delivered, delivered_value, source = _delivered(lines, details)
	recognized = _already_recognized(details)

	# Some lines carry a balance-sheet account (e.g. a WIP stock account) as
	# their expense account. COGS must land in P&L, so those fall back to the
	# company's default COGS account.
	default_cogs = frappe.get_cached_value("Company", company, "default_expense_account")
	accounts = {l.expense_account for l in lines if l.expense_account}
	expense = set(
		frappe.get_all(
			"Account", filters={"name": ("in", list(accounts) or [""]), "root_type": "Expense"}, pluck="name"
		)
	)

	for l in lines:
		l.delivered_qty = flt(delivered.get(l.si_detail), 6)
		l.delivery_source = source.get(l.si_detail) or ""
		l.cogs_account = l.expense_account if l.expense_account in expense else default_cogs
		l.recognized_qty = flt(recognized.get(l.si_detail))
		l.remaining_qty = flt(l.invoiced_qty - l.delivered_qty - l.recognized_qty, 6)
		l.rate, l.rate_source, l.amount = 0, "", 0
		if l.remaining_qty > QTY_TOLERANCE:
			l.rate, l.rate_source = _rate(l, delivered_value.get(l.si_detail))
			l.amount = flt(l.remaining_qty * l.rate, 2)
			l.status = "To Post" if l.amount else "No Valuation Rate"
		elif l.remaining_qty < -QTY_TOLERANCE and l.recognized_qty:
			# Shipped after its COGS was booked here: the note posted COGS
			# again. Left for Finance to reverse rather than guessed at.
			l.status = "Over-Recognized"
		elif l.remaining_qty < -QTY_TOLERANCE:
			l.status = "Over-Delivered"
		else:
			l.status = "Fully Covered"
	return lines


def _credited_qty(details):
	"""Credit-note quantity per original invoice line (negative)."""
	if not details:
		return {}
	return dict(
		frappe.db.sql(
			"""
			SELECT r.sales_invoice_item, SUM(r.stock_qty)
			FROM `tabSales Invoice Item` r
			JOIN `tabSales Invoice` rsi ON rsi.name = r.parent
			WHERE rsi.docstatus = 1 AND rsi.is_return = 1 AND r.sales_invoice_item IN %(d)s
			GROUP BY r.sales_invoice_item
			""",
			{"d": tuple(details)},
		)
	)


def _delivered(lines, details):
	"""Delivered qty, delivered stock value and a description, per invoice line."""
	delivered, value, source = {}, {}, {}

	def add(si_detail, qty, val, label):
		delivered[si_detail] = delivered.get(si_detail, 0) + qty
		value[si_detail] = value.get(si_detail, 0) + val
		if label:
			source[si_detail] = ", ".join(filter(None, [source.get(si_detail), label]))

	# 1. Update Stock invoices move stock themselves.
	own = [l.si_detail for l in lines if l.update_stock]
	if own:
		for d, qty, val in frappe.db.sql(
			"""
			SELECT voucher_detail_no, -SUM(actual_qty), -SUM(stock_value_difference)
			FROM `tabStock Ledger Entry`
			WHERE voucher_type = 'Sales Invoice' AND is_cancelled = 0
				AND voucher_detail_no IN %(d)s
			GROUP BY voucher_detail_no
			""",
			{"d": tuple(own)},
		):
			add(d, flt(qty), flt(val), "Update Stock")

	# 2. Delivery Notes tied to the invoice line directly.
	detail_set = set(details)
	by_dn_detail = {l.dn_detail: l.si_detail for l in lines if l.dn_detail}
	direct = frappe.db.sql(
		"""
		SELECT dni.name, dni.parent, dni.si_detail
		FROM `tabDelivery Note Item` dni
		JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dn.docstatus = 1 AND dn.is_return = 0
			AND (dni.si_detail IN %(d)s OR dni.name IN %(dn)s)
		""",
		{"d": tuple(details), "dn": tuple(by_dn_detail) or ("",)},
		as_dict=True,
	)
	direct_lines, note_rows = set(), {}
	for r in direct:
		target = r.si_detail if r.si_detail in detail_set else by_dn_detail.get(r.name)
		if target:
			note_rows[r.name] = (target, r.parent)
			direct_lines.add(target)
	for dni, (qty, val) in _note_qty(list(note_rows)).items():
		target, dn = note_rows[dni]
		add(target, qty, val, dn)

	# 3. Same Sales Order line, no direct link.
	so_details = list(
		{l.so_detail for l in lines if l.so_detail and not l.update_stock and l.si_detail not in direct_lines}
	)
	if so_details:
		_allocate_via_sales_order(so_details, add)

	return delivered, value, source


def _note_qty(dn_item_names):
	"""Net shipped qty and stock value per Delivery Note row, returns deducted."""
	if not dn_item_names:
		return {}
	out = {}
	# Stock value from the Stock Ledger so the rate matches what was booked.
	for d, qty, val in frappe.db.sql(
		"""
		SELECT voucher_detail_no, -SUM(actual_qty), -SUM(stock_value_difference)
		FROM `tabStock Ledger Entry`
		WHERE voucher_type = 'Delivery Note' AND is_cancelled = 0
			AND voucher_detail_no IN %(d)s
		GROUP BY voucher_detail_no
		""",
		{"d": tuple(dn_item_names)},
	):
		out[d] = [flt(qty), flt(val)]
	for d, qty, val in frappe.db.sql(
		"""
		SELECT ret.dn_detail, -SUM(sle.actual_qty), -SUM(sle.stock_value_difference)
		FROM `tabDelivery Note Item` ret
		JOIN `tabDelivery Note` rdn ON rdn.name = ret.parent
		JOIN `tabStock Ledger Entry` sle ON sle.voucher_type = 'Delivery Note'
			AND sle.voucher_detail_no = ret.name AND sle.is_cancelled = 0
		WHERE rdn.docstatus = 1 AND rdn.is_return = 1 AND ret.dn_detail IN %(d)s
		GROUP BY ret.dn_detail
		""",
		{"d": tuple(dn_item_names)},
	):
		row = out.setdefault(d, [0, 0])
		row[0] += flt(qty)
		row[1] += flt(val)
	return {k: tuple(v) for k, v in out.items()}


def _allocate_via_sales_order(so_details, add):
	"""Share each order line's delivered qty among its invoices, oldest first."""
	notes = frappe.db.sql(
		"""
		SELECT dni.name, dni.parent, dni.so_detail
		FROM `tabDelivery Note Item` dni
		JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dn.docstatus = 1 AND dn.is_return = 0 AND dni.so_detail IN %(s)s
			AND IFNULL(dni.si_detail, '') = ''
		""",
		{"s": tuple(so_details)},
		as_dict=True,
	)
	if notes:
		# A note row an invoice was made from belongs to that invoice alone.
		claimed = set(
			frappe.db.sql_list(
				"""
				SELECT sii.dn_detail FROM `tabSales Invoice Item` sii
				JOIN `tabSales Invoice` si ON si.name = sii.parent
				WHERE si.docstatus = 1 AND sii.dn_detail IN %(d)s
				""",
				{"d": tuple(n.name for n in notes)},
			)
		)
		notes = [n for n in notes if n.name not in claimed]

	qty_by_row = _note_qty([n.name for n in notes])
	pool = {}
	for n in notes:
		qty, val = qty_by_row.get(n.name, (0, 0))
		p = pool.setdefault(n.so_detail, {"qty": 0, "value": 0, "notes": set()})
		p["qty"] += qty
		p["value"] += val
		if qty:
			p["notes"].add(n.parent)

	# Every invoice line on these order lines, any date, that relies on the order.
	claimants = frappe.db.sql(
		"""
		SELECT sii.name, sii.so_detail, sii.stock_qty
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1 AND si.is_return = 0 AND si.update_stock = 0
			AND sii.so_detail IN %(s)s AND IFNULL(sii.dn_detail, '') = ''
			AND NOT EXISTS (
				SELECT 1 FROM `tabDelivery Note Item` dni
				JOIN `tabDelivery Note` dn ON dn.name = dni.parent
				WHERE dn.docstatus = 1 AND dni.si_detail = sii.name)
		ORDER BY si.posting_date, si.posting_time, si.creation, sii.idx
		""",
		{"s": tuple(so_details)},
		as_dict=True,
	)
	credited = _credited_qty([c.name for c in claimants])
	for c in claimants:
		p = pool.get(c.so_detail)
		if not p or p["qty"] <= QTY_TOLERANCE:
			continue
		take = min(flt(c.stock_qty) + flt(credited.get(c.name)), p["qty"])
		if take <= 0:
			continue
		unit = p["value"] / p["qty"]
		add(c.name, take, take * unit, "via SO: " + ", ".join(sorted(p["notes"])))
		p["value"] -= take * unit
		p["qty"] -= take


def _already_recognized(details):
	return dict(
		frappe.db.sql(
			"""
			SELECT jea.{line}, SUM(jea.{qty})
			FROM `tabJournal Entry Account` jea
			JOIN `tabJournal Entry` je ON je.name = jea.parent
			WHERE je.docstatus = 1 AND jea.debit > 0 AND jea.{line} IN %(d)s
			GROUP BY jea.{line}
			""".format(line=ROW_LINE_FIELD, qty=ROW_QTY_FIELD),
			{"d": tuple(details)},
		)
	)


def _rate(line, delivered_value):
	"""Unit cost for the undelivered units, and where it came from."""
	# What the shipped part of this same line actually cost.
	if line.delivered_qty > QTY_TOLERANCE and flt(delivered_value) > 0:
		return flt(delivered_value / line.delivered_qty, 6), "Delivered cost of this line"

	at = get_datetime(f"{line.posting_date} {line.posting_time or '23:59:59'}")
	warehouse = line.warehouse or (
		line.so_detail and frappe.db.get_value("Sales Order Item", line.so_detail, "warehouse")
	)
	if warehouse:
		rate = frappe.db.sql(
			"""
			SELECT valuation_rate FROM `tabStock Ledger Entry`
			WHERE item_code = %s AND warehouse = %s AND is_cancelled = 0 AND posting_datetime <= %s
			ORDER BY posting_datetime DESC, creation DESC LIMIT 1
			""",
			(line.item_code, warehouse, at),
		)
		if rate and flt(rate[0][0]) > 0:
			return flt(rate[0][0], 6), f"Valuation in {warehouse} on invoice date"

	rate = frappe.db.sql(
		"""
		SELECT valuation_rate FROM `tabStock Ledger Entry`
		WHERE item_code = %s AND company = %s AND is_cancelled = 0
			AND posting_datetime <= %s AND valuation_rate > 0
		ORDER BY posting_datetime DESC, creation DESC LIMIT 1
		""",
		(line.item_code, line.company, at),
	)
	if rate and flt(rate[0][0]) > 0:
		return flt(rate[0][0], 6), "Latest company valuation on invoice date"

	rate = flt(frappe.db.get_value("Item", line.item_code, "valuation_rate"))
	if rate > 0:
		return rate, "Item valuation rate"
	return 0, ""


# ── posting ─────────────────────────────────────────────────────────────────


def post_entries(company, from_date, to_date, sales_invoice=None, notify=True):
	"""Post one Journal Entry per invoice with an undelivered gap. Safe to re-run."""
	defaults = frappe.db.get_value(
		"Company", company, ["stock_adjustment_account", "default_expense_account", "cost_center"], as_dict=True
	)
	if not defaults or not defaults.stock_adjustment_account:
		frappe.throw(_("Set a Stock Adjustment Account on Company {0}").format(company))

	by_invoice = {}
	for l in get_lines(company, from_date, to_date):
		if l.status == "To Post" and (not sales_invoice or l.sales_invoice == sales_invoice):
			by_invoice.setdefault(l.sales_invoice, []).append(l)

	posted, failed = [], []
	for si, rows in by_invoice.items():
		frappe.db.savepoint("undelivered_cogs")
		try:
			je = _make_journal_entry(company, si, rows, defaults)
			posted.append((si, je.name, flt(sum(r.amount for r in rows), 2)))
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback(save_point="undelivered_cogs")
			failed.append((si, str(e)))
			frappe.log_error(frappe.get_traceback(), f"Undelivered COGS failed for {si}")

	summary = {
		"posted": len(posted),
		"amount": flt(sum(p[2] for p in posted), 2),
		"failed": failed,
		"entries": posted,
	}
	if not notify:
		return summary
	frappe.publish_realtime(
		"msgprint",
		_("Undelivered COGS: {0} Journal Entries posted, total {1}. {2} failed.").format(
			summary["posted"], frappe.format_value(summary["amount"], "Currency"), len(failed)
		)
		+ ("<br>" + "<br>".join(f"{s}: {m}" for s, m in failed[:20]) if failed else ""),
		user=frappe.session.user,
	)
	return summary


def _make_journal_entry(company, si, rows, defaults):
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = rows[0].posting_date
	je.set(JE_INVOICE_FIELD, si)
	je.title = f"Undelivered COGS - {si}"
	je.user_remark = (
		f"COGS for quantity invoiced on {si} with no Stock Ledger Entry (not delivered). "
		"Accounting entry only; no stock was moved."
	)
	for r in rows:
		cost_center = r.cost_center or defaults.cost_center
		je.append(
			"accounts",
			{
				"account": r.cogs_account,
				"debit_in_account_currency": r.amount,
				"cost_center": cost_center,
				ROW_LINE_FIELD: r.si_detail,
				ROW_QTY_FIELD: r.remaining_qty,
				"user_remark": f"{r.item_code}: {r.remaining_qty} @ {r.rate} ({r.rate_source})",
			},
		)
		je.append(
			"accounts",
			{
				"account": defaults.stock_adjustment_account,
				"credit_in_account_currency": r.amount,
				"cost_center": cost_center,
				ROW_LINE_FIELD: r.si_detail,
			},
		)
	je.insert()
	je.submit()
	return je


@frappe.whitelist()
def enqueue_post(company, from_date, to_date):
	frappe.only_for(MANAGER_ROLES)
	_check_company(company)
	frappe.enqueue(
		"cannabis_management.api.undelivered_cogs.post_entries",
		queue="long",
		timeout=3600,
		company=company,
		from_date=from_date,
		to_date=to_date,
	)
	return _("Posting started in the background. You will get a message when it finishes.")


# ── Sales Invoice form ──────────────────────────────────────────────────────


@frappe.whitelist()
def get_invoice_status(sales_invoice):
	"""The invoice's undelivered COGS entries, and what is still left to post."""
	frappe.has_permission("Sales Invoice", "read", sales_invoice, throw=True)
	_ensure_fields()
	entries = frappe.get_list(
		"Journal Entry",
		filters={JE_INVOICE_FIELD: sales_invoice, "docstatus": ("<", 2)},
		fields=["name", "posting_date", "total_debit", "docstatus"],
		order_by="posting_date, creation",
	)
	out = {"entries": entries, "can_post": False, "to_post": 0, "lines": 0}
	if not set(MANAGER_ROLES) & set(frappe.get_roles()):
		return out

	si = frappe.db.get_value("Sales Invoice", sales_invoice, ["company", "posting_date", "docstatus", "is_return"], as_dict=True)
	if si.docstatus != 1 or si.is_return or si.company not in COMPANIES:
		return out
	pending = [
		l
		for l in get_lines(si.company, si.posting_date, si.posting_date)
		if l.sales_invoice == sales_invoice and l.status == "To Post"
	]
	out.update(can_post=True, to_post=flt(sum(l.amount for l in pending), 2), lines=len(pending))
	return out


@frappe.whitelist()
def post_for_invoice(sales_invoice):
	"""Post the undelivered COGS of one invoice, from its form."""
	frappe.only_for(MANAGER_ROLES)
	si = frappe.db.get_value("Sales Invoice", sales_invoice, ["company", "posting_date", "docstatus"], as_dict=True)
	if not si or si.docstatus != 1:
		frappe.throw(_("Sales Invoice {0} is not submitted").format(sales_invoice))
	summary = post_entries(si.company, si.posting_date, si.posting_date, sales_invoice=sales_invoice, notify=False)
	if summary["failed"]:
		frappe.throw(summary["failed"][0][1])
	return summary


# ── General Ledger: file under the Sales Invoice ────────────────────────────


def file_under_invoice(journal_entry, sales_invoice=None):
	"""Restamp a Journal Entry's live GL rows onto its Sales Invoice's voucher."""
	sales_invoice = sales_invoice or frappe.db.get_value("Journal Entry", journal_entry, JE_INVOICE_FIELD)
	if not sales_invoice:
		return 0
	names = frappe.get_all(
		"GL Entry",
		filters={"voucher_type": "Journal Entry", "voucher_no": journal_entry, "is_cancelled": 0},
		pluck="name",
	)
	if not names:
		return 0
	frappe.db.sql(
		"""
		UPDATE `tabGL Entry`
		SET voucher_type = 'Sales Invoice',
		    voucher_no   = %(si)s,
		    voucher_subtype = %(subtype)s,
		    `{otype}`    = 'Journal Entry',
		    `{ono}`      = %(je)s
		WHERE name IN %(names)s
		""".format(otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD),
		{"si": sales_invoice, "subtype": invoice_voucher_subtype(sales_invoice), "je": journal_entry, "names": tuple(names)},
	)
	return len(names)


def move_back_to_journal_entry(journal_entry):
	"""Undo file_under_invoice, so core's cancel can find the rows to reverse."""
	frappe.db.sql(
		"""
		UPDATE `tabGL Entry`
		SET voucher_type = 'Journal Entry',
		    voucher_no   = %(je)s,
		    voucher_subtype = %(subtype)s,
		    `{otype}`    = NULL,
		    `{ono}`      = NULL
		WHERE `{otype}` = 'Journal Entry' AND `{ono}` = %(je)s AND is_cancelled = 0
		""".format(otype=ORIGIN_TYPE_FIELD, ono=ORIGIN_NO_FIELD),
		{"je": journal_entry, "subtype": frappe.db.get_value("Journal Entry", journal_entry, "voucher_type")},
	)


def restore_for_invoice(sales_invoice):
	"""Re-post entries a repost of the invoice deleted along with its own rows."""
	for je in frappe.get_all(
		"Journal Entry", filters={JE_INVOICE_FIELD: sales_invoice, "docstatus": 1}, pluck="name"
	):
		live = frappe.db.sql(
			"""SELECT 1 FROM `tabGL Entry` WHERE is_cancelled = 0
			AND ((voucher_type = 'Journal Entry' AND voucher_no = %(je)s) OR `{ono}` = %(je)s) LIMIT 1""".format(
				ono=ORIGIN_NO_FIELD
			),
			{"je": je},
		)
		if not live:
			frappe.get_doc("Journal Entry", je).make_gl_entries()
			file_under_invoice(je, sales_invoice)


def journal_entry_on_submit(doc, method=None):
	if doc.get(JE_INVOICE_FIELD):
		file_under_invoice(doc.name, doc.get(JE_INVOICE_FIELD))


def journal_entry_before_cancel(doc, method=None):
	if doc.get(JE_INVOICE_FIELD):
		move_back_to_journal_entry(doc.name)


def repost_ledger_validate(doc, method=None):
	"""Core's repost looks rows up by the Journal Entry's own voucher and would
	miss the ones filed under the invoice, booking the COGS twice."""
	for row in doc.get("vouchers") or []:
		if row.voucher_type == "Journal Entry" and frappe.db.get_value(
			"Journal Entry", row.voucher_no, JE_INVOICE_FIELD
		):
			frappe.throw(
				_("Row {0}: {1} is an Undelivered COGS entry filed under its Sales Invoice. Repost the Sales Invoice instead.").format(
					row.idx, row.voucher_no
				)
			)


def backfill_gl(company="Motley Terpz"):
	"""File already-submitted entries' GL under their invoices. Idempotent."""
	_check_company(company)
	moved = 0
	for je in frappe.get_all(
		"Journal Entry", filters={JE_INVOICE_FIELD: ("is", "set"), "docstatus": 1, "company": company}, pluck="name"
	):
		moved += file_under_invoice(je)
	frappe.db.commit()
	print(f"Filed {moved} GL rows under their Sales Invoices.")
