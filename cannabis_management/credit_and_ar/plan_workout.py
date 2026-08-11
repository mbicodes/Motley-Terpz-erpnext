"""Payment plans (§8) and workout accounts (§9).

A **payment plan** splits a delinquent balance into a signed, ratified schedule.
One missed payment is an immediate hard hold on all new work until cured — the
plan engine and the ordinary past-due engine run independently, and neither
suppresses the other.

A **workout account** is prepaid only, forever, and its balance only moves down.
A rising balance ends the workout.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, now_datetime, nowdate

from cannabis_management.credit_and_ar import credit_engine, hold_engine, utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
	INACTIVE_STATUSES,
	STATUS_DEFAULTED,
	TYPE_HARD_HOLD,
	TYPE_PAYMENT_PLAN,
	TYPE_WORKOUT,
	sync_customer_from_cases,
)

TREND_SHRINKING = "Shrinking"
TREND_FLAT = "Flat"
TREND_RISING = "Rising"


# ── plan lifecycle ───────────────────────────────────────────────────────────


def on_ar_case_update(doc, method=None):
	"""Capture the invoices a plan covers, the moment the MD ratifies it."""
	if doc.case_type != TYPE_PAYMENT_PLAN or not doc.md_ratified:
		return

	previous = doc.get_doc_before_save()
	if previous and previous.md_ratified:
		return

	_capture_plan_invoices(doc)


def _capture_plan_invoices(case):
	"""Ratification freezes which invoices belong to the plan.

	Without this the two ledgers have no boundary — "plan money" would be a
	label rather than a rule.

	Only **past-due** invoices are captured: the plan exists to work off a
	delinquent balance. An invoice that is merely open, and still inside its
	terms, is current trading and stays on the new book.
	"""
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": case.customer,
			"docstatus": 1,
			"outstanding_amount": (">", 0),
			"custom_is_finance_charge": 0,
			"due_date": ("<", getdate(nowdate())),
		},
		fields=["name", "outstanding_amount"],
	)
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

	if abs(captured - flt(case.plan_principal)) > 0.01:
		message += _(
			"<br><b>Note:</b> the captured balance differs from the plan principal of {0}. "
			"Confirm the schedule covers the intended debt."
		).format(utils.fmt_currency(case.plan_principal))

	case.add_comment("Info", message)


def get_active_plan(customer: str) -> dict | None:
	rows = frappe.get_all(
		"AR Case",
		filters={
			"customer": customer,
			"case_type": TYPE_PAYMENT_PLAN,
			"status": ("not in", INACTIVE_STATUSES),
		},
		fields=["name", "md_ratified", "missed_installments", "new_line_credit_application"],
		limit=1,
	)
	return rows[0] if rows else None


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
	"""Daily — a missed installment is an immediate hold on all new work."""
	if not utils.require_policy_live("check_plan_installments"):
		return

	today = getdate(nowdate())

	cases = frappe.get_all(
		"AR Case",
		filters={"case_type": TYPE_PAYMENT_PLAN, "status": ("not in", INACTIVE_STATUSES)},
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

	hold_engine.raise_immediate_hold(
		customer=case.customer,
		trigger_reason="Plan Default",
		trigger_details=detail,
		company=case.company,
	)

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
			"All new work is on <b>immediate hold</b> until it is cured.</p><ul>{2}</ul>"
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
	rows = frappe.get_all(
		"AR Case",
		filters={
			"customer": customer,
			"case_type": TYPE_WORKOUT,
			"status": ("not in", INACTIVE_STATUSES),
		},
		fields=[
			"name",
			"paydown_mode",
			"paydown_percent",
			"paydown_amount",
			"starting_balance",
			"current_balance",
		],
		limit=1,
	)
	return rows[0] if rows else None


def required_paydown(workout: dict, order_total: float) -> float:
	if not workout:
		return 0.0
	if workout.get("paydown_mode") == "Fixed Amount per Order":
		return flt(workout.get("paydown_amount"))
	return flt(order_total) * flt(workout.get("paydown_percent")) / 100.0


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
	"""Daily — the balance only moves down. A rising balance ends the workout."""
	if not utils.require_policy_live("review_workouts"):
		return

	settings = utils.get_settings()
	no_shrink_days = int(settings.workout_no_shrink_days or 60)
	review_days = int(settings.workout_review_frequency_days or 30)
	today = getdate(nowdate())

	cases = frappe.get_all(
		"AR Case",
		filters={"case_type": TYPE_WORKOUT, "status": ("not in", INACTIVE_STATUSES)},
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

	# The balance only moves down. Above where it started ends the workout.
	if starting and current > starting + 0.01:
		case.status = STATUS_DEFAULTED
		case.save(ignore_permissions=True)
		case.add_comment(
			"Info",
			_("Workout ended — balance rose from {0} to {1}.").format(
				utils.fmt_currency(starting), utils.fmt_currency(current)
			),
		)
		hold_engine.create_case(
			customer=case.customer,
			case_type=TYPE_HARD_HOLD,
			trigger_reason="Manual",
			trigger_details=_("Workout {0} defaulted — balance rose above its starting point.").format(
				case.name
			),
			company=case.company,
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
		case.status = STATUS_DEFAULTED
		case.save(ignore_permissions=True)
		case.add_comment(
			"Info",
			_("Workout flagged for final demand — no reduction in {0} days.").format(no_shrink_days),
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
				<tr><td style="padding:3px 14px 3px 0;color:#666;">Status</td><td>{status}</td></tr>
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
			status=case.status,
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
