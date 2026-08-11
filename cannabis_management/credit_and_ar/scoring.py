"""The 350–800 payment score (§15).

The MD's single number for whether an account deserves a line. Every weight and
anchor is a module constant so the model can be retuned without touching the
logic.

Excluded throughout: intercompany customers, sample orders, and finance-charge
invoices — a late fee is a consequence of poor payment, and letting it feed back
into the score would double-count the same behaviour.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, now_datetime, nowdate

from cannabis_management.credit_and_ar import utils

# ── the model ────────────────────────────────────────────────────────────────

SCORE_FLOOR = 350
SCORE_CEILING = 800

WEIGHT_TIMING = 250
WEIGHT_CONSISTENCY = 100
WEIGHT_TENURE_VOLUME = 60
WEIGHT_STANDING = 40
PENALTY_CAP = 100

# (days late relative to due date, points). Interpolated linearly between.
TIMING_ANCHORS = [
	(-5, 250),
	(0, 210),
	(5, 150),
	(15, 70),
	(30, 20),
	(45, 0),
]

TENURE_POINTS = 30
VOLUME_POINTS = 30
TENURE_MONTHS_REQUIRED = 12

STANDING_CLEAN = 40
STANDING_WARNING = 20
STANDING_HOLD = 0

PENALTY_RETURNED_PAYMENT = 25
PENALTY_BROKEN_PTP = 20
PENALTY_HARD_HOLD = 25
PENALTY_PLAN_DEFAULT = 50

MIN_PAID_INVOICES = 3
LOOKBACK_MONTHS = 12
VOLUME_WEEKS = 4

BAND_INSUFFICIENT = "Insufficient History"
BANDS = [
	(750, "Excellent"),
	(700, "Good"),
	(650, "Fair"),
	(600, "Watch"),
	(0, "COD Only"),
]


def band_for(score: int | None) -> str:
	if score is None:
		return BAND_INSUFFICIENT
	for floor, name in BANDS:
		if score >= floor:
			return name
	return "COD Only"


# ── the daily job ────────────────────────────────────────────────────────────


def update_customer_payment_scores():
	if not utils.require_policy_live("update_customer_payment_scores"):
		return

	customers = frappe.get_all(
		"Customer",
		filters={
			"disabled": 0,
			"custom_is_intercompany": 0,
			"custom_credit_policy_exempt": 0,
		},
		pluck="name",
	)

	for customer in customers:
		try:
			result = score_customer(customer)
			_store(customer, result)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Scoring failed for {customer}")

	frappe.db.commit()


def _store(customer: str, result: dict):
	"""Write the score back onto the Customer.

	§15 asks for a *null* score below the minimum invoice count, but Frappe
	creates Int columns as ``NOT NULL DEFAULT 0`` — a null cannot be stored
	there. So **`custom_score_band` is the authoritative signal**: a band of
	"Insufficient History" means there is no score, and a stored 0 must be
	rendered as "—", never as a real reading. Every report in this module keys
	off the band for exactly that reason.
	"""
	frappe.db.set_value(
		"Customer",
		customer,
		{
			"custom_payment_score": result["score"],
			"custom_score_band": result["band"],
			"custom_avg_days_to_pay": result["avg_days_to_pay"],
			"custom_on_time_percent": result["on_time_percent"],
			"custom_weekly_volume_g": result["weekly_volume_g"],
			"custom_weekly_volume_lbs": result["weekly_volume_lbs"],
			"custom_score_last_updated": now_datetime(),
		},
		update_modified=False,
	)


# ── scoring ──────────────────────────────────────────────────────────────────


@frappe.whitelist()
def score_customer(customer: str) -> dict:
	"""Score one customer. Returns the components too, so the model is auditable."""
	paid = _paid_invoices(customer)
	volume_g = _weekly_volume_grams(customer)

	result = {
		"customer": customer,
		"score": None,
		"band": BAND_INSUFFICIENT,
		"paid_invoice_count": len(paid),
		"avg_days_to_pay": 0.0,
		"on_time_percent": 0.0,
		"weekly_volume_g": volume_g,
		"weekly_volume_lbs": utils.grams_to_lbs(volume_g),
		"components": {},
	}

	if len(paid) < MIN_PAID_INVOICES:
		return result

	total_value = flt(sum(row["amount"] for row in paid)) or 1.0

	# Value-weighted: a large invoice paid late says more than a small one.
	avg_days = flt(sum(row["days_late"] * row["amount"] for row in paid) / total_value)
	on_time = flt(len([row for row in paid if row["days_late"] <= 0]) / len(paid) * 100)

	timing = _interpolate(avg_days)
	consistency = flt(on_time / 100 * WEIGHT_CONSISTENCY)
	tenure_volume = _tenure_and_volume(customer, volume_g)
	standing = _standing(customer)
	penalties = _penalties(customer)

	raw = SCORE_FLOOR + timing + consistency + tenure_volume + standing - penalties
	score = int(round(max(SCORE_FLOOR, min(SCORE_CEILING, raw))))

	result.update(
		{
			"score": score,
			"band": band_for(score),
			"avg_days_to_pay": avg_days,
			"on_time_percent": on_time,
			"components": {
				"base": SCORE_FLOOR,
				"timing": round(timing, 1),
				"consistency": round(consistency, 1),
				"tenure_volume": round(tenure_volume, 1),
				"standing": standing,
				"penalties": -round(penalties, 1),
				"raw": round(raw, 1),
			},
		}
	)
	return result


def _interpolate(days_late: float) -> float:
	"""Linear interpolation between the timing anchors, clamped at both ends."""
	first_days, first_points = TIMING_ANCHORS[0]
	if days_late <= first_days:
		return float(first_points)

	last_days, last_points = TIMING_ANCHORS[-1]
	if days_late >= last_days:
		return float(last_points)

	for (low_days, low_points), (high_days, high_points) in zip(
		TIMING_ANCHORS, TIMING_ANCHORS[1:]
	):
		if low_days <= days_late <= high_days:
			span = high_days - low_days
			if not span:
				return float(low_points)
			ratio = (days_late - low_days) / span
			return float(low_points + (high_points - low_points) * ratio)

	return 0.0


def _paid_invoices(customer: str) -> list[dict]:
	"""Fully-settled invoices in the window, with how late each one was paid.

	The settlement date comes from the ledger — the last receipt allocated to
	the invoice — because `Sales Invoice` records no payment date of its own.
	"""
	since = add_months(getdate(nowdate()), -LOOKBACK_MONTHS)

	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": customer,
			"docstatus": 1,
			"is_return": 0,
			"posting_date": (">=", since),
			"outstanding_amount": ("<=", 0),
			"custom_is_finance_charge": 0,
		},
		fields=["name", "due_date", "base_grand_total", "custom_order_type", "posting_date"],
	)
	invoices = [
		row
		for row in invoices
		if flt(row.base_grand_total) > 0
		and (row.custom_order_type or "") not in utils.SAMPLE_ORDER_TYPES
	]
	if not invoices:
		return []

	settled = _settlement_dates([row.name for row in invoices])

	paid = []
	for row in invoices:
		settled_on = settled.get(row.name)
		if not settled_on or not row.due_date:
			continue
		paid.append(
			{
				"invoice": row.name,
				"amount": flt(row.base_grand_total),
				"days_late": (getdate(settled_on) - getdate(row.due_date)).days,
			}
		)

	return paid


def _settlement_dates(invoice_names: list[str]) -> dict[str, str]:
	if not invoice_names:
		return {}

	from cannabis_management.credit_and_ar.metrics import receivable_accounts

	accounts = receivable_accounts()
	if not accounts:
		return {}

	result: dict[str, str] = {}
	chunk_size = 500
	for start in range(0, len(invoice_names), chunk_size):
		chunk = invoice_names[start : start + chunk_size]
		rows = frappe.db.sql(
			"""
			SELECT against_voucher AS invoice, MAX(posting_date) AS settled_on
			FROM `tabGL Entry`
			WHERE is_cancelled = 0
			  AND party_type = 'Customer'
			  AND against_voucher_type = 'Sales Invoice'
			  AND against_voucher IN %(invoices)s
			  AND account IN %(accounts)s
			  AND credit > 0
			GROUP BY against_voucher
			""",
			{"invoices": chunk, "accounts": accounts},
			as_dict=True,
		)
		for row in rows:
			result[row.invoice] = row.settled_on

	return result


def _tenure_and_volume(customer: str, weekly_volume_g: float) -> float:
	points = 0.0

	first = frappe.db.get_value(
		"Sales Invoice",
		{"customer": customer, "docstatus": 1},
		"posting_date",
		order_by="posting_date asc",
	)
	if first:
		months = (getdate(nowdate()) - getdate(first)).days / 30.44
		if months >= TENURE_MONTHS_REQUIRED:
			points += TENURE_POINTS
		else:
			points += TENURE_POINTS * (months / TENURE_MONTHS_REQUIRED)

	settings = utils.get_settings()
	qualifying_g = flt(settings.qualifying_weekly_volume_g)
	if qualifying_g and weekly_volume_g >= qualifying_g:
		points += VOLUME_POINTS
	elif qualifying_g:
		points += VOLUME_POINTS * min(1.0, weekly_volume_g / qualifying_g)

	return min(points, WEIGHT_TENURE_VOLUME)


def _standing(customer: str) -> int:
	hold_type = frappe.db.get_value("Customer", customer, "custom_hold_type")
	if hold_type in utils.BLOCKING_HOLDS:
		return STANDING_HOLD
	if hold_type == utils.HOLD_WARNING:
		return STANDING_WARNING

	from cannabis_management.credit_and_ar import credit_engine

	snapshot = credit_engine.get_past_due_snapshot(customer)
	if flt(snapshot["past_due_amount"]) > 0:
		return STANDING_WARNING
	return STANDING_CLEAN


def _penalties(customer: str) -> float:
	returned, broken = frappe.db.get_value(
		"Customer",
		customer,
		["custom_returned_payment_count", "custom_broken_ptp_count"],
	) or (0, 0)

	total = flt(returned) * PENALTY_RETURNED_PAYMENT + flt(broken) * PENALTY_BROKEN_PTP

	six_months_ago = add_months(getdate(nowdate()), -6)
	hard_holds = frappe.db.count(
		"AR Case",
		{
			"customer": customer,
			"case_type": ("in", ["Hard Hold", "Immediate Hold"]),
			"opened_on": (">=", six_months_ago),
		},
	)
	total += hard_holds * PENALTY_HARD_HOLD

	plan_defaults = frappe.db.count(
		"AR Case", {"customer": customer, "trigger_reason": "Plan Default"}
	)
	total += plan_defaults * PENALTY_PLAN_DEFAULT

	return min(total, PENALTY_CAP)


# ── volume ───────────────────────────────────────────────────────────────────


def _weekly_volume_grams(customer: str) -> float:
	"""Trailing four-week average, normalised to grams.

	Reported in pounds for TSBC Ranch and grams for Motley Terpz and Master
	Touch; both figures are stored so the report can pick.
	"""
	since = add_days(getdate(nowdate()), -VOLUME_WEEKS * 7)

	rows = frappe.db.sql(
		"""
		SELECT sii.item_code, sii.qty, sii.uom, sii.stock_qty, sii.stock_uom
		FROM `tabSales Invoice Item` sii
		JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
		  AND si.customer = %(customer)s
		  AND si.posting_date >= %(since)s
		  AND si.is_return = 0
		  AND IFNULL(si.custom_is_finance_charge, 0) = 0
		  AND IFNULL(si.custom_order_type, '') NOT IN %(sample_types)s
		""",
		{
			"customer": customer,
			"since": since,
			"sample_types": utils.SAMPLE_ORDER_TYPES,
		},
		as_dict=True,
	)

	total_g = 0.0
	for row in rows:
		grams = utils.to_grams(row.stock_qty, row.stock_uom, row.item_code)
		if not grams:
			grams = utils.to_grams(row.qty, row.uom, row.item_code)
		total_g += grams

	return flt(total_g / VOLUME_WEEKS)
