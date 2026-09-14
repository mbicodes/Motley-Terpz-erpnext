"""Payment plans (§8) and workout accounts (§9) — resolutions on the one case.

A **payment plan** splits a delinquent balance into a signed, ratified schedule.
A missed installment is logged and notified, but it does not raise a second
case — the one Active AR Case, already on Hard Hold, already stops new work.

A **workout account** is prepaid only, forever, and its balance only moves down.
A rising balance — or one that never shrinks — ends the workout and hands the
case back to Finance to decide again, rather than closing it and opening
another; there is still only ever one case per customer.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from cannabis_management.credit_and_ar import credit_engine, utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
	RESOLUTION_PAYMENT_PLAN,
	RESOLUTION_WORKOUT,
	STATUS_ACTIVE,
	STATUS_CLOSED,
	get_active_case,
	sync_customer_from_cases,
)

TREND_SHRINKING = "Shrinking"
TREND_FLAT = "Flat"
TREND_RISING = "Rising"

# Generate Plan — one due-date step per frequency. Custom is deliberately
# absent: it has no step, since its dates are typed by hand (see
# AR Case.installment_frequency).
FREQUENCY_STEPS = {
	"Weekly": lambda d: add_days(d, 7),
	"Monthly": lambda d: add_months(d, 1),
	"Bi-annually": lambda d: add_months(d, 6),
}

# A sane ceiling against a fat-fingered date range (e.g. Weekly over 20 years).
MAX_GENERATED_INSTALLMENTS = 260


# ── plan lifecycle ───────────────────────────────────────────────────────────


def on_ar_case_update(doc, method=None):
	"""Capture the invoices a plan covers, the moment the MD ratifies it."""
	if doc.resolution != RESOLUTION_PAYMENT_PLAN or not doc.md_ratified:
		return

	previous = doc.get_doc_before_save()
	if previous and previous.md_ratified:
		return

	_capture_plan_invoices(doc)


# ── Generate Plan ────────────────────────────────────────────────────────────
#
# Weekly / Monthly / Bi-annually only — a Custom-frequency plan is entered by
# hand (due dates, invoices and amounts all typed in), never through here. See
# the description on AR Case.installment_frequency.


def _installment_dates(start_date, end_date, frequency) -> list:
	"""Due dates from Plan Start Date to Plan End Date, one per frequency step."""
	step = FREQUENCY_STEPS.get(frequency)
	if not step:
		frappe.throw(
			_("{0} does not auto-generate a schedule — enter due dates by hand.").format(frequency)
		)

	start = getdate(start_date)
	end = getdate(end_date)
	if end < start:
		frappe.throw(_("Plan End Date must be on or after Plan Start Date."))

	dates = []
	current = start
	while current <= end:
		dates.append(current)
		if len(dates) > MAX_GENERATED_INSTALLMENTS:
			frappe.throw(
				_("That date range produces more than {0} installments at {1} frequency — narrow it down.").format(
					MAX_GENERATED_INSTALLMENTS, frequency
				)
			)
		current = step(current)

	return dates or [end]


@frappe.whitelist()
def generate_schedule(
	case_name: str,
	resolution: str | None = None,
	plan_start_date: str | None = None,
	plan_end_date: str | None = None,
	installment_frequency: str | None = None,
):
	"""§8 Generate Plan — compute the installment schedule from live invoices.

	Pure computation, nothing is saved here: the client populates the Schedule
	grid from the return value so Finance can review (and attach the signed
	plan document) before hitting Save, which runs the usual validation.

	``resolution`` / ``plan_start_date`` / ``plan_end_date`` /
	``installment_frequency`` are taken from the caller (the open form) rather
	than re-read from the database, since Finance may have just picked
	"Payment Plan" and typed in the dates without saving yet — checking the
	stale, already-saved case would refuse to generate a schedule for what is
	plainly on screen. Each falls back to the saved case when omitted.

	Due dates are Plan Start Date → Plan End Date stepped by Installment
	Frequency. The customer's open, past-due invoices (oldest first — FIFO)
	are drawn down evenly across those dates: an installment that outruns its
	invoice keeps drawing from the next one on the list, so one installment
	can straddle several invoices and one invoice can straddle several
	installments.
	"""
	case = frappe.get_doc("AR Case", case_name)
	case.check_permission("write")

	resolution = resolution or case.resolution
	if resolution != RESOLUTION_PAYMENT_PLAN:
		frappe.throw(_("{0} is not on a Payment Plan.").format(case_name))

	# No Credit Finance / System Manager gate here — anyone with write access
	# to the case (checked above) can generate the schedule. Saving it still
	# runs the full ARCase validation (signed document, MD ratification, etc).

	plan_start_date = plan_start_date or case.plan_start_date
	plan_end_date = plan_end_date or case.plan_end_date
	installment_frequency = installment_frequency or case.installment_frequency

	if not plan_start_date or not plan_end_date:
		frappe.throw(_("Set Plan Start Date and Plan End Date first."))

	invoices = _open_plan_invoices(case.customer)
	if not invoices:
		frappe.throw(_("{0} has no open, past-due Sales Invoices to schedule.").format(case.customer))

	dates = _installment_dates(plan_start_date, plan_end_date, installment_frequency)
	total = flt(sum(flt(row.outstanding_amount) for row in invoices))

	# Even split across installments, the last one absorbing the rounding
	# remainder so the schedule always foots exactly to the total — see
	# ARCase._validate_payment_plan, which enforces that match on Save.
	count = len(dates)
	share = flt(round(total / count, 2))
	amounts = [share] * (count - 1) + [flt(total - share * (count - 1), 2)]

	remaining = {row.name: flt(row.outstanding_amount) for row in invoices}
	order = [row.name for row in invoices]
	cursor = 0

	installments = []
	for due_date, amount in zip(dates, amounts):
		row_invoices = []
		needed = amount
		while needed > 0.005 and cursor < len(order):
			invoice = order[cursor]
			available = remaining[invoice]
			if available <= 0.005:
				cursor += 1
				continue
			take = flt(min(available, needed), 2)
			row_invoices.append({"sales_invoice": invoice, "allocated_amount": take})
			remaining[invoice] -= take
			needed -= take
			if remaining[invoice] <= 0.005:
				cursor += 1
		installments.append(
			{"due_date": due_date, "amount": amount, "invoices": row_invoices}
		)

	return {
		"total": total,
		"invoice_count": len(invoices),
		"installments": installments,
	}


def _open_plan_invoices(customer: str) -> list:
	"""This customer's open, past-due invoices, oldest due date first.

	The one FIFO order both plan ratification (below) and Generate Plan
	(``generate_schedule``) draw down against. Only **past-due** invoices
	count: the plan exists to work off a delinquent balance. An invoice that
	is merely open, and still inside its terms, is current trading and stays
	on the new book.
	"""
	return frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": customer,
			"docstatus": 1,
			"outstanding_amount": (">", 0),
			"custom_is_finance_charge": 0,
			"due_date": ("<", getdate(nowdate())),
		},
		fields=["name", "outstanding_amount"],
		order_by="due_date asc, posting_date asc, name asc",
	)


def _capture_plan_invoices(case):
	"""Ratification freezes which invoices belong to the plan.

	Without this the two ledgers have no boundary — "plan money" would be a
	label rather than a rule.
	"""
	invoices = _open_plan_invoices(case.customer)
	if not invoices:
		case.add_comment(
			"Info",
			_("Plan ratified, but no past-due invoices were found to capture onto the Plan ledger."),
		)
		return

	for row in invoices:
		frappe.db.set_value(
			"Sales Invoice",
			row.name,
			{"custom_ar_case": case.name, "custom_ledger": utils.LEDGER_PLAN},
			update_modified=False,
		)

	captured = flt(sum(flt(row.outstanding_amount) for row in invoices))
	exposure = credit_engine.get_current_exposure(case.customer)
	frappe.db.set_value(
		"AR Case",
		case.name,
		{"total_exposure_at_approval": exposure},
		update_modified=False,
	)

	message = _(
		"Plan ratified — {0} past-due invoice(s) totalling {1} captured onto the Plan "
		"ledger. Total group exposure {2}."
	).format(len(invoices), utils.fmt_currency(captured), utils.fmt_currency(exposure))

	case.add_comment("Info", message)


def get_active_plan(customer: str) -> dict | None:
	return get_active_case(customer, resolution=RESOLUTION_PAYMENT_PLAN)


def plan_problems(customer: str) -> list[str]:
	"""§8 — why a plan customer may not take new terms work, if anything.

	All four must hold: the plan is ratified, nothing has been missed, a
	*separate* credit line exists, and that line is approved.
	"""
	if utils.is_policy_exempt(customer):
		return []

	plan = get_active_plan(customer)
	if not plan:
		return []

	problems = []

	if not plan.md_ratified:
		problems.append(
			_("Payment plan {0} has not been ratified by the Managing Director.").format(plan.name)
		)

	if int(plan.missed_installments or 0) > 0:
		problems.append(
			_("Payment plan {0} has {1} missed installment(s).").format(
				plan.name, plan.missed_installments
			)
		)

	if not plan.new_line_credit_application:
		problems.append(
			_(
				"No separate credit line has been approved for new business. A plan "
				"customer needs a fresh line sized against plan balance plus new line."
			)
		)
	else:
		state = frappe.db.get_value(
			"Credit Application", plan.new_line_credit_application, "workflow_state"
		)
		if state != "Approved":
			problems.append(
				_("Credit Application {0} is {1}, not Approved.").format(
					plan.new_line_credit_application, state
				)
			)

	return problems


def assert_plan_allows_terms(customer: str):
	"""Throwing wrapper around :func:`plan_problems`."""
	problems = plan_problems(customer)
	if problems:
		problems.append(
			_("Until then this customer is COD only, and plan payments continue as scheduled.")
		)
		utils.throw_consolidated(problems, "Payment Plan In Force")


# ── plan default ─────────────────────────────────────────────────────────────


def check_plan_installments():
	"""Daily — a missed installment is logged and notified.

	It does not raise a further hold: the case it belongs to is already on
	Hard Hold and already stops new work.
	"""
	if not utils.require_policy_live("check_plan_installments"):
		return

	today = getdate(nowdate())

	cases = frappe.get_all(
		"AR Case",
		filters={"resolution": RESOLUTION_PAYMENT_PLAN, "status": STATUS_ACTIVE},
		pluck="name",
	)

	for name in cases:
		if utils.is_policy_exempt(frappe.db.get_value("AR Case", name, "customer")):
			continue
		try:
			_check_one_plan(name, today)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Plan installment check failed for {name}")

	frappe.db.commit()


def _check_one_plan(case_name, today):
	case = frappe.get_doc("AR Case", case_name)
	newly_missed = []

	for row in case.schedule:
		if row.status != "Pending":
			continue
		if not row.due_date or getdate(row.due_date) >= today:
			continue
		if flt(row.paid_amount) + 0.005 >= flt(row.amount):
			continue
		row.status = "Missed"
		newly_missed.append(row)

	if not newly_missed:
		return

	case.missed_installments = len([row for row in case.schedule if row.status == "Missed"])
	case.flags.ignore_role_guards = True
	case.save(ignore_permissions=True)

	detail = _("{0} installment(s) missed; {1} outstanding on the plan.").format(
		len(newly_missed),
		utils.fmt_currency(sum(flt(r.amount) - flt(r.paid_amount) for r in newly_missed)),
	)
	case.add_comment("Info", _("Plan default — {0}").format(detail))

	_notify_missed_installment(case, newly_missed)


def _notify_missed_installment(case, rows):
	recipients = utils.dedupe_recipients(
		utils.finance_recipients(),
		utils.routed_user("managing_director"),
		utils.routed_user("collections_officer"),
	)
	if not recipients:
		return

	items = "".join(
		"<li>{0} — {1}</li>".format(
			frappe.format(row.due_date, {"fieldtype": "Date"}),
			utils.fmt_currency(flt(row.amount) - flt(row.paid_amount)),
		)
		for row in rows
	)

	_sendmail(
		recipients,
		_("Plan installment missed — {0}").format(case.customer),
		_(
			"<p>Payment plan <b>{0}</b> for <b>{1}</b> has missed an installment. "
			"All new work is on <b>hold</b> until it is cured.</p><ul>{2}</ul>"
			"<p>Missed to date: <b>{3}</b></p><p>{4}</p>"
		).format(
			case.name,
			frappe.utils.escape_html(case.customer),
			items,
			case.missed_installments,
			utils.doc_link("AR Case", case.name),
		),
		case,
	)


# ── workout ──────────────────────────────────────────────────────────────────


def get_active_workout(customer: str) -> dict | None:
	return get_active_case(customer, resolution=RESOLUTION_WORKOUT)


def required_paydown(workout: dict, order_total: float) -> float:
	if not workout:
		return 0.0
	if workout.get("paydown_mode") == "Fixed Amount per Order":
		return flt(workout.get("paydown_amount"))
	return flt(order_total) * flt(workout.get("paydown_percent")) / 100.0


def get_previous_workout_balance(workout: dict | None) -> float:
	"""§9 Previous Balance.

	The workout's Starting Balance for the first order submitted since it
	began; otherwise the "Workout Balance at Order" snapshot saved on the
	customer's last *submitted* order against this same case.
	"""
	if not workout:
		return 0.0

	last_order = frappe.get_all(
		"Sales Order",
		filters={"custom_ar_case": workout["name"], "docstatus": 1},
		fields=["custom_workout_balance_at_order"],
		order_by="creation desc",
		limit=1,
	)
	if not last_order:
		return flt(workout.get("starting_balance"))
	return flt(last_order[0].custom_workout_balance_at_order)


def refresh_workout_balance(customer: str):
	"""Recompute an active workout's Current Balance right away.

	§9 step 8 — a payment against an old/overdue invoice should move the
	balance immediately, not wait for the nightly ``review_workouts`` sweep.
	Current Balance is simply live group exposure (exactly what the nightly
	job also uses), so any receipt or refund that changes exposure is enough
	reason to recompute here.

	§9 step 9 — the moment the balance reaches zero this closes the case and
	clears the customer's credit status outright. The nightly sweep never does
	this on its own: it only ever *ends* a workout that is rising or stuck,
	never closes one that has been paid off.
	"""
	if not customer or utils.is_policy_exempt(customer):
		return

	workout = get_active_workout(customer)
	if not workout:
		return

	case = frappe.get_doc("AR Case", workout["name"])
	current = credit_engine.get_current_exposure(customer)
	starting = flt(case.starting_balance)
	previous = flt(case.current_balance)

	case.current_balance = current
	case.recovered_to_date = max(0.0, starting - current)

	if previous:
		if current < previous - 0.01:
			case.balance_trend = TREND_SHRINKING
		elif current > previous + 0.01:
			case.balance_trend = TREND_RISING
		else:
			case.balance_trend = TREND_FLAT

	case.flags.ignore_role_guards = True

	if current <= 0.005:
		case.current_balance = 0.0
		case.status = STATUS_CLOSED
		case.save(ignore_permissions=True)

		sync_customer_from_cases(case.customer)
		# §9 step 9 — reaching zero clears the slate outright, not the usual
		# Terms Approved / COD fallback sync_customer_from_cases would leave.
		frappe.db.set_value(
			"Customer", case.customer, "custom_credit_status", "", update_modified=False
		)
		frappe.clear_document_cache("Customer", case.customer)

		case.add_comment(
			"Info", _("Workout balance reached zero — case closed, credit status cleared.")
		)
		_notify_workout(case, _("Workout complete — balance paid to zero"))
		return

	case.save(ignore_permissions=True)


def get_cleared_paydowns(sales_order: str) -> float:
	"""Cleared Workout Paydown receipts booked against this order."""
	from cannabis_management.credit_and_ar.sales_order_hooks import _is_cleared

	rows = frappe.get_all(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"payment_type": "Receive",
			"custom_against_sales_order": sales_order,
			"custom_ledger": utils.LEDGER_WORKOUT_PAYDOWN,
		},
		fields=["paid_amount", "clearance_date", "mode_of_payment"],
	)
	return flt(sum(flt(row.paid_amount) for row in rows if _is_cleared(row)))


def review_workouts():
	"""Daily — the balance only moves down. A rising, or unmoving, balance ends
	the workout and hands the case back to Finance."""
	if not utils.require_policy_live("review_workouts"):
		return

	settings = utils.get_settings()
	no_shrink_days = int(settings.workout_no_shrink_days or 60)
	review_days = int(settings.workout_review_frequency_days or 30)
	today = getdate(nowdate())

	cases = frappe.get_all(
		"AR Case",
		filters={"resolution": RESOLUTION_WORKOUT, "status": STATUS_ACTIVE},
		pluck="name",
	)

	for name in cases:
		if utils.is_policy_exempt(frappe.db.get_value("AR Case", name, "customer")):
			continue
		try:
			_review_one_workout(name, today, no_shrink_days, review_days)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Workout review failed for {name}")

	frappe.db.commit()


def _review_one_workout(case_name, today, no_shrink_days, review_days):
	case = frappe.get_doc("AR Case", case_name)

	current = credit_engine.get_current_exposure(case.customer)
	starting = flt(case.starting_balance)
	previous = flt(case.current_balance)

	case.current_balance = current
	case.recovered_to_date = max(0.0, starting - current)

	if previous:
		if current < previous - 0.01:
			case.balance_trend = TREND_SHRINKING
		elif current > previous + 0.01:
			case.balance_trend = TREND_RISING
		else:
			case.balance_trend = TREND_FLAT

	case.flags.ignore_role_guards = True

	# The balance only moves down. Above where it started ends the workout —
	# back to Finance to decide the next step. The case itself stays Active
	# and on hold throughout; there is no second case to raise.
	if starting and current > starting + 0.01:
		case.resolution = ""
		case.save(ignore_permissions=True)
		case.add_comment(
			"Info",
			_(
				"Workout ended — balance rose from {0} to {1}. Back with Finance to decide "
				"the next step."
			).format(utils.fmt_currency(starting), utils.fmt_currency(current)),
		)
		sync_customer_from_cases(case.customer)
		_notify_workout(case, _("Workout ended — the balance is rising"))
		return

	# Not shrinking within the no-shrink window → final demand and collections.
	opened = getdate(case.opened_on or today)
	if (
		starting
		and (today - opened).days >= no_shrink_days
		and current >= starting - 0.01
	):
		case.resolution = ""
		case.save(ignore_permissions=True)
		case.add_comment(
			"Info",
			_(
				"Workout flagged for final demand — no reduction in {0} days. Back with "
				"Finance to decide the next step."
			).format(no_shrink_days),
		)
		sync_customer_from_cases(case.customer)
		_notify_workout(case, _("Workout has not shrunk in {0} days").format(no_shrink_days))
		return

	due_for_review = not case.next_review_date or getdate(case.next_review_date) <= today
	if due_for_review:
		case.last_review_date = today
		case.next_review_date = add_days(today, review_days)
		case.save(ignore_permissions=True)
		_notify_workout(case, _("Workout review"))
	else:
		case.save(ignore_permissions=True)


def _notify_workout(case, headline):
	recipients = utils.dedupe_recipients(
		utils.routed_user("managing_director"), utils.finance_recipients()
	)
	if not recipients:
		return

	_sendmail(
		recipients,
		_("{0} — {1}").format(headline, case.customer),
		_(
			"""
			<p>{headline} for <b>{customer}</b>.</p>
			<table style="font-size:14px;margin:8px 0;">
				<tr><td style="padding:3px 14px 3px 0;color:#666;">Starting Balance</td><td><b>{starting}</b></td></tr>
				<tr><td style="padding:3px 14px 3px 0;color:#666;">Current Balance</td><td><b>{current}</b></td></tr>
				<tr><td style="padding:3px 14px 3px 0;color:#666;">Recovered</td><td>{recovered}</td></tr>
				<tr><td style="padding:3px 14px 3px 0;color:#666;">Trend</td><td>{trend}</td></tr>
				<tr><td style="padding:3px 14px 3px 0;color:#666;">Resolution</td><td>{resolution}</td></tr>
			</table>
			<p>{link}</p>
			"""
		).format(
			headline=headline,
			customer=frappe.utils.escape_html(case.customer),
			starting=utils.fmt_currency(case.starting_balance),
			current=utils.fmt_currency(case.current_balance),
			recovered=utils.fmt_currency(case.recovered_to_date),
			trend=case.balance_trend or _("not yet established"),
			resolution=case.resolution or _("back with Finance"),
			link=utils.doc_link("AR Case", case.name),
		),
		case,
	)


def _sendmail(recipients, subject, message, doc=None):
	try:
		kwargs = {"recipients": recipients, "subject": subject, "message": message}
		if doc is not None:
			kwargs["reference_doctype"] = doc.doctype
			kwargs["reference_name"] = doc.name
		frappe.sendmail(**kwargs)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Plan/workout notification failed")
