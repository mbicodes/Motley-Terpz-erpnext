"""Two ledgers, never netted.

A customer on a payment plan runs two books at once: the **plan** (the old debt
being worked off) and the **new book** (current trading). Money for one must
never quietly pay down the other — that is how a plan silently collapses while
the reports still look healthy.

Every customer receipt therefore carries a ledger, and allocations are confined
to invoices belonging to that same ledger.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.credit_and_ar import utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
	INACTIVE_STATUSES,
	TYPE_PAYMENT_PLAN,
	TYPE_WORKOUT,
)

# Which invoice ledgers each receipt ledger is allowed to touch.
ALLOWED_TARGETS = {
	utils.LEDGER_NEW_BOOK: (utils.LEDGER_NEW_BOOK,),
	utils.LEDGER_LEGACY: (utils.LEDGER_LEGACY,),
	utils.LEDGER_PLAN: (utils.LEDGER_PLAN, utils.LEDGER_LEGACY),
}

# These never allocate against an invoice — they sit against a Sales Order.
ORDER_LEDGERS = (utils.LEDGER_DEPOSIT, utils.LEDGER_WORKOUT_PAYDOWN)


def validate(doc, method=None):
	if not _is_customer_receipt(doc):
		return
	if utils.is_policy_exempt(doc.party):
		return

	_default_ledger(doc)
	_validate_case_link(doc)
	_validate_order_link(doc)
	_validate_allocations(doc)


def on_submit(doc, method=None):
	if not _is_customer_receipt(doc):
		return
	if utils.is_policy_exempt(doc.party):
		return

	if doc.custom_ledger == utils.LEDGER_PLAN:
		apply_to_installment(doc)


def on_cancel(doc, method=None):
	if not _is_customer_receipt(doc):
		return

	if doc.custom_ledger == utils.LEDGER_PLAN and doc.custom_ar_case:
		_unapply_installment(doc)


def _is_customer_receipt(doc) -> bool:
	return doc.payment_type == "Receive" and doc.party_type == "Customer" and bool(doc.party)


# ── ledger ───────────────────────────────────────────────────────────────────


def _default_ledger(doc):
	"""Derive the ledger when it is blank, rather than blocking the save.

	Every customer receipt ends up carrying a ledger, but existing automation
	that creates Payment Entries keeps working — the value is inferred from what
	the receipt is actually paying.
	"""
	if doc.custom_ledger:
		return

	if doc.get("custom_against_sales_order"):
		doc.custom_ledger = utils.LEDGER_DEPOSIT
		return

	ledgers = {
		frappe.db.get_value("Sales Invoice", ref.reference_name, "custom_ledger")
		for ref in doc.get("references") or []
		if ref.reference_doctype == "Sales Invoice" and ref.reference_name
	}
	ledgers.discard(None)
	ledgers.discard("")

	if len(ledgers) == 1:
		doc.custom_ledger = ledgers.pop()
	elif not ledgers:
		doc.custom_ledger = utils.LEDGER_NEW_BOOK


def _validate_case_link(doc):
	if doc.custom_ledger not in (utils.LEDGER_PLAN, utils.LEDGER_WORKOUT_PAYDOWN):
		return

	if not doc.get("custom_ar_case"):
		case_type = (
			TYPE_PAYMENT_PLAN if doc.custom_ledger == utils.LEDGER_PLAN else TYPE_WORKOUT
		)
		found = frappe.get_all(
			"AR Case",
			filters={
				"customer": doc.party,
				"case_type": case_type,
				"status": ("not in", INACTIVE_STATUSES),
			},
			pluck="name",
			limit=1,
		)
		if not found:
			frappe.throw(
				_("{0} has no active {1} case, so this receipt cannot be booked to that ledger.").format(
					frappe.bold(doc.party), case_type
				),
				title=_("No Case"),
			)
		doc.custom_ar_case = found[0]

	case_customer = frappe.db.get_value("AR Case", doc.custom_ar_case, "customer")
	if case_customer != doc.party:
		frappe.throw(
			_("AR Case {0} belongs to {1}, not {2}.").format(
				doc.custom_ar_case, case_customer, doc.party
			)
		)


def _validate_order_link(doc):
	if doc.custom_ledger not in ORDER_LEDGERS:
		return

	if not doc.get("custom_against_sales_order"):
		frappe.throw(
			_("A {0} receipt must name the Sales Order it is against.").format(doc.custom_ledger),
			title=_("Sales Order Required"),
		)

	so_customer = frappe.db.get_value(
		"Sales Order", doc.custom_against_sales_order, "customer"
	)
	if so_customer != doc.party:
		frappe.throw(
			_("Sales Order {0} belongs to {1}, not {2}.").format(
				doc.custom_against_sales_order, so_customer, doc.party
			)
		)


# ── allocations ──────────────────────────────────────────────────────────────


def _validate_allocations(doc):
	"""Confine a receipt to invoices on its own ledger."""
	allowed = ALLOWED_TARGETS.get(doc.custom_ledger)
	if not allowed:
		# Deposit / Workout Paydown are unallocated on purpose: they sit against
		# an order until it is invoiced.
		if doc.custom_ledger in ORDER_LEDGERS:
			_reject_allocations(doc)
		return

	plan_case = doc.custom_ar_case if doc.custom_ledger == utils.LEDGER_PLAN else None

	for ref in doc.get("references") or []:
		if ref.reference_doctype != "Sales Invoice" or not ref.reference_name:
			continue

		invoice = frappe.db.get_value(
			"Sales Invoice",
			ref.reference_name,
			["custom_ledger", "custom_ar_case"],
			as_dict=True,
		) or {}
		invoice_ledger = invoice.get("custom_ledger") or utils.LEDGER_NEW_BOOK

		if invoice_ledger not in allowed:
			frappe.throw(
				_(
					"<b>Cross-ledger allocation.</b><br><br>This receipt is booked to the "
					"<b>{0}</b> ledger, but {1} belongs to the <b>{2}</b> ledger.<br><br>"
					"Plan money and new-book money are never netted. Split the receipt "
					"into one Payment Entry per ledger."
				).format(doc.custom_ledger, ref.reference_name, invoice_ledger),
				title=_("Two Ledgers, Never Netted"),
			)

		if plan_case and invoice.get("custom_ar_case") and invoice["custom_ar_case"] != plan_case:
			frappe.throw(
				_("{0} belongs to plan {1}, not {2}.").format(
					ref.reference_name, invoice["custom_ar_case"], plan_case
				),
				title=_("Wrong Plan"),
			)

		if doc.custom_ledger == utils.LEDGER_NEW_BOOK and invoice.get("custom_ar_case"):
			frappe.throw(
				_(
					"{0} is under payment plan {1}. A new-book receipt cannot pay a plan "
					"invoice — book it to the <b>Plan</b> ledger instead."
				).format(ref.reference_name, invoice["custom_ar_case"]),
				title=_("Two Ledgers, Never Netted"),
			)


def _reject_allocations(doc):
	if doc.get("references"):
		frappe.throw(
			_(
				"A <b>{0}</b> receipt is held against the Sales Order until it is invoiced, "
				"so it must not be allocated to an invoice."
			).format(doc.custom_ledger),
			title=_("Do Not Allocate"),
		)


# ── installments ─────────────────────────────────────────────────────────────


def apply_to_installment(doc):
	"""Settle the named installment, or the oldest one still owing."""
	if not doc.custom_ar_case:
		return

	case = frappe.get_doc("AR Case", doc.custom_ar_case)
	remaining = flt(doc.paid_amount)

	rows = []
	if doc.get("custom_installment"):
		rows = [row for row in case.schedule if row.name == doc.custom_installment]
	if not rows:
		rows = [
			row
			for row in case.schedule
			if row.status in ("Pending", "Partially Paid", "Missed")
		]
		rows.sort(key=lambda row: getdate(row.due_date or nowdate()))

	touched = False
	for row in rows:
		if remaining <= 0:
			break
		owing = flt(row.amount) - flt(row.paid_amount)
		if owing <= 0:
			continue

		applied = min(owing, remaining)
		row.paid_amount = flt(row.paid_amount) + applied
		row.paid_on = doc.posting_date
		row.payment_entry = doc.name
		row.status = "Paid" if flt(row.paid_amount) + 0.005 >= flt(row.amount) else "Partially Paid"
		remaining -= applied
		touched = True

	if not touched:
		return

	case.missed_installments = len([row for row in case.schedule if row.status == "Missed"])
	case.flags.ignore_role_guards = True
	case.save(ignore_permissions=True)
	case.add_comment(
		"Info",
		_("Plan receipt {0} for {1} applied to the schedule.").format(
			doc.name, utils.fmt_currency(doc.paid_amount)
		),
	)


def _unapply_installment(doc):
	"""Cancelling a plan receipt puts the installments back where they were."""
	case = frappe.get_doc("AR Case", doc.custom_ar_case)
	touched = False

	for row in case.schedule:
		if row.payment_entry != doc.name:
			continue
		row.paid_amount = 0
		row.paid_on = None
		row.payment_entry = None
		row.status = "Missed" if row.due_date and getdate(row.due_date) < getdate(nowdate()) else "Pending"
		touched = True

	if not touched:
		return

	case.missed_installments = len([row for row in case.schedule if row.status == "Missed"])
	case.flags.ignore_role_guards = True
	case.save(ignore_permissions=True)


# ── Sales Invoice ledger stamping ────────────────────────────────────────────


def stamp_invoice_ledger(doc, method=None):
	"""Classify every invoice as it is written.

	Legacy is anything dated before the policy effective date: collected on its
	original terms, never charged a finance charge, and excluded from the
	new-book cap, DSO and CEI.
	"""
	_stamp_payment_mode(doc)

	if doc.get("custom_is_finance_charge"):
		doc.custom_ledger = utils.LEDGER_NEW_BOOK
		return

	effective_date = utils.policy_effective_date()
	if not effective_date:
		return

	if doc.custom_ar_case:
		doc.custom_ledger = utils.LEDGER_PLAN
		return

	doc.custom_ledger = (
		utils.LEDGER_LEGACY
		if getdate(doc.posting_date) < effective_date
		else utils.LEDGER_NEW_BOOK
	)


def _stamp_payment_mode(doc):
	"""Carry the order's payment mode onto the invoice.

	DSO and CEI measure *credit* sales only, so every invoice has to say whether
	it was sold on terms or COD. The existing (and otherwise unused)
	`custom_mode_of_payment` field on Sales Invoice carries it, rather than a
	second field meaning the same thing.
	"""
	if doc.get("custom_mode_of_payment"):
		return

	for item in doc.get("items") or []:
		if item.get("sales_order"):
			mode = frappe.db.get_value(
				"Sales Order", item.sales_order, "custom_mode_of_payment"
			)
			if mode:
				doc.custom_mode_of_payment = mode
				return

	template = doc.get("payment_terms_template")
	if template and template != "COD" and utils.template_credit_days(template) > 0:
		doc.custom_mode_of_payment = utils.MODE_TERMS
	else:
		doc.custom_mode_of_payment = utils.MODE_COD


@frappe.whitelist()
def get_plan_context(customer: str):
	"""Tell the Payment Entry form whether this customer runs two books."""
	plan = frappe.get_all(
		"AR Case",
		filters={
			"customer": customer,
			"case_type": TYPE_PAYMENT_PLAN,
			"status": ("not in", INACTIVE_STATUSES),
		},
		fields=["name", "md_ratified", "missed_installments"],
		limit=1,
	)
	return {"plan": plan[0] if plan else None}
