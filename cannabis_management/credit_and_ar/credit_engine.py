"""Exposure and available-line arithmetic.

The credit line is a **single group-wide line**: one approved limit per customer
group, consumed by every operating company (TSBC Ranch, Motley Terpz, Master
Touch Manufacturing) and by every Customer record sharing the same
``custom_credit_group_parent``. A buyer cannot stack three lines by trading with
three entities.

What counts as exposure
-----------------------
* The customer's **net receivable balance in the General Ledger** — every posting
  to a Receivable account for that party, new book and legacy alike. Money owed
  is money owed; the Legacy/New Book split governs the company-wide freeze and
  finance charges, not a customer's own line.

  Reading the ledger rather than summing unpaid invoices matters on this site:
  payments and journal credits are routinely posted against a customer without
  being allocated to a specific invoice, which leaves si.outstanding_amount high
  long after the money arrived. Charging a customer for an invoice they have
  already paid — merely because nobody clicked allocate — blocks real orders.
  Credit Policy Settings -> "AR Source for Credit Checks" switches this back to
  the invoice-only measure if that is ever wanted.
* Submitted, not-yet-fully-billed **Terms** Sales Orders, at the portion of the
  order actually extended on credit — which, since README decision 18, is the
  whole of it. A COD order is not credit until it becomes an unpaid invoice, but
  a 50%-down order is too: nothing gates its up-front leg before the order
  ships, so the whole grand total is at risk.
* Sample orders never count — they are zero-value by construction.
"""

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate, nowdate

from cannabis_management.credit_and_ar import utils

# Sales Order statuses that no longer represent live exposure.
DEAD_SO_STATUSES = ("Closed", "Cancelled")


# ── Credit grouping ──────────────────────────────────────────────────────────


def get_credit_group_parent(customer: str) -> str:
	"""The head of the customer's related-entity group, or the customer itself."""
	if not customer:
		return ""
	parent = frappe.db.get_value("Customer", customer, "custom_credit_group_parent")
	if not parent or parent == customer:
		return customer

	# Walk up, defensively — a mis-keyed cycle must not hang the validate hook.
	seen = {customer}
	while parent and parent not in seen:
		seen.add(parent)
		grandparent = frappe.db.get_value("Customer", parent, "custom_credit_group_parent")
		if not grandparent or grandparent == parent:
			return parent
		parent = grandparent
	return parent or customer


def get_credit_group_members(customer: str) -> list[str]:
	"""Every Customer sharing this customer's credit group, including itself."""
	if not customer:
		return []

	root = get_credit_group_parent(customer)
	members = {customer, root}

	# One level of children is enough because get_credit_group_parent collapses
	# deeper chains onto the root.
	frontier = [root]
	while frontier:
		children = frappe.get_all(
			"Customer",
			filters={"custom_credit_group_parent": ("in", frontier)},
			pluck="name",
		)
		new = [child for child in children if child not in members]
		if not new:
			break
		members.update(new)
		frontier = new

	return sorted(members)


# ── Exposure ─────────────────────────────────────────────────────────────────


AR_SOURCE_GL = "General Ledger"
AR_SOURCE_INVOICES = "Sales Invoice Outstanding"


def get_ar_source() -> str:
	"""Which receivable measure the credit checks run on. Defaults to the ledger.

	Tolerates the field not existing: get_single_value throws on an unknown
	fieldname, and code reaches a server a moment before `bench migrate` adds the
	column. A credit check must not explode in that window.
	"""
	try:
		source = frappe.db.get_single_value("Credit Policy Settings", "ar_source")
	except Exception:
		source = None
	return source or AR_SOURCE_GL


def get_ledger_outstanding(customers: list[str]) -> float:
	"""Net receivable balance in the GL for these parties, in company currency.

	Sums debit - credit over every non-cancelled GL Entry on a Receivable account
	for the party, so unallocated payments, journal credits and credit notes all
	count against what the customer owes — which is the whole point of reading the
	ledger instead of the invoice list. debit/credit are already company currency,
	so nothing is converted here.

	Floored at zero per group: a customer sitting on an on-account credit consumes
	none of their line, but that credit must not silently *extend* the line beyond
	the approved limit. Granting more than the approved figure is Finance's
	decision, not an arithmetic side effect.
	"""
	if not customers:
		return 0.0

	gle = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	rows = (
		frappe.qb.from_(gle)
		.join(account)
		.on(account.name == gle.account)
		.select(Sum(gle.debit - gle.credit).as_("balance"))
		.where(
			(gle.party_type == "Customer")
			& (gle.party.isin(customers))
			& (gle.is_cancelled == 0)
			& (account.account_type == "Receivable")
		)
	).run(as_dict=True)

	balance = flt(rows[0].balance) if rows else 0.0
	return max(0.0, balance)


def get_invoice_outstanding(customers: list[str]) -> float:
	"""Receivable exposure for these customers, per the configured AR source.

	Name kept for its callers and the decision log; the ledger is the default
	measure now — see get_ledger_outstanding.
	"""
	if not customers:
		return 0.0

	if get_ar_source() != AR_SOURCE_INVOICES:
		return get_ledger_outstanding(customers)

	si = frappe.qb.DocType("Sales Invoice")
	rows = (
		frappe.qb.from_(si)
		.select(si.outstanding_amount, si.conversion_rate)
		.where(
			(si.docstatus == 1)
			& (si.customer.isin(customers))
			& (si.outstanding_amount > 0)
		)
	).run(as_dict=True)

	return flt(sum(flt(row.outstanding_amount) * flt(row.conversion_rate or 1) for row in rows))


def get_unbilled_terms_exposure(
	customers: list[str], exclude_sales_order: str | list[str] | None = None
) -> float:
	"""Credit portion of submitted Terms Sales Orders not yet fully invoiced."""
	if not customers:
		return 0.0

	so = frappe.qb.DocType("Sales Order")
	query = (
		frappe.qb.from_(so)
		.select(
			so.name,
			so.grand_total,
			so.conversion_rate,
			so.per_billed,
			so.payment_terms_template,
			so.custom_sales_order_type,
			so.custom_mode_of_payment,
		)
		.where(
			(so.docstatus == 1)
			& (so.customer.isin(customers))
			& (so.status.notin(DEAD_SO_STATUSES))
			& (so.per_billed < 100)
		)
	)
	if exclude_sales_order:
		# Accepts one order or several: an invoice can bill more than one, and
		# each of those orders stops being unbilled exposure the moment it does.
		excluded = (
			[exclude_sales_order]
			if isinstance(exclude_sales_order, str)
			else list(exclude_sales_order)
		)
		if excluded:
			query = query.where(so.name.notin(excluded))

	total = 0.0
	for row in query.run(as_dict=True):
		if utils.resolve_order_type(row) != utils.ORDER_TYPE_TERMS:
			continue
		unbilled = flt(row.grand_total) * (100.0 - flt(row.per_billed)) / 100.0
		credit_portion = utils.template_credit_portion(row.payment_terms_template) / 100.0
		total += unbilled * credit_portion * flt(row.conversion_rate or 1)

	return flt(total)


DEFAULT_CUSTOMER_AR_CAP = 400_000.0


def get_customer_ar_cap() -> float:
	"""The per-customer AR ceiling. An explicit 0 switches the cap off.

	Read from the raw Singles row rather than through get_single_value, which
	casts a Currency field to 0.0 when nothing is stored — making "never
	configured" indistinguishable from "deliberately disabled". Defaulting a
	safety cap to off because nobody had opened the settings form is exactly the
	wrong way round, so: no row means not configured, and the default applies;
	only a row holding 0 turns the cap off.
	"""
	# Raw SQL, not get_value: tabSingles has no `modified` column and get_value
	# appends ORDER BY modified, so it raises on that table.
	rows = frappe.db.sql(
		"SELECT value FROM tabSingles WHERE doctype = %s AND field = %s",
		("Credit Policy Settings", "customer_ar_cap"),
	)
	stored = rows[0][0] if rows else None

	if stored is None or str(stored).strip() == "":
		return DEFAULT_CUSTOMER_AR_CAP
	return flt(stored)


def is_internal_customer(customer: str | None) -> bool:
	"""Is this "customer" really one of our own entities?

	Intercompany billing runs through Customer records that stand for a Company
	(Motley Terpz, TSBC Ranch, MT...). Their receivable balances are large by
	construction — Motley Terpz alone carries seven figures — and they are not
	credit risk, so the per-customer AR cap must not treat them as a delinquent
	buyer and stop internal work. Same three tests the AR dashboard uses.
	"""
	if not customer:
		return False
	if frappe.db.exists("Company", customer):
		return True
	row = frappe.db.get_value(
		"Customer", customer, ["is_internal_customer", "represents_company"], as_dict=True
	)
	if not row:
		return False
	return bool(row.is_internal_customer or row.represents_company)


def get_customer_ar(customer: str) -> float:
	"""Receivables owed by this customer's credit group, per the configured AR
	source. Open orders are deliberately excluded: this is AR, not exposure."""
	if not customer:
		return 0.0
	return flt(get_invoice_outstanding(get_credit_group_members(customer)))


def get_exposure(customer: str, exclude_sales_order: str | list[str] | None = None) -> dict:
	"""Full group exposure breakdown for a customer."""
	members = get_credit_group_members(customer)
	invoice_outstanding = get_invoice_outstanding(members)
	unbilled = get_unbilled_terms_exposure(members, exclude_sales_order=exclude_sales_order)

	return {
		"customer": customer,
		"group_parent": get_credit_group_parent(customer),
		"members": members,
		"invoice_outstanding": invoice_outstanding,
		"unbilled_terms": unbilled,
		"total": flt(invoice_outstanding + unbilled),
	}


def get_current_exposure(customer: str, exclude_sales_order: str | list[str] | None = None) -> float:
	return get_exposure(customer, exclude_sales_order=exclude_sales_order)["total"]


# ── Approved limit and available line ────────────────────────────────────────


def get_approved_limit(customer: str) -> float:
	"""The group-wide approved limit — read from the group parent."""
	root = get_credit_group_parent(customer)
	if not root:
		return 0.0
	return flt(frappe.db.get_value("Customer", root, "custom_approved_credit_limit"))


def get_available_line(customer: str, exclude_sales_order: str | list[str] | None = None) -> float:
	"""Approved limit less group exposure. May legitimately go negative."""
	return flt(
		get_approved_limit(customer)
		- get_current_exposure(customer, exclude_sales_order=exclude_sales_order)
	)


def get_line_summary(customer: str, exclude_sales_order: str | list[str] | None = None) -> dict:
	"""Everything the Sales Order gate and the approval email need, in one read."""
	exposure = get_exposure(customer, exclude_sales_order=exclude_sales_order)
	limit = get_approved_limit(customer)
	available = flt(limit - exposure["total"])

	exposure.update(
		{
			"approved_limit": limit,
			"available_line": available,
			"utilisation_percent": flt(exposure["total"] / limit * 100.0) if limit else 0.0,
		}
	)
	return exposure


# ── Credit application state ─────────────────────────────────────────────────


def get_active_credit_application(customer: str) -> dict | None:
	"""The live, approved application for the credit group.

	Returns the application dict, or None when the customer has no live line.
	There is no validity window any more — a line stays live until someone
	explicitly revokes it through the workflow.
	"""
	if not customer:
		return None

	if not frappe.db.exists("DocType", "Credit Application"):
		# Phase 2 has not been installed yet.
		return None

	members = get_credit_group_members(customer)
	rows = frappe.get_all(
		"Credit Application",
		filters={
			"customer": ("in", members),
			"docstatus": 1,
			"workflow_state": "Approved",
		},
		fields=[
			"name",
			"customer",
			"approved_limit",
			"approved_terms",
			"credit_agreement_signed",
			"credit_agreement_document",
		],
		order_by="modified desc",
		limit=1,
	)

	# The MD's approval is the gate on its own — terms go live on submit
	# regardless of agreement status (see CreditApplication.on_submit). The
	# signed agreement is tracked but no longer required for the line to be
	# usable.
	return rows[0] if rows else None


def describe_line_blocker(customer: str) -> str | None:
	"""Why this customer cannot take terms right now, phrased for Sales.

	Returns None when terms are available.
	"""
	if not customer:
		return None

	if not frappe.db.exists("DocType", "Credit Application"):
		return None

	members = get_credit_group_members(customer)
	rows = frappe.get_all(
		"Credit Application",
		filters={"customer": ("in", members), "docstatus": 1},
		fields=["name", "workflow_state"],
		order_by="modified desc",
	)

	approved = [row for row in rows if row.workflow_state == "Approved"]

	if not approved:
		latest = rows[0] if rows else None
		if latest and latest.workflow_state in ("Revoked", "Expired"):
			return frappe._(
				"Terms not available — the credit line for {0} is {1}. A new Credit "
				"Application must be approved before terms can be used again."
			).format(frappe.bold(customer), latest.workflow_state.lower())

		return frappe._(
			"Terms not available — {0} has no approved credit line. The customer must "
			"complete the Line of Credit form and sign the Credit Agreement."
		).format(frappe.bold(customer))

	# Approved is live on its own now (see CreditApplication.on_submit) — a
	# missing signed agreement is a paperwork reminder, not a terms blocker.
	return None


# ── Customer roll-up ─────────────────────────────────────────────────────────


def refresh_customer_exposure(customer: str):
	"""Write the cached exposure figures back onto the Customer record."""
	summary = get_line_summary(customer)
	frappe.db.set_value(
		"Customer",
		customer,
		{
			"custom_current_exposure": summary["total"],
			"custom_available_line": summary["available_line"],
		},
		update_modified=False,
	)
	return summary


def get_past_due_snapshot(customer: str) -> dict:
	"""Past-due position for the credit group, as of today.

	Used by the hold engine and by the release guard, which must recompute live
	rather than trust a stored figure.
	"""
	members = get_credit_group_members(customer)
	if not members:
		return {"past_due_amount": 0.0, "max_days_past_due": 0, "total_outstanding": 0.0}

	si = frappe.qb.DocType("Sales Invoice")
	rows = (
		frappe.qb.from_(si)
		.select(si.name, si.due_date, si.outstanding_amount, si.conversion_rate)
		.where(
			(si.docstatus == 1)
			& (si.customer.isin(members))
			& (si.outstanding_amount > 0)
		)
	).run(as_dict=True)

	today = getdate(nowdate())
	past_due_amount = 0.0
	total_outstanding = 0.0
	max_days = 0

	for row in rows:
		amount = flt(row.outstanding_amount) * flt(row.conversion_rate or 1)
		total_outstanding += amount
		if not row.due_date:
			continue
		days = (today - getdate(row.due_date)).days
		if days > 0:
			past_due_amount += amount
			max_days = max(max_days, days)

	return {
		"past_due_amount": flt(past_due_amount),
		"max_days_past_due": max_days,
		"total_outstanding": flt(total_outstanding),
	}


def get_total_ar(new_book_only: bool = True, company: str | None = None) -> float:
	"""Company-wide AR. The freeze engine governs the new book only.

	With no ``policy_effective_date`` set there is no New Book yet, so a
	new-book request returns zero rather than passing the entire legacy balance
	off as new exposure. Pass ``new_book_only=False`` for the true total.
	"""
	effective_date = utils.policy_effective_date()
	if new_book_only and not effective_date:
		return 0.0

	si = frappe.qb.DocType("Sales Invoice")
	query = (
		frappe.qb.from_(si)
		.select(Sum(si.outstanding_amount * si.conversion_rate))
		.where((si.docstatus == 1) & (si.outstanding_amount > 0))
	)
	if company:
		query = query.where(si.company == company)

	if new_book_only:
		query = query.where(si.posting_date >= effective_date)

	result = query.run()
	return flt(result[0][0]) if result and result[0] else 0.0
