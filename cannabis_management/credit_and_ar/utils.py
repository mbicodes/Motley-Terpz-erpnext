import frappe
from frappe import _
from frappe.utils import flt, getdate

ORDER_TYPE_COD = "COD"
ORDER_TYPE_TERMS = "Terms"
ORDER_TYPE_SAMPLE = "Sample"

MODE_COD = "Cash On Delivery"
MODE_TERMS = "Payment Terms"

SAMPLE_ORDER_TYPES = ("Samples", "Packaged Goods - Sample")

APPROVAL_NOT_REQUIRED = "Not Required"
APPROVAL_PENDING = "Pending Approval"
APPROVAL_APPROVED = "Approved"
APPROVAL_REJECTED = "Rejected"

NEW_AR_START = "2026-06-01"

LEDGER_NEW_BOOK = "New Book"
LEDGER_LEGACY = "Legacy"
LEDGER_PLAN = "Plan"
LEDGER_WORKOUT_PAYDOWN = "Workout Paydown"
LEDGER_DEPOSIT = "Deposit"

STATUS_COD = "COD"
STATUS_EXEMPT = "Policy Exempt"
STATUS_TERMS_APPROVED = "Terms Approved"
STATUS_WARNING = "Warning"
STATUS_HARD_HOLD = "Hard Hold"
STATUS_PAYMENT_PLAN = "Payment Plan"
STATUS_WORKOUT = "Workout"
STATUS_BLOCKED = "Blocked"

LINE_ENFORCED_STATUSES = (
	STATUS_TERMS_APPROVED,
	STATUS_WARNING,
	STATUS_HARD_HOLD,
	STATUS_BLOCKED,
)

LINE_OVERRIDE_ROLE = "Account Manager"


def can_override_line(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return LINE_OVERRIDE_ROLE in frappe.get_roles(user)

CASE_DRIVEN_STATUSES = (STATUS_HARD_HOLD, STATUS_PAYMENT_PLAN, STATUS_WORKOUT)

INSTALLMENT_PENDING = "Pending"
INSTALLMENT_PAID = "Paid"
INSTALLMENT_PARTIALLY_PAID = "Partially Paid"
INSTALLMENT_MISSED = "Missed"


def installment_status(amount, paid_amount, due_date, today=None) -> str:
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
	rows = frappe.db.sql(
		"SELECT value FROM tabSingles WHERE doctype = %s AND field = %s",
		("Selling Settings", "custom_enforce_ar_cap"),
	)
	stored = rows[0][0] if rows else None
	if stored is None or str(stored).strip() == "":
		return True
	return bool(int(stored))


def is_on_hold(customer: str | None) -> bool:
	if not customer:
		return False
	return frappe.get_cached_value("Customer", customer, "custom_credit_status") == STATUS_HARD_HOLD

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

POUND_REPORTING_COMPANIES = ("TSBC Ranch",)


def get_settings():
	return frappe.get_cached_doc("Credit Policy Settings", "Credit Policy Settings")


def policy_effective_date():
	value = get_settings().policy_effective_date
	if not value:
		return None

	parsed = getdate(value)
	if not parsed or parsed.year < 1900:
		return None
	return parsed


def policy_is_live() -> bool:
	return policy_effective_date() is not None


def require_policy_live(context: str) -> bool:
	if policy_is_live():
		return True
	frappe.logger("credit_and_ar").info(
		f"{context} skipped — Credit Policy Settings.policy_effective_date is not set."
	)
	return False


def settings_list(fieldname: str) -> list[str]:
	raw = get_settings().get(fieldname)
	if not raw:
		return []
	return [part.strip() for part in raw.split(",") if part.strip()]


def resolve_order_type(doc) -> str:
	if (doc.get("custom_sales_order_type") or "") in SAMPLE_ORDER_TYPES:
		return ORDER_TYPE_SAMPLE
	if (doc.get("custom_mode_of_payment") or "") == MODE_TERMS:
		return ORDER_TYPE_TERMS
	return ORDER_TYPE_COD


def is_terms_order(doc) -> bool:
	return resolve_order_type(doc) == ORDER_TYPE_TERMS


def is_cash_order(doc) -> bool:
	return resolve_order_type(doc) == ORDER_TYPE_COD


def is_sample_order(doc) -> bool:
	return resolve_order_type(doc) == ORDER_TYPE_SAMPLE


def template_credit_days(template: str | None) -> int:
	if not template:
		return 0
	rows = frappe.get_all(
		"Payment Terms Template Detail",
		filters={"parent": template},
		pluck="credit_days",
	)
	return max([int(days or 0) for days in rows], default=0)


def template_upfront_portion(template: str | None) -> float:
	if not template:
		return 0.0
	rows = frappe.get_all(
		"Payment Terms Template Detail",
		filters={"parent": template, "credit_days": 0},
		pluck="invoice_portion",
	)
	return flt(sum(flt(row) for row in rows))


def template_credit_portion(template: str | None) -> float:
	return 100.0


def to_grams(qty: float, uom: str | None, item_code: str | None = None) -> float:
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


def routed_user(fieldname: str) -> str | None:
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
	if not customer:
		return False
	return frappe.get_cached_value("Customer", customer, "custom_credit_status") == STATUS_EXEMPT


def company_of(customer: str | None) -> str | None:
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

	fallback = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if fallback:
		return fallback

	rows = frappe.get_all("Company", filters={"is_group": 0}, pluck="name", limit=1)
	return rows[0] if rows else None


def exempt_customers() -> list[str]:
	return frappe.get_all(
		"Customer", filters={"custom_credit_status": STATUS_EXEMPT}, pluck="name"
	)


def intercompany_customers() -> list[str]:
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
		frappe.logger("credit_and_ar").warning(
			f"No enabled System User holds the {role} role — credit notifications have no recipients."
		)
	return users


def dedupe_recipients(*groups) -> list[str]:
	seen: dict[str, None] = {}
	for group in groups:
		if not group:
			continue
		items = [group] if isinstance(group, str) else group
		for item in items:
			if item and item != "Guest" and item not in seen:
				seen[item] = None
	return list(seen)


def fmt_currency(amount, currency: str = "USD") -> str:
	return frappe.utils.fmt_money(flt(amount), currency=currency)


def doc_link(doctype: str, name: str) -> str:
	url = frappe.utils.get_url(f"/app/{frappe.scrub(doctype).replace('_', '-')}/{name}")
	return f'<a href="{url}">{frappe.utils.escape_html(name)}</a>'


def has_any_role(*roles) -> bool:
	user_roles = set(frappe.get_roles(frappe.session.user))
	return bool(user_roles.intersection(roles))


def throw_consolidated(problems: list[str], title: str):
	if not problems:
		return
	items = "".join(f"<li>{problem}</li>" for problem in problems)
	frappe.throw(f"<ul style='margin:0 0 0 16px;padding:0'>{items}</ul>", title=_(title))


def new_ar_start_date():
	return getdate(policy_effective_date() or NEW_AR_START)
