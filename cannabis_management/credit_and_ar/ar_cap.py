import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_and_ar import credit_engine, utils


def assert_under_cap(doc, credit_amount: float, noun: str = "order"):
	if not utils.ar_cap_enabled():
		return

	cap = credit_engine.get_customer_ar_cap()
	if cap <= 0:
		return

	customer = doc.get("customer")
	if not customer or credit_engine.is_internal_customer(customer):
		return

	current_ar = credit_engine.get_customer_new_ar(customer)
	projected = current_ar + flt(credit_amount)
	if projected <= cap:
		return

	currency = doc.get("currency")

	def money(amount):
		return utils.fmt_currency(amount, currency)

	frappe.throw(
		_(
			"<b>AR cap reached.</b> {customer} cannot take Terms work while their "
			"new-book receivables sit above <b>{cap}</b>. Legacy AR is excluded."
			"<ul style='margin:8px 0 0 16px;padding:0'>"
			"<li>New AR today: <b>{current}</b></li>"
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
	portion = utils.template_credit_portion(doc.get("payment_terms_template")) / 100.0
	return flt(doc.get("grand_total")) * portion


def is_terms_invoice(doc) -> bool:
	mode = (doc.get("custom_mode_of_payment") or "").strip()
	if mode == utils.MODE_TERMS:
		return True
	if mode:
		return False
	return flt(doc.get("outstanding_amount")) > 0.005
