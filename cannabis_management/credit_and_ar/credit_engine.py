"""Exposure and available-line arithmetic.

The credit line is a **single group-wide line**: one approved limit per customer
group, consumed by every operating company (TSBC Ranch, Motley Terpz, Master
Touch Manufacturing) and by every Customer record sharing the same
``custom_credit_group_parent``. A buyer cannot stack three lines by trading with
three entities.

What counts as exposure
-----------------------
* **Every** submitted Sales Invoice with an outstanding balance — new book and
  legacy alike. Money owed is money owed; the Legacy/New Book split governs the
  company-wide freeze and finance charges, not a customer's own line.
* Submitted, not-yet-fully-billed **Terms** Sales Orders, at the portion of the
  order actually extended on credit. A COD order is not credit until it becomes
  an unpaid invoice, and the paid-up-front half of a 50%-down order was never at
  risk.
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


def get_invoice_outstanding(customers: list[str]) -> float:
	"""Outstanding on submitted Sales Invoices, in company currency."""
	if not customers:
		return 0.0

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


def get_unbilled_terms_exposure(customers: list[str], exclude_sales_order: str | None = None) -> float:
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
		query = query.where(so.name != exclude_sales_order)

	total = 0.0
	for row in query.run(as_dict=True):
		if utils.resolve_order_type(row) != utils.ORDER_TYPE_TERMS:
			continue
		unbilled = flt(row.grand_total) * (100.0 - flt(row.per_billed)) / 100.0
		credit_portion = utils.template_credit_portion(row.payment_terms_template) / 100.0
		total += unbilled * credit_portion * flt(row.conversion_rate or 1)

	return flt(total)


def get_exposure(customer: str, exclude_sales_order: str | None = None) -> dict:
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


def get_current_exposure(customer: str, exclude_sales_order: str | None = None) -> float:
	return get_exposure(customer, exclude_sales_order=exclude_sales_order)["total"]


# ── Approved limit and available line ────────────────────────────────────────


def get_approved_limit(customer: str) -> float:
	"""The group-wide approved limit — read from the group parent."""
	root = get_credit_group_parent(customer)
	if not root:
		return 0.0
	return flt(frappe.db.get_value("Customer", root, "custom_approved_credit_limit"))


def get_available_line(customer: str, exclude_sales_order: str | None = None) -> float:
	"""Approved limit less group exposure. May legitimately go negative."""
	return flt(
		get_approved_limit(customer)
		- get_current_exposure(customer, exclude_sales_order=exclude_sales_order)
	)


def get_line_summary(customer: str, exclude_sales_order: str | None = None) -> dict:
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
		fields=["name", "customer", "approved_limit", "approved_terms", "counsel_approved_clause"],
		order_by="modified desc",
		limit=1,
	)

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

	if not rows or not any(row.workflow_state == "Approved" for row in rows):
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
