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
	if doc.get("is_return") or doc.get("is_pos"):
		return

	if utils.is_policy_exempt(doc.customer):
		return

	if ar_cap.is_terms_invoice(doc):
		ar_cap.assert_under_cap(doc, _invoice_credit_amount(doc), noun="invoice")

	uncovered, orders = _uncovered_credit(doc)
	if uncovered <= 0.005:
		return

	_check_line(doc, uncovered, orders)
	_assert_not_on_hold(doc)


def on_submit(doc, method=None):
	if doc.customer:
		credit_engine.refresh_customer_exposure(doc.customer)


def on_cancel(doc, method=None):
	if doc.customer:
		credit_engine.refresh_customer_exposure(doc.customer)


def _invoice_credit_amount(doc) -> float:
	outstanding = flt(doc.get("outstanding_amount"))
	if outstanding:
		return outstanding
	return max(
		0.0,
		flt(doc.grand_total) - flt(doc.get("total_advance")) - flt(doc.get("write_off_amount")),
	)


def _uncovered_credit(doc):
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
		return credit_amount, sorted(orders)

	uncovered_ratio = max(0.0, 1.0 - (ordered / total))
	return flt(credit_amount * uncovered_ratio), sorted(orders)


def _assert_not_on_hold(doc):
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import get_hold_type

	hold_type = get_hold_type(doc.customer)
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
