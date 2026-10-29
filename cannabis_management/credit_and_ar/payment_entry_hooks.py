import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from cannabis_management.credit_and_ar import credit_engine, utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
	RESOLUTION_PAYMENT_PLAN,
	RESOLUTION_WORKOUT,
	STATUS_ACTIVE,
)

ALLOWED_TARGETS = {
	utils.LEDGER_NEW_BOOK: (utils.LEDGER_NEW_BOOK,),
	utils.LEDGER_LEGACY: (utils.LEDGER_LEGACY,),
	utils.LEDGER_PLAN: (utils.LEDGER_PLAN, utils.LEDGER_LEGACY),
}

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
	if doc.party_type == "Customer" and doc.party:
		credit_engine.refresh_customer_exposure(doc.party)

		from cannabis_management.credit_and_ar import plan_workout

		plan_workout.refresh_workout_balance(doc.party)

	if not _is_customer_receipt(doc):
		return
	if utils.is_policy_exempt(doc.party):
		return

	if doc.custom_ledger == utils.LEDGER_PLAN:
		apply_to_installment(doc)


def on_cancel(doc, method=None):
	if doc.party_type == "Customer" and doc.party:
		credit_engine.refresh_customer_exposure(doc.party)

		from cannabis_management.credit_and_ar import plan_workout

		plan_workout.refresh_workout_balance(doc.party)

	if not _is_customer_receipt(doc):
		return

	if doc.custom_ledger == utils.LEDGER_PLAN and doc.custom_ar_case:
		_unapply_installment(doc)


def _is_customer_receipt(doc) -> bool:
	return doc.payment_type == "Receive" and doc.party_type == "Customer" and bool(doc.party)


def _default_ledger(doc):
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
		resolution = (
			RESOLUTION_PAYMENT_PLAN if doc.custom_ledger == utils.LEDGER_PLAN else RESOLUTION_WORKOUT
		)
		found = frappe.get_all(
			"AR Case",
			filters={
				"customer": doc.party,
				"resolution": resolution,
				"status": STATUS_ACTIVE,
			},
			pluck="name",
			limit=1,
		)
		if not found:
			frappe.throw(
				_("{0} has no active {1} case, so this receipt cannot be booked to that ledger.").format(
					frappe.bold(doc.party), resolution
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


def _validate_allocations(doc):
	allowed = ALLOWED_TARGETS.get(doc.custom_ledger)
	if not allowed:
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


def apply_to_installment(doc):
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


def stamp_invoice_ledger(doc, method=None):
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
	plan = frappe.get_all(
		"AR Case",
		filters={
			"customer": customer,
			"resolution": RESOLUTION_PAYMENT_PLAN,
			"status": STATUS_ACTIVE,
		},
		fields=["name", "md_ratified", "missed_installments"],
		limit=1,
	)
	return {"plan": plan[0] if plan else None}
