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
# The Legacy / New AR cut-over. Everything invoiced on or before 2026-05-31 is
# the legacy book — worked through separately (see the AR Legacy page) and
# deliberately outside the $400k ceiling. New AR starts 2026-06-01.
NEW_AR_START = "2026-06-01"

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


# Statuses where the Available Line is enforced on every Sales Order, whatever
# the payment mode. COD is included deliberately: cash carries no credit risk in
# principle, but an account already at its ceiling should not keep taking work on
# any terms until the balance comes down.
LINE_ENFORCED_STATUSES = (
	STATUS_TERMS_APPROVED,
	STATUS_WARNING,
	STATUS_HARD_HOLD,
	STATUS_BLOCKED,
)

# The one role that may raise — and print — an order above the line.
LINE_OVERRIDE_ROLE = "Account Manager"


def can_override_line(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return LINE_OVERRIDE_ROLE in frappe.get_roles(user)


# Statuses that come from a live AR Case rather than the account's own standing.
# A Payment Plan or Workout is a *resolution* on the hold case: the account is
# still under Finance's control even though it is no longer stopped.
CASE_DRIVEN_STATUSES = (STATUS_HARD_HOLD, STATUS_PAYMENT_PLAN, STATUS_WORKOUT)


# ── Payment plan installment status ──────────────────────────────────────────
# AR Case Installment.status is always derived, never hand-set — Finance cannot
# type "Paid" onto a row, even for a Custom-frequency plan. See README §6.
INSTALLMENT_PENDING = "Pending"
INSTALLMENT_PAID = "Paid"
INSTALLMENT_PARTIALLY_PAID = "Partially Paid"
INSTALLMENT_MISSED = "Missed"


def installment_status(amount, paid_amount, due_date, today=None) -> str:
	"""The one place an installment's status is decided.

	Paid              full installment amount has been paid.
	Missed            due date has passed and the required amount is still
	                  outstanding — outranks Partially Paid, since a partial
	                  payment on an overdue installment is still a default.
	Partially Paid    some amount paid, not yet overdue, not yet full.
	Pending           nothing paid (or not enough), due date not yet passed.
	"""
	amount = flt(amount)
	paid_amount = flt(paid_amount)
	today = today or getdate()

	if amount > 0 and paid_amount + 0.005 >= amount:
		return INSTALLMENT_PAID
	if due_date and getdate(due_date) < today:
		return INSTALLMENT_MISSED
	if paid_amount > 0.005:
		return INSTALLMENT_PARTIALLY_PAID
	return INSTALLMENT_PENDING


def ar_cap_enabled() -> bool:
	"""Is the $400,000 AR ceiling switched on? Selling Settings -> Enforce $400,000 AR Cap.

	Read from the raw Singles row rather than through get_single_value, which
	casts an unset Check to 0 and would make "nobody has opened the settings
	form" indistinguishable from "deliberately switched off". A safety ceiling
	must not fall away just because a site has never saved that form, so no row
	means enabled; only an explicit 0 disables it.
	"""
	rows = frappe.db.sql(
		"SELECT value FROM tabSingles WHERE doctype = %s AND field = %s",
		("Selling Settings", "custom_enforce_ar_cap"),
	)
	stored = rows[0][0] if rows else None
	if stored is None or str(stored).strip() == "":
		return True
	return bool(int(stored))


def is_on_hold(customer: str | None) -> bool:
	"""Is this account stopped? Credit Status = "Hard Hold".

	Replaces the separate custom_on_hold checkbox: two fields describing the same
	thing could disagree, and the status is the one people actually read. A
	Payment Plan or Workout is deliberately NOT a hold — that is the agreed way
	back to trading, not a stop-work order.
	"""
	if not customer:
		return False
	return frappe.get_cached_value("Customer", customer, "custom_credit_status") == STATUS_HARD_HOLD


# ── Hold reasons ─────────────────────────────────────────────────────────────
# Why an account is on Hard Hold, in the language Finance uses. Shown on the
# Customer (custom_hold_reason) and only while the account is on Hard Hold.
#
# Promise to Pay broken, License expired and Credit limit breached are stamped
# by the engines from the AR Case that raised the hold; Payment Returned/Bounced,
# Fraud suspected and Insolvency signs are for a human to select — nothing sets
# them on its own. (The "(Auto)"/"(Manual)" suffixes that used to mark this in
# the option text itself were removed — that was only ever a mapping aid, not
# something Finance needed to see.)
HOLD_REASON_PROMISE = "Promise to Pay broken"
HOLD_REASON_RETURNED = "Payment Returned/Bounced"
HOLD_REASON_LICENSE = "License expired"
HOLD_REASON_FRAUD = "Fraud suspected"
HOLD_REASON_INSOLVENCY = "Insolvency signs"
HOLD_REASON_LIMIT = "Credit limit breached"

HOLD_REASON_OPTIONS = "\n".join([
	"",
	HOLD_REASON_PROMISE,
	HOLD_REASON_RETURNED,
	HOLD_REASON_LICENSE,
	HOLD_REASON_FRAUD,
	HOLD_REASON_INSOLVENCY,
	HOLD_REASON_LIMIT,
])

# AR Case.trigger_reason -> the reason shown on the Customer. Anything missing
# here (notably "Manual") leaves the field alone for a human to fill in.
HOLD_REASON_BY_TRIGGER = {
	"Past Due Days": HOLD_REASON_PROMISE,
	"Past Due Amount": HOLD_REASON_PROMISE,
	"Broken Promise to Pay": HOLD_REASON_PROMISE,
	"Plan Default": HOLD_REASON_PROMISE,
	"Returned Payment": HOLD_REASON_RETURNED,
	"Expired License": HOLD_REASON_LICENSE,
	"Suspected Fraud": HOLD_REASON_FRAUD,
	"Insolvency Signs": HOLD_REASON_INSOLVENCY,
	"Limit Breach": HOLD_REASON_LIMIT,
	"AR Threshold Breach": HOLD_REASON_LIMIT,
}

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
	"""Percentage of the order that counts against the customer's credit line.

	**The whole order, always** — the single knob for this rule, read by the
	exposure engine, the Sales Order gate and the AR reports alike.

	This used to discount a `50% down NETnn` order to its deferred half, on the
	reasoning that the prepaid half was never at risk (decision 3). That premise
	died with decision 17, which stopped the up-front leg from gating submit: the
	order now ships with nothing collected, the full grand total becomes
	receivable, and half of it was invisible to the line. A $30,000 order was
	therefore submitting against a $20,000 limit — measured as $15,000 of credit.

	The up-front leg is still a real due date on the ERPNext payment schedule and
	is still chased like any other due amount; it is simply no longer allowed to
	buy headroom on the credit line that nothing forces the customer to fund.
	"""
	return 100.0


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

	The single switch every engine checks — Credit Status set to "Policy Exempt".
	It used to be a separate checkbox; the status now carries it, so there is one
	field describing where an account stands rather than two that could disagree. When on, nothing in this module
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
	return frappe.get_cached_value("Customer", customer, "custom_credit_status") == STATUS_EXEMPT


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
		"Customer", filters={"custom_credit_status": STATUS_EXEMPT}, pluck="name"
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


def new_ar_start_date():
	"""First day of the new book, as a date.

	Prefers Credit Policy Settings.policy_effective_date where Finance has set
	one, so the module keeps a single cut-over; falls back to NEW_AR_START, which
	is the date the business actually drew the line.
	"""
	return getdate(policy_effective_date() or NEW_AR_START)
