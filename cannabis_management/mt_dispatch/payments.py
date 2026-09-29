"""What has been paid against a Sales Order, and the cached G5 result.

`custom_amount_paid` and `custom_payment_verified` on the order are a cache so
Slack messages can show the figure without recomputing. The gate itself always
recomputes -- the cache is never trusted for the release decision.
"""

import frappe
from frappe.utils import flt

from cannabis_management.mt_dispatch import notify, stages
from cannabis_management.mt_dispatch.settings import get_company_settings


def required_amount(so):
	"""What the order is owed, matching whatever total the customer sees."""
	if so.get("disable_rounded_total"):
		return flt(so.grand_total)
	return flt(so.rounded_total or so.grand_total)


def paid_amount(so):
	"""Money in against this order.

	Advances against the Sales Order are the primary measure -- the Slack
	payment form always creates those. Invoices raised from the order are a
	fallback for payments taken the ordinary way, against the invoice.

	The two overlap: an advance allocated to an invoice shows up in both. Take
	the larger of the two rather than the sum, or an allocated advance counts
	twice and an unpaid order looks settled.
	"""
	paid = flt(so.advance_paid)

	invoices = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": so.name, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	if invoices:
		rows = frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", invoices], "docstatus": 1},
			fields=["rounded_total", "grand_total", "outstanding_amount"],
		)
		settled = sum(
			flt(r.rounded_total or r.grand_total) - flt(r.outstanding_amount) for r in rows
		)
		paid = max(paid, settled)

	return flt(paid)


def is_internal(so):
	if so.get("is_internal_customer") is not None:
		return bool(so.get("is_internal_customer"))
	return bool(frappe.db.get_value("Customer", so.customer, "is_internal_customer"))


def payment_gate_applies(so, cfg):
	"""Whether G5 has anything to say about this order at all.

	Terms orders are governed by credit approval (G0), not by money in the
	bank, so the payment gate only ever looks at Cash On Delivery.
	"""
	if not cfg or not cfg.payment_gate_enabled:
		return False
	if so.get("custom_mode_of_payment") != stages.COD:
		return False
	if required_amount(so) <= 0:
		return False
	if is_internal(so) and not cfg.gate_internal_customers:
		return False
	return True


def payment_status(so, cfg=None):
	"""(applies, paid, required, short) for one order."""
	cfg = cfg or get_company_settings(so.company)
	paid = paid_amount(so)
	required = required_amount(so)
	tolerance = flt(cfg.payment_tolerance) if cfg else 0.01
	short = flt(required - paid)
	return payment_gate_applies(so, cfg), paid, required, (short if short > tolerance else 0.0)


def refresh_payment_status(sales_order, notify_approvers=True):
	"""Recompute the cache on one order. Returns True when it is now clear."""
	if not frappe.db.exists("Sales Order", sales_order):
		return False

	so = frappe.get_doc("Sales Order", sales_order)
	if so.docstatus != 1:
		return False

	cfg = get_company_settings(so.company)
	if not cfg:
		return False

	applies, paid, _required, short = payment_status(so, cfg)
	verified = 0 if (applies and short) else 1

	was_verified = bool(so.get("custom_payment_verified"))
	so.db_set(
		{"custom_amount_paid": paid, "custom_payment_verified": verified},
		update_modified=False,
	)

	just_cleared = verified and not was_verified
	if notify_approvers and just_cleared and so.get("custom_logistic_status") == stages.AWAITING_RELEASE:
		notify.enqueue(
			"cannabis_management.mt_dispatch.notify.on_payment_cleared",
			sales_order=so.name,
			enqueue_after_commit=True,
			queue="short",
		)
	return bool(verified)


def orders_touched_by(pe):
	"""Every Sales Order a Payment Entry moves money against.

	Sales Order references count directly. Sales Invoice references are mapped
	back through Sales Invoice Item.sales_order, because paying the invoice is
	how a COD order settles when finance works in the ERP rather than Slack.
	"""
	orders, invoices = set(), set()
	for ref in pe.references or []:
		if ref.reference_doctype == "Sales Order" and ref.reference_name:
			orders.add(ref.reference_name)
		elif ref.reference_doctype == "Sales Invoice" and ref.reference_name:
			invoices.add(ref.reference_name)

	if invoices:
		for row in frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": ["in", list(invoices)], "sales_order": ["is", "set"]},
			fields=["sales_order"],
			distinct=True,
		):
			orders.add(row.sales_order)

	return orders


def on_pe_change(doc, method=None):
	"""Payment Entry submitted or cancelled -- refresh every order it touches."""
	for name in orders_touched_by(doc):
		refresh_payment_status(name)
