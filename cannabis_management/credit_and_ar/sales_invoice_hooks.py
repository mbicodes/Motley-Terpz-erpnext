"""Credit gate on the Sales Invoice — the other way exposure gets committed.

The Sales Order gate (sales_order_hooks.before_submit) refuses an order that
would push a customer past their approved line. On its own that is a fence with
one gate and no wall: an invoice can be raised directly, with no Sales Order at
all, and the same exposure lands on the same customer without anyone being
asked. This module closes that path.

What is gated, and what deliberately is not
-------------------------------------------
Only the part of the invoice that **no submitted Sales Order already covers**.

An invoice raised from an approved, submitted order was already measured against
the line at the order, and the goods have typically shipped by the time it is
billed. Re-testing it here would strand delivered product in an unbillable
state — and worse, the debt would go unrecorded, which is precisely what Finance
needs to see. So a fully order-backed invoice passes; a direct invoice is
measured in full; a part-ordered invoice is measured on the part nobody
approved.

Holds follow the same split, for the same reason: a held customer can still be
billed for work already ordered, but no new unordered credit work goes through.
"""

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_and_ar import (
	ar_cap,
	credit_engine,
	sales_order_hooks,
	utils,
)


def before_submit(doc, method=None):
	"""Refuse an invoice whose un-ordered portion breaks the credit line."""
	# A credit note reduces exposure; a POS sale is paid at the till.
	if doc.get("is_return") or doc.get("is_pos"):
		return

	# The AR cap first — see ar_cap: it deliberately outranks the policy
	# exemption, so it is checked before the exemption can end this function.
	if ar_cap.is_terms_invoice(doc):
		ar_cap.assert_under_cap(doc, _invoice_credit_amount(doc), noun="invoice")

	if utils.is_policy_exempt(doc.customer):
		return

	uncovered, orders = _uncovered_credit(doc)
	if uncovered <= 0.005:
		return

	# Line first, hold second — same reasoning as the Sales Order gate: when both
	# apply, the number that stopped the invoice is the actionable one, and a
	# bare "on hold" sends Sales to Finance instead of to the arithmetic.
	_check_line(doc, uncovered, orders)
	_assert_not_on_hold(doc)


def _invoice_credit_amount(doc) -> float:
	"""What this invoice will still have outstanding once submitted.

	outstanding_amount is already net of advances, write-offs and anything paid
	on the invoice itself, so it is the honest measure of credit extended. It is
	computed during validate, so it is populated by the time before_submit runs;
	the fallback covers a doc built in code that skipped that path.
	"""
	outstanding = flt(doc.get("outstanding_amount"))
	if outstanding:
		return outstanding
	return max(
		0.0,
		flt(doc.grand_total) - flt(doc.get("total_advance")) - flt(doc.get("write_off_amount")),
	)


def _uncovered_credit(doc):
	"""(credit not covered by a submitted Sales Order, orders this invoice bills).

	Proportional rather than line-exact: the invoice's credit amount is net of
	advances that are not attributable to particular lines, so the un-ordered
	share of the invoice value is the defensible way to split it.
	"""
	total = 0.0
	ordered = 0.0
	orders = set()

	for item in doc.get("items") or []:
		amount = flt(item.get("base_amount") or item.get("amount"))
		total += amount
		sales_order = item.get("sales_order")
		if sales_order and frappe.db.get_value("Sales Order", sales_order, "docstatus") == 1:
			ordered += amount
			orders.add(sales_order)

	credit_amount = _invoice_credit_amount(doc)
	if total <= 0:
		# Nothing to apportion — treat the whole thing as un-ordered.
		return credit_amount, sorted(orders)

	uncovered_ratio = max(0.0, 1.0 - (ordered / total))
	return flt(credit_amount * uncovered_ratio), sorted(orders)


def _assert_not_on_hold(doc):
	"""Same stop-work rule the Sales Order gate applies, limited to new credit
	work — an ordered invoice is still billable while a customer is held."""
	hold_type = frappe.db.get_value("Customer", doc.customer, "custom_hold_type")
	if hold_type not in utils.BLOCKING_HOLDS:
		return

	case = frappe.db.get_value("Customer", doc.customer, "custom_active_ar_case")
	case_link = f" ({utils.doc_link('AR Case', case)})" if case else ""

	frappe.throw(
		_(
			"<b>Stop Work.</b> {0} is on <b>{1}</b>{2}.<br><br>"
			"This invoice is not backed by an approved Sales Order, so it counts as "
			"new credit work. Raise and approve a Sales Order, or have Credit Finance "
			"release the hold."
		).format(frappe.bold(doc.customer), hold_type, case_link),
		title=_("Customer On Hold"),
	)


def _check_line(doc, uncovered, orders):
	"""The same arithmetic and the same wording as the Sales Order refusal, so
	Sales cannot be told two different numbers for one customer."""
	summary = credit_engine.get_line_summary(doc.customer, exclude_sales_order=orders)

	required = max(0.0, uncovered - flt(summary["available_line"]))
	if required <= 0.005:
		return

	frappe.throw(
		sales_order_hooks._describe_over_limit(doc, summary, uncovered, required, noun="invoice")
		+ _(
			"<br><br>This invoice is not backed by an approved Sales Order, so it is "
			"measured against the line in full. Raise a Sales Order and get it "
			"approved, or collect payment before invoicing."
		),
		title=_("Credit Limit Exceeded"),
	)
