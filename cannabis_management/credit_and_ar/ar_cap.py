"""The per-customer AR ceiling — the one rule nothing negotiates with.

Everything else in this module has a way through: a deposit clears an
over-limit order, the Managing Director approves an exception, a policy
exemption carves an account out altogether. This cap has none. Past the figure
in Credit Policy Settings, a customer takes no further Terms work — no Sales
Order, no Sales Invoice — until the balance comes down.

Two deliberate carve-outs, both narrow:

* **Policy exemption does not apply.** Every other engine checks
  ``utils.is_policy_exempt`` first; this one does not, because an exemption
  would otherwise be the bypass, and "no matter what" is the entire point of
  the rule.
* **Internal customers are skipped.** The Customer records standing for our own
  companies carry seven-figure intercompany balances by construction. Blocking
  them would stop internal billing while protecting nobody.

Cash and Sample work is untouched: money arriving with the goods is not AR.
"""

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_and_ar import credit_engine, utils


def assert_under_cap(doc, credit_amount: float, noun: str = "order"):
	"""Refuse a Terms document that would carry the customer past the AR cap.

	`credit_amount` is what this document adds to AR — the deferred portion of an
	order, or an invoice's outstanding balance. It is included in the comparison
	so the document that *crosses* the line is the one refused, rather than
	sailing through and blocking the next one.
	"""
	cap = credit_engine.get_customer_ar_cap()
	if cap <= 0:
		return

	customer = doc.get("customer")
	if not customer or credit_engine.is_internal_customer(customer):
		return

	current_ar = credit_engine.get_customer_ar(customer)
	projected = current_ar + flt(credit_amount)
	if projected <= cap:
		return

	currency = doc.get("currency")

	def money(amount):
		return utils.fmt_currency(amount, currency)

	frappe.throw(
		_(
			"<b>AR cap reached.</b> {customer} cannot take Terms work while their "
			"receivables sit above <b>{cap}</b>."
			"<ul style='margin:8px 0 0 16px;padding:0'>"
			"<li>AR today: <b>{current}</b></li>"
			"<li>This {noun} adds: <b>{adds}</b></li>"
			"<li>Would reach: <b>{projected}</b> against a cap of <b>{cap}</b></li>"
			"</ul>"
			"<br>Collect against the outstanding balance, or switch this {noun} to "
			"Cash On Delivery. No deposit, approval or policy exemption overrides "
			"this cap."
		).format(
			customer=frappe.bold(customer),
			cap=money(cap),
			current=money(current_ar),
			adds=money(credit_amount),
			projected=money(projected),
			noun=noun,
		),
		title=_("AR Cap Reached"),
	)


def order_credit_amount(doc) -> float:
	"""The credit a Terms Sales Order commits — its deferred portion."""
	portion = utils.template_credit_portion(doc.get("payment_terms_template")) / 100.0
	return flt(doc.get("grand_total")) * portion


def is_terms_invoice(doc) -> bool:
	"""Does this invoice extend credit?

	Sales Invoice carries the same custom_mode_of_payment marker as the order, but
	it is blank on most historical invoices. Rather than let a blank mode be the
	way around the cap, a blank is judged on substance: an invoice that leaves
	money outstanding is credit, whatever the label says. An explicit Cash On
	Delivery is taken at its word.
	"""
	mode = (doc.get("custom_mode_of_payment") or "").strip()
	if mode == utils.MODE_TERMS:
		return True
	if mode:
		return False
	return flt(doc.get("outstanding_amount")) > 0.005
