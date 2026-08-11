"""Finance charges on past-due balances (§6).

Simple, non-compounding, pro-rated by day from the day *after* the due date, at
the lower of the policy rate and any statutory ceiling.

Two hard exclusions, both of them legal rather than arithmetic:

* **Legacy invoices are never charged.** §12 — pre-policy balances are collected
  on their original terms, with no retroactive fees.
* **No charge under an agreement missing the counsel-approved clause.** If the
  signed Credit Agreement does not carry the California counsel-approved
  language, there is nothing to charge under.

Finance charge invoices are excluded from DSO, CEI and the payment score: a late
fee is a consequence of poor payment, not evidence of it.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from cannabis_management.credit_and_ar import utils

NET30_TEMPLATES = ("NET30", "50% down NET30")


def apply_finance_charges():
	"""Monthly. Leaves invoices in Draft unless Finance has opted into auto-submit."""
	if not utils.require_policy_live("apply_finance_charges"):
		return

	settings = utils.get_settings()
	if not settings.finance_charge_enabled:
		frappe.logger("credit_and_ar").info("Finance charges are disabled — run skipped.")
		return

	if not settings.finance_charge_item or not settings.finance_charge_income_account:
		frappe.log_error(
			"Finance charges are enabled but the item or income account is not set.",
			"Finance charge run aborted",
		)
		return

	rate = _effective_monthly_rate(settings)
	if rate <= 0:
		return

	today = getdate(nowdate())
	created = []

	for customer in _eligible_customers(settings):
		try:
			invoice = _charge_customer(customer, settings, rate, today)
			if invoice:
				created.append(invoice)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Finance charge failed for {customer}")

	frappe.db.commit()

	if created:
		_notify(created, rate, settings)

	return created


def _effective_monthly_rate(settings) -> float:
	"""The lower of the policy rate and the statutory ceiling."""
	rate = flt(settings.monthly_rate)
	ceiling = flt(settings.max_lawful_rate)
	if ceiling:
		rate = min(rate, ceiling)
	return rate


def _eligible_customers(settings) -> list[str]:
	customers = frappe.get_all(
		"Customer",
		filters={
			"disabled": 0,
			"custom_is_intercompany": 0,
			"custom_credit_policy_exempt": 0,
		},
		pluck="name",
	)

	if not settings.require_counsel_approved_clause:
		return customers

	# No charge is assessed under an agreement lacking the counsel-approved clause.
	allowed = []
	for customer in customers:
		if _has_counsel_clause(customer):
			allowed.append(customer)
	return allowed


def _has_counsel_clause(customer: str) -> bool:
	from cannabis_management.credit_and_ar import credit_engine

	application = credit_engine.get_active_credit_application(customer)
	return bool(application and application.get("counsel_approved_clause"))


def _template_qualifies(settings, template: str | None) -> bool:
	if settings.apply_to == "Net 30 Only":
		return template in NET30_TEMPLATES
	if settings.apply_to == "Per Payment Terms Template":
		return template in utils.settings_list("finance_charge_templates")
	# All Terms Invoices — anything that was actually extended on credit.
	if not template or template == "COD":
		return False
	return utils.template_credit_days(template) > 0


def _charge_customer(customer: str, settings, rate: float, today):
	invoices = _chargeable_invoices(customer, settings, today)
	if not invoices:
		return None

	lines = []
	for row, days, amount in invoices:
		lines.append(
			{
				"invoice": row.name,
				"days": days,
				"amount": amount,
				"principal": flt(row.outstanding_amount),
				"company": row.company,
				"currency": row.currency,
			}
		)

	if not lines:
		return None

	company = lines[0]["company"]
	return _raise_charge_invoice(customer, company, lines, rate, settings, today)


def _chargeable_invoices(customer: str, settings, today):
	"""Every past-due invoice that may lawfully carry a charge, with its accrual."""
	rows = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": customer,
			"docstatus": 1,
			"is_return": 0,
			"outstanding_amount": (">", 0),
			"custom_is_finance_charge": 0,
		},
		fields=[
			"name",
			"company",
			"currency",
			"posting_date",
			"due_date",
			"outstanding_amount",
			"custom_ledger",
			"custom_finance_charge_applied_upto",
			"payment_terms_template",
		],
	)

	effective_date = utils.policy_effective_date()
	rate = _effective_monthly_rate(settings)
	chargeable = []

	for row in rows:
		# §12 — legacy is collected on original terms, no retroactive charges.
		if row.custom_ledger == utils.LEDGER_LEGACY:
			continue
		if effective_date and row.get("posting_date") and getdate(row.posting_date) < effective_date:
			continue
		if not row.due_date:
			continue
		if not _template_qualifies(settings, row.payment_terms_template):
			continue

		# Charge from the day after the due date, never re-charging a period.
		start = add_days(getdate(row.due_date), 1)
		if row.custom_finance_charge_applied_upto:
			applied_upto = getdate(row.custom_finance_charge_applied_upto)
			if applied_upto >= start:
				start = add_days(applied_upto, 1)

		if start > today:
			continue

		days = (today - start).days + 1
		if days <= 0:
			continue

		# Simple, non-compounding, pro-rated by day.
		amount = flt(row.outstanding_amount) * (rate / 100.0) / 30.0 * days
		if amount < 0.01:
			continue

		chargeable.append((row, days, amount))

	return chargeable


def _raise_charge_invoice(customer, company, lines, rate, settings, today):
	doc = frappe.new_doc("Sales Invoice")
	doc.customer = customer
	doc.company = company
	doc.posting_date = today
	doc.set_posting_time = 1
	doc.currency = lines[0]["currency"] or frappe.db.get_value(
		"Company", company, "default_currency"
	)
	doc.custom_is_finance_charge = 1
	doc.custom_ledger = utils.LEDGER_NEW_BOOK
	doc.update_stock = 0
	doc.custom_mode_of_payment = utils.MODE_COD

	if len(lines) == 1:
		doc.custom_finance_charge_against = lines[0]["invoice"]

	for line in lines:
		doc.append(
			"items",
			{
				"item_code": settings.finance_charge_item,
				"qty": 1,
				"rate": flt(line["amount"], 2),
				"income_account": settings.finance_charge_income_account,
				"description": _(
					"Finance charge on {0} — {1} at {2}%/month for {3} day(s)"
				).format(
					line["invoice"],
					utils.fmt_currency(line["principal"]),
					rate,
					line["days"],
				),
			},
		)

	doc.remarks = _(
		"Finance charge assessed under the signed Credit Agreement at {0}% per month, "
		"simple and non-compounding, on {1} past-due invoice(s)."
	).format(rate, len(lines))

	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)

	if settings.auto_submit_finance_charges:
		doc.submit()

	# Stamp the source invoices so the same days are never charged twice —
	# even if the run is repeated.
	for line in lines:
		frappe.db.set_value(
			"Sales Invoice",
			line["invoice"],
			"custom_finance_charge_applied_upto",
			today,
			update_modified=False,
		)

	return {
		"invoice": doc.name,
		"customer": customer,
		"company": company,
		"total": flt(doc.grand_total or sum(line["amount"] for line in lines), 2),
		"lines": len(lines),
		"submitted": int(bool(settings.auto_submit_finance_charges)),
	}


def _notify(created, rate, settings):
	recipients = utils.finance_recipients()
	if not recipients:
		return

	rows = "".join(
		"<tr><td style='padding:4px 12px;border:1px solid #e2e8f0;'>{customer}</td>"
		"<td style='padding:4px 12px;border:1px solid #e2e8f0;'>{invoice}</td>"
		"<td style='padding:4px 12px;border:1px solid #e2e8f0;text-align:right;'>{total}</td>"
		"<td style='padding:4px 12px;border:1px solid #e2e8f0;text-align:right;'>{lines}</td></tr>".format(
			customer=frappe.utils.escape_html(row["customer"]),
			invoice=row["invoice"],
			total=utils.fmt_currency(row["total"]),
			lines=row["lines"],
		)
		for row in created
	)

	state = (
		_("submitted automatically")
		if settings.auto_submit_finance_charges
		else _("left in <b>Draft</b> for your review")
	)

	try:
		frappe.sendmail(
			recipients=recipients,
			subject=_("Finance charges assessed — {0} customer(s)").format(len(created)),
			message=_(
				"<p>{count} finance charge invoice(s) raised at <b>{rate}%/month</b>, simple "
				"and non-compounding. They have been {state}.</p>"
				"<table style='border-collapse:collapse;font-size:13px;'><thead><tr>"
				"<th style='padding:4px 12px;border:1px solid #e2e8f0;background:#f8fafc;'>Customer</th>"
				"<th style='padding:4px 12px;border:1px solid #e2e8f0;background:#f8fafc;'>Invoice</th>"
				"<th style='padding:4px 12px;border:1px solid #e2e8f0;background:#f8fafc;'>Amount</th>"
				"<th style='padding:4px 12px;border:1px solid #e2e8f0;background:#f8fafc;'>Lines</th>"
				"</tr></thead><tbody>{rows}</tbody></table>"
				"<p style='color:#666;font-size:13px;'>Legacy invoices and customers whose "
				"agreement lacks the counsel-approved clause were excluded.</p>"
			).format(count=len(created), rate=rate, state=state, rows=rows),
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Finance charge notification failed")
