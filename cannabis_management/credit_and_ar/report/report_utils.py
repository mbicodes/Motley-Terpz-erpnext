"""Shared helpers for the Credit & AR reports.

The AR aggregates are computed **in bulk** — one query across every customer in
scope — rather than per row. A per-customer round trip is fine for one Sales
Order gate; across 249 customers on a report refresh it is not.
"""

import frappe
from frappe.utils import flt, getdate, nowdate

from cannabis_management.credit_and_ar import utils

# A score of 0 means "no score": Frappe Int columns cannot hold null, so the
# band is the authoritative signal. See scoring._store.
NO_SCORE_BAND = "Insufficient History"


def customer_filters(filters: dict | None = None) -> dict:
	"""Base Customer filters, always excluding intercompany accounts."""
	filters = filters or {}
	conditions = {"disabled": 0, "custom_is_intercompany": 0}

	if filters.get("customer"):
		conditions["name"] = filters["customer"]
	if filters.get("customer_group"):
		conditions["customer_group"] = filters["customer_group"]
	if filters.get("score_band"):
		conditions["custom_score_band"] = filters["score_band"]
	if filters.get("credit_status"):
		conditions["custom_credit_status"] = filters["credit_status"]

	return conditions


def intercompany_group() -> str | None:
	return utils.get_settings().intercompany_customer_group


def excluded_customers() -> list[str]:
	"""Customers kept off every client-facing credit report."""
	names = frappe.get_all("Customer", filters={"custom_is_intercompany": 1}, pluck="name")

	group = intercompany_group()
	if group:
		names += frappe.get_all("Customer", filters={"customer_group": group}, pluck="name")

	return list(set(names))


def ar_by_customer(company: str | None = None, customers: list[str] | None = None) -> dict:
	"""Outstanding, past due and worst age per customer, in one pass."""
	conditions = ["si.docstatus = 1", "si.outstanding_amount > 0"]
	values: dict = {}

	if company:
		conditions.append("si.company = %(company)s")
		values["company"] = company
	if customers:
		conditions.append("si.customer IN %(customers)s")
		values["customers"] = customers

	rows = frappe.db.sql(
		f"""
		SELECT si.customer, si.name, si.due_date, si.posting_date,
		       si.outstanding_amount, si.conversion_rate, si.custom_ledger,
		       si.custom_is_finance_charge
		FROM `tabSales Invoice` si
		WHERE {" AND ".join(conditions)}
		""",
		values,
		as_dict=True,
	)

	today = getdate(nowdate())
	result: dict[str, dict] = {}

	for row in rows:
		bucket = result.setdefault(
			row.customer,
			{
				"outstanding": 0.0,
				"past_due": 0.0,
				"max_days": 0,
				"legacy": 0.0,
				"new_book": 0.0,
				"finance_charges": 0.0,
				"invoice_count": 0,
			},
		)
		amount = flt(row.outstanding_amount) * flt(row.conversion_rate or 1)

		bucket["outstanding"] += amount
		bucket["invoice_count"] += 1

		if row.custom_is_finance_charge:
			bucket["finance_charges"] += amount
		elif row.custom_ledger == utils.LEDGER_LEGACY:
			bucket["legacy"] += amount
		else:
			bucket["new_book"] += amount

		if row.due_date:
			days = (today - getdate(row.due_date)).days
			if days > 0:
				bucket["past_due"] += amount
				bucket["max_days"] = max(bucket["max_days"], days)

	return result


def unbilled_terms_by_customer(customers: list[str] | None = None) -> dict:
	"""Credit portion of submitted, not-fully-billed Terms orders, per customer."""
	conditions = ["so.docstatus = 1", "so.per_billed < 100", "so.status NOT IN ('Closed', 'Cancelled')"]
	values: dict = {}

	if customers:
		conditions.append("so.customer IN %(customers)s")
		values["customers"] = customers

	rows = frappe.db.sql(
		f"""
		SELECT so.customer, so.grand_total, so.conversion_rate, so.per_billed,
		       so.payment_terms_template, so.custom_sales_order_type, so.custom_mode_of_payment
		FROM `tabSales Order` so
		WHERE {" AND ".join(conditions)}
		""",
		values,
		as_dict=True,
	)

	result: dict[str, float] = {}
	for row in rows:
		if utils.resolve_order_type(row) != utils.ORDER_TYPE_TERMS:
			continue
		unbilled = flt(row.grand_total) * (100.0 - flt(row.per_billed)) / 100.0
		portion = utils.template_credit_portion(row.payment_terms_template) / 100.0
		result[row.customer] = result.get(row.customer, 0.0) + unbilled * portion * flt(
			row.conversion_rate or 1
		)

	return result


def score_or_none(customer_row) -> int | None:
	"""Render a stored 0 as "no score" when the band says so."""
	if customer_row.get("custom_score_band") in (None, "", NO_SCORE_BAND):
		return None
	return customer_row.get("custom_payment_score") or None


def days_to_expiry(valid_until) -> int | None:
	if not valid_until:
		return None
	return (getdate(valid_until) - getdate(nowdate())).days


def attachment_link(url: str | None, label: str) -> str:
	if not url:
		return ""
	return f'<a href="{frappe.utils.escape_html(url)}" target="_blank">{label}</a>'
