"""Shared helpers for the Credit & AR Control module.

Everything in here is deliberately dependency-light: the settings accessor, the
order-type vocabulary, UOM normalisation and notification routing are read on
almost every transaction, so they must stay cheap.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

# ── Order type vocabulary ────────────────────────────────────────────────────
#
# The gate does NOT introduce a new order-type field. Two fields already live on
# Sales Order and drive existing print formats, dashboards and reports, so the
# credit engine reads them instead of duplicating them:
#
#   custom_sales_order_type  Sales / Samples / Events / Testing / Influencers /
#                            Consignment / Tolling
#   custom_mode_of_payment   Cash On Delivery / Payment Terms
#
# "Samples" wins over the payment mode: a zero-value sample is never a credit
# decision. Anything else with Payment Terms is a Terms order; everything else,
# including the 216 historical Sales Orders with a blank payment mode, is COD.

ORDER_TYPE_COD = "COD"
ORDER_TYPE_TERMS = "Terms"
ORDER_TYPE_SAMPLE = "Sample"

MODE_COD = "Cash On Delivery"
MODE_TERMS = "Payment Terms"

SAMPLE_ORDER_TYPES = ("Samples", "Packaged Goods - Sample")

# custom_approval_status values. "Pending Approval" is kept verbatim from the
# pre-existing flow — renaming it would strand the Sales Orders already carrying
# it and break the print formats that read the field.
APPROVAL_NOT_REQUIRED = "Not Required"
APPROVAL_PENDING = "Pending Approval"
APPROVAL_APPROVED = "Approved"
APPROVAL_REJECTED = "Rejected"

# Ledger vocabulary — shared by Sales Invoice and Payment Entry.
LEDGER_NEW_BOOK = "New Book"
LEDGER_LEGACY = "Legacy"
LEDGER_PLAN = "Plan"
LEDGER_WORKOUT_PAYDOWN = "Workout Paydown"
LEDGER_DEPOSIT = "Deposit"

# Credit status vocabulary on Customer.
STATUS_COD = "COD"
STATUS_EXEMPT = "Policy Exempt"
STATUS_TERMS_APPROVED = "Terms Approved"
STATUS_WARNING = "Warning"
STATUS_HARD_HOLD = "Hard Hold"
STATUS_PAYMENT_PLAN = "Payment Plan"
STATUS_WORKOUT = "Workout"
STATUS_BLOCKED = "Blocked"

HOLD_NONE = "None"
HOLD_WARNING = "Warning"
HOLD_HARD = "Hard Hold"
HOLD_IMMEDIATE = "Immediate Hold"

BLOCKING_HOLDS = (HOLD_HARD, HOLD_IMMEDIATE)

GRAMS_PER_POUND = 453.59237

# TSBC reports in pounds; the other operating companies report in grams.
POUND_REPORTING_COMPANIES = ("TSBC Ranch",)


# ── Settings ─────────────────────────────────────────────────────────────────


def get_settings():
	"""Cached Credit Policy Settings. Read on nearly every transaction."""
	return frappe.get_cached_doc("Credit Policy Settings", "Credit Policy Settings")


def policy_effective_date():
	"""The Legacy/New Book cut-over, or None when the policy has not gone live.

	An empty Date on a Single can come back as ``0001-01-01`` rather than NULL,
	which is truthy — every scheduled job would then believe the policy was
	live and treat the entire legacy book as new. Anything before 1900 is
	treated as unset.
	"""
	value = get_settings().policy_effective_date
	if not value:
		return None

	parsed = getdate(value)
	if not parsed or parsed.year < 1900:
		return None
	return parsed


def policy_is_live() -> bool:
	"""Scheduled jobs no-op until Finance sets the effective date."""
	return policy_effective_date() is not None


def require_policy_live(context: str) -> bool:
	"""Guard for scheduled jobs. Logs once per run rather than throwing."""
	if policy_is_live():
		return True
	frappe.logger("credit_and_ar").info(
		f"{context} skipped — Credit Policy Settings.policy_effective_date is not set."
	)
	return False


def settings_list(fieldname: str) -> list[str]:
	"""Read one of the comma-separated Settings fields as a clean list."""
	raw = get_settings().get(fieldname)
	if not raw:
		return []
	return [part.strip() for part in raw.split(",") if part.strip()]


# ── Order type resolution ────────────────────────────────────────────────────


def resolve_order_type(doc) -> str:
	"""Map the two existing Sales Order fields onto COD / Terms / Sample."""
	if (doc.get("custom_sales_order_type") or "") in SAMPLE_ORDER_TYPES:
		return ORDER_TYPE_SAMPLE
	if (doc.get("custom_mode_of_payment") or "") == MODE_TERMS:
		return ORDER_TYPE_TERMS
	return ORDER_TYPE_COD


def is_terms_order(doc) -> bool:
	return resolve_order_type(doc) == ORDER_TYPE_TERMS


def is_cash_order(doc) -> bool:
	"""Mode of Payment = Cash On Delivery — the policy-free path.

	A cash order carries no credit exposure: the money arrives with the product.
	The Credit & AR policy therefore does not apply to it at all — no approval, no
	credit line, no deposit, no print block, no hold — and ERPNext's own defaults
	are left alone, including ``payment_terms_template``.

	The one thing a cash order still owes is a workout paydown, kept deliberately:
	without it a customer on a workout plan could move every order to cash and
	never pay down the old balance. See the README decision log.

	Note this returns True for an order with no Mode of Payment set, matching
	``resolve_order_type`` — ``_default_payment_mode`` fills a blank with cash.
	"""
	return resolve_order_type(doc) == ORDER_TYPE_COD


def is_sample_order(doc) -> bool:
	return resolve_order_type(doc) == ORDER_TYPE_SAMPLE


# ── Payment terms ────────────────────────────────────────────────────────────


def template_credit_days(template: str | None) -> int:
	"""Longest credit period in a Payment Terms Template, in days."""
	if not template:
		return 0
	rows = frappe.get_all(
		"Payment Terms Template Detail",
		filters={"parent": template},
		pluck="credit_days",
	)
	return max([int(days or 0) for days in rows], default=0)


def template_upfront_portion(template: str | None) -> float:
	"""Percentage of the invoice due on day zero — the deposit leg of 50%-down terms."""
	if not template:
		return 0.0
	rows = frappe.get_all(
		"Payment Terms Template Detail",
		filters={"parent": template, "credit_days": 0},
		pluck="invoice_portion",
	)
	return flt(sum(flt(row) for row in rows))


def template_credit_portion(template: str | None) -> float:
	"""Percentage of the order that is genuinely extended on credit.

	A 50%-down template puts only the deferred half at risk, so only that half
	is charged against the customer's available line.
	"""
	if not template:
		return 100.0
	upfront = template_upfront_portion(template)
	return max(0.0, 100.0 - upfront)


# ── UOM normalisation ────────────────────────────────────────────────────────


def to_grams(qty: float, uom: str | None, item_code: str | None = None) -> float:
	"""Normalise a sold quantity to grams.

	Falls back through the item's UOM Conversion Detail, then the global UOM
	Conversion Factor table, then a hard-coded pound conversion. Returns 0 for
	units that carry no weight meaning (Nos, Box, …) rather than guessing.
	"""
	qty = flt(qty)
	if not qty or not uom:
		return 0.0

	normalised = uom.strip().lower()
	if normalised in ("g", "gram", "grams"):
		return qty
	if normalised in ("lb", "lbs", "pound", "pounds"):
		return qty * GRAMS_PER_POUND
	if normalised in ("kg", "kilogram", "kilograms"):
		return qty * 1000.0
	if normalised in ("mg", "milligram", "milligrams"):
		return qty / 1000.0
	if normalised in ("oz", "ounce", "ounces"):
		return qty * 28.349523125

	# Item-specific conversion, e.g. a Case that holds a known gram weight.
	if item_code:
		factor = frappe.db.get_value(
			"UOM Conversion Detail",
			{"parent": item_code, "uom": uom},
			"conversion_factor",
		)
		if factor:
			stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
			if stock_uom and stock_uom.strip().lower() != normalised:
				return to_grams(qty * flt(factor), stock_uom)

	factor = frappe.db.get_value(
		"UOM Conversion Factor", {"from_uom": uom, "to_uom": "Gram"}, "value"
	)
	if factor:
		return qty * flt(factor)

	return 0.0


def grams_to_lbs(grams: float) -> float:
	return flt(grams) / GRAMS_PER_POUND


def reports_in_pounds(company: str | None) -> bool:
	return (company or "") in POUND_REPORTING_COMPANIES


# ── Notification routing ─────────────────────────────────────────────────────


def routed_user(fieldname: str) -> str | None:
	"""Read a routing slot from Settings, skipping blanks with a log line."""
	user = get_settings().get(fieldname)
	if not user:
		frappe.logger("credit_and_ar").info(
			f"Credit Policy Settings.{fieldname} is not set — notification recipient skipped."
		)
		return None
	if not frappe.db.get_value("User", user, "enabled"):
		frappe.logger("credit_and_ar").warning(
			f"Credit Policy Settings.{fieldname} points at disabled or missing user {user}."
		)
		return None
	return user


def users_with_role(role: str | None) -> list[str]:
	if not role:
		return []
	users = frappe.get_all(
		"Has Role",
		filters={"role": role, "parenttype": "User"},
		pluck="parent",
	)
	if not users:
		return []
	return frappe.get_all(
		"User",
		filters={"name": ("in", users), "enabled": 1, "user_type": "System User"},
		pluck="name",
	)


def is_policy_exempt(customer: str | None) -> bool:
	"""Is this customer carved out of the Credit & AR policy entirely?

	The single switch every engine checks. When on, nothing in this module
	touches the account: no Sales Order gate, no holds, no AR Cases, no ledger
	enforcement, no finance charges, no scoring. The account behaves exactly as
	it did before the module existed.

	What it does **not** do is hide the money. The customer's AR still counts
	toward the company-wide cap, DSO and CEI, and they still appear on the
	reports — otherwise exempting the largest debtor would quietly switch off
	the freeze engine for everyone.
	"""
	if not customer:
		return False
	return bool(frappe.get_cached_value("Customer", customer, "custom_credit_policy_exempt"))


def company_of(customer: str | None) -> str | None:
	"""The company a customer most recently traded with.

	The credit line is group-wide, so a Credit Application carries no company of
	its own. Where one is still needed — mirroring the native Customer Credit
	Limit row, stamping an AR Case — it is derived from the customer's own
	trading history rather than asked for again.
	"""
	if customer:
		rows = frappe.get_all(
			"Sales Invoice",
			filters={"customer": customer, "docstatus": 1},
			fields=["company"],
			order_by="posting_date desc",
			limit=1,
		)
		if rows:
			return rows[0].company

	# Fall back through the usual defaults, then to any real company — a brand
	# new customer has no trading history, and the native credit-limit row still
	# has to land somewhere.
	fallback = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if fallback:
		return fallback

	rows = frappe.get_all("Company", filters={"is_group": 0}, pluck="name", limit=1)
	return rows[0] if rows else None


def exempt_customers() -> list[str]:
	"""Every account carved out of the policy — for bulk filters in the engines."""
	return frappe.get_all(
		"Customer", filters={"custom_credit_policy_exempt": 1}, pluck="name"
	)


def intercompany_customers() -> list[str]:
	"""Customer records that are really our own operating entities.

	Excluded from every credit report *and* from the company metrics: a balance
	between two of our own companies is not unsecured customer credit, and
	counting it toward the AR cap would trip the freeze on money we owe
	ourselves.
	"""
	names = frappe.get_all("Customer", filters={"custom_is_intercompany": 1}, pluck="name")

	group = get_settings().intercompany_customer_group
	if group:
		names += frappe.get_all("Customer", filters={"customer_group": group}, pluck="name")

	return list(set(names))


def finance_recipients() -> list[str]:
	settings = get_settings()
	role = settings.finance_notification_role or "Credit Finance"
	users = users_with_role(role)
	if not users:
		# Every credit notification routes through this role. An empty result
		# means the whole module goes quiet, so say so rather than return [] and
		# let each caller return early in silence.
		frappe.logger("credit_and_ar").warning(
			f"No enabled System User holds the {role} role — credit notifications have no recipients."
		)
	return users


def dedupe_recipients(*groups) -> list[str]:
	"""Flatten recipient groups, drop blanks and duplicates, preserve order.

	``Guest`` is dropped. Anything submitted through a public web form is owned
	by Guest, so ``doc.owner`` lands here as the literal string "Guest" — not an
	address. Frappe validates every Email Queue recipient, so one bad entry
	raises and the *whole* notification is lost, including the real Finance
	recipients alongside it. Guest is also never a valid ToDo assignee, so the
	filter is safe for the approver-routing callers too.
	"""
	seen: dict[str, None] = {}
	for group in groups:
		if not group:
			continue
		items = [group] if isinstance(group, str) else group
		for item in items:
			if item and item != "Guest" and item not in seen:
				seen[item] = None
	return list(seen)


# ── Misc ─────────────────────────────────────────────────────────────────────


def fmt_currency(amount, currency: str = "USD") -> str:
	return frappe.utils.fmt_money(flt(amount), currency=currency)


def doc_link(doctype: str, name: str) -> str:
	url = frappe.utils.get_url(f"/app/{frappe.scrub(doctype).replace('_', '-')}/{name}")
	return f'<a href="{url}">{frappe.utils.escape_html(name)}</a>'


def has_any_role(*roles) -> bool:
	user_roles = set(frappe.get_roles(frappe.session.user))
	return bool(user_roles.intersection(roles))


def throw_consolidated(problems: list[str], title: str):
	"""Raise every missing requirement at once instead of one per save."""
	if not problems:
		return
	items = "".join(f"<li>{problem}</li>" for problem in problems)
	frappe.throw(f"<ul style='margin:0 0 0 16px;padding:0'>{items}</ul>", title=_(title))
