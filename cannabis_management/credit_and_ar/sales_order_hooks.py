"""The Sales Order gate — COD / Terms / Sample routing.

Order type is not a new field: it is derived from the two that already existed
on Sales Order (see ``utils.resolve_order_type``).

  Cash    → policy does not apply; ERPNext defaults are left alone, no hold block
  Sample  → forced to zero value, no credit checks, no hold block
  Terms   → the full gate, and blocked from submit *and print* until approved

Per-order approval applies to every Terms order, every time — an approved credit
line grants the *ability* to order on terms, not a standing approval.

Cash orders were previously forced onto the "COD" payment terms template with the
payment schedule wiped. They no longer are: a cash order carries no credit exposure,
so the module leaves the document to ERPNext. Everything downstream that used to key
off ``payment_terms_template == "COD"`` (finance_charge, metrics, payment_entry_hooks)
already treats an empty template identically, so nothing else had to change.

The single exception is the workout paydown, which still applies to cash — see
``utils.is_cash_order`` and the README decision log.
"""

import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_and_ar import credit_engine, utils


# ── entry points ─────────────────────────────────────────────────────────────


def validate(doc, method=None):
	if not doc.customer:
		return

	if utils.is_policy_exempt(doc.customer):
		_clear_credit_fields(doc)
		return

	_default_payment_mode(doc)

	order_type = utils.resolve_order_type(doc)

	if order_type == utils.ORDER_TYPE_COD:
		# Short-circuit before the credit engine runs at all. A cash order needs no
		# line summary, so there is no reason to compute one.
		_apply_cash(doc)
		_apply_workout_paydown(doc, order_type)
		return

	summary = credit_engine.get_line_summary(doc.customer, exclude_sales_order=doc.name)
	doc.custom_customer_available_line = summary["available_line"]

	if order_type == utils.ORDER_TYPE_SAMPLE:
		_apply_sample(doc)
	else:
		_validate_terms(doc, summary)

	_apply_workout_paydown(doc, order_type)


def before_submit(doc, method=None):
	if utils.is_policy_exempt(doc.customer):
		return

	order_type = utils.resolve_order_type(doc)

	if order_type == utils.ORDER_TYPE_SAMPLE:
		_assert_zero_value(doc)
		return

	if order_type == utils.ORDER_TYPE_COD:
		_check_workout_paydown(doc)
		return

	# Everything that stops a Terms order lives here, not at save. A draft can
	# always be written down; it is submitting that commits the exposure.
	_assert_terms_allowed(doc)
	_check_workout_paydown(doc)

	# The credit line is checked *before* the approval status, deliberately. An
	# over-limit order never auto-approves, so leaving this last meant the only
	# error Sales ever saw was "awaiting approval" — true, but not the reason the
	# order was stuck, and it sent them to the MD instead of to the number.
	_check_deposit(doc)

	if doc.custom_approval_status != utils.APPROVAL_APPROVED:
		frappe.throw(
			_(
				"This Terms order is awaiting Managing Director approval. It cannot be "
				"submitted or printed until approved."
			),
			title=_("Approval Required"),
		)


def on_update(doc, method=None):
	"""Keep the print block honest even if the status is changed elsewhere."""
	if doc.docstatus != 0 or utils.is_policy_exempt(doc.customer):
		return

	should_block = int(
		utils.resolve_order_type(doc) == utils.ORDER_TYPE_TERMS
		and doc.custom_approval_status == utils.APPROVAL_PENDING
	)
	if int(doc.custom_print_blocked or 0) != should_block:
		doc.db_set("custom_print_blocked", should_block, update_modified=False)


# ── Cash ─────────────────────────────────────────────────────────────────────


def _clear_credit_fields(doc):
	"""An exempt account carries no credit state at all.

	The order behaves exactly as it did before this module existed — including
	leaving `payment_terms_template` alone, so the exemption is a real carve-out
	rather than a silently-still-COD order.
	"""
	doc.custom_approval_status = utils.APPROVAL_NOT_REQUIRED
	doc.custom_print_blocked = 0
	doc.custom_required_deposit = 0
	doc.custom_workout_paydown_required = 0
	doc.custom_credit_application = None
	doc.custom_ar_case = None
	doc.custom_customer_available_line = 0


def _default_payment_mode(doc):
	if not doc.custom_mode_of_payment:
		doc.custom_mode_of_payment = utils.MODE_COD


def _apply_cash(doc):
	"""A cash order carries no credit state — and no credit behaviour.

	This deliberately does **not** touch ``payment_terms_template`` or
	``payment_schedule``. The module used to force both (template = "COD", schedule
	emptied); it no longer does, because the money arrives with the product and
	there is nothing for the policy to protect. Whatever ERPNext or the user puts
	on the document stands.

	Only the module's own fields are reset, so an order flipped from Terms to Cash
	does not carry stale approval or deposit state.
	"""
	doc.custom_approval_status = utils.APPROVAL_NOT_REQUIRED
	doc.custom_print_blocked = 0
	doc.custom_required_deposit = 0
	doc.custom_credit_application = None
	doc.custom_customer_available_line = 0


# ── Sample ───────────────────────────────────────────────────────────────────


def _apply_sample(doc):
	"""Zero value, enforced — not merely expected.

	Stock still leaves inventory; a sample is a pricing decision, not an
	inventory one. Holds do not block samples.
	"""
	changed = False
	for item in doc.items:
		if flt(item.rate) or flt(item.discount_percentage) or flt(item.discount_amount):
			item.rate = 0
			item.price_list_rate = 0
			item.discount_percentage = 0
			item.discount_amount = 0
			item.margin_rate_or_amount = 0
			changed = True

	if changed:
		doc.calculate_taxes_and_totals()

	doc.payment_terms_template = None
	doc.payment_schedule = []
	doc.custom_approval_status = utils.APPROVAL_NOT_REQUIRED
	doc.custom_print_blocked = 0
	doc.custom_required_deposit = 0
	doc.custom_credit_application = None

	_assert_zero_value(doc)


def _assert_zero_value(doc):
	if flt(doc.grand_total):
		frappe.throw(
			_(
				"A Sample order must be zero value, but this one totals {0}.<br><br>"
				"Remove the charge, or change the order type if this is a real sale."
			).format(utils.fmt_currency(doc.grand_total, doc.currency)),
			title=_("Sample Order"),
		)


# ── Terms ────────────────────────────────────────────────────────────────────


def _validate_terms(doc, summary):
	"""Save time — compute, stamp and **warn**. Nothing here blocks a draft.

	Sales need to be able to write an order down while the credit file is still
	being put together; the policy only has to bite before the order is
	committed. Everything that refuses lives in ``_assert_terms_allowed``, which
	runs at submit.
	"""
	application = credit_engine.get_active_credit_application(doc.customer)
	doc.custom_credit_application = application.get("name") if application else None

	_compute_required_deposit(doc, summary)

	if doc.custom_approval_status not in (
		utils.APPROVAL_PENDING,
		utils.APPROVAL_APPROVED,
		utils.APPROVAL_REJECTED,
	):
		doc.custom_approval_status = utils.APPROVAL_PENDING

	if doc.custom_approval_status == utils.APPROVAL_PENDING and _qualifies_for_auto_approval(
		doc, summary
	):
		_auto_approve_terms(doc)

	doc.custom_print_blocked = int(doc.custom_approval_status == utils.APPROVAL_PENDING)

	_warn_terms_problems(doc)


def _qualifies_for_auto_approval(doc, summary) -> bool:
	"""A Managing Director already signed off on this account's credit line —
	an order that stays inside it does not need a second, per-order sign-off.

	Anything that would still need a human — a hold, a freeze, an expired or
	revoked line, a wrong term, an account on a plan or workout, or an order
	that pushes exposure past the approved line — falls straight through to
	the usual Pending Approval queue, unchanged.
	"""
	if frappe.db.get_value("Customer", doc.customer, "custom_credit_status") != (
		utils.STATUS_TERMS_APPROVED
	):
		return False

	if _terms_problems(doc):
		return False

	credit_portion = utils.template_credit_portion(doc.payment_terms_template) / 100.0
	order_credit_exposure = flt(doc.grand_total) * credit_portion
	over_limit = order_credit_exposure - flt(summary["available_line"])
	return over_limit <= 0.005


def _auto_approve_terms(doc):
	"""Same end state as ``api.approve_terms`` — approved, print unblocked —
	minus the human. ``custom_terms_approved_by`` still needs a real User for
	the Link field; Administrator marks it as policy-driven rather than
	claiming a person signed off who did not."""
	doc.custom_approval_status = utils.APPROVAL_APPROVED
	doc.custom_terms_approved_by = "Administrator"
	doc.custom_terms_approved_on = frappe.utils.now_datetime()
	doc.custom_terms_rejection_reason = None

	# A brand-new document has no row in the database yet, so a Comment
	# pointing at it as its reference would fail to link. Only log the
	# comment for a document that already exists — new inserts still carry
	# the same audit trail via the approved_by/approved_on stamp above.
	if not doc.get("__islocal"):
		doc.add_comment(
			"Comment",
			_(
				"Terms auto-approved — order stays within {0}'s approved credit line, "
				"no Managing Director sign-off required."
			).format(doc.customer),
		)


def _warn_terms_problems(doc):
	"""Tell Sales now what will stop the order at submit — without stopping the save."""
	problems = _terms_problems(doc)
	if not problems:
		return

	items = "".join(f"<li>{problem}</li>" for problem in problems)
	frappe.msgprint(
		_(
			"This order can be saved as a draft, but it <b>cannot be submitted</b> until "
			"the following is resolved:"
		)
		+ f"<ul style='margin:8px 0 0 16px;padding:0'>{items}</ul>",
		title=_("Terms Order — Not Ready to Submit"),
		indicator="orange",
	)


def _assert_terms_allowed(doc):
	"""Submit time — the same checks, now refusing.

	Re-run live rather than trusted from the save: holds, freezes and credit
	lines all move between drafting an order and committing it.
	"""
	problems = _terms_problems(doc)
	utils.throw_consolidated(problems, "Terms Order Cannot Be Submitted")


def _terms_problems(doc) -> list[str]:
	"""Every reason a Terms order may not be committed, gathered in one pass.

	Each check *returns* its problem rather than throwing, so the same list can
	drive a non-blocking warning at save and a hard refusal at submit without
	the two ever drifting apart.
	"""
	settings = utils.get_settings()

	checks = (
		_problem_workout(doc),
		_problem_terms_template(doc),
		_problem_line(doc),
		_problem_one_term_per_account(doc),
		_problem_terms_ceiling(doc, settings),
		_problem_hold(doc),
		_problem_freeze(),
	)

	problems = [problem for problem in checks if problem]
	problems += _problem_payment_plan(doc)
	return problems


def _problem_terms_template(doc) -> str | None:
	if not doc.payment_terms_template:
		return _("A Payment Terms Template is required on a Terms order.")
	return None


def _problem_line(doc) -> str | None:
	"""No approved credit line, or one that has expired or been revoked."""
	blocker = credit_engine.describe_line_blocker(doc.customer)
	return frappe.utils.strip_html(blocker).strip() if blocker else None


def _problem_one_term_per_account(doc) -> str | None:
	"""§5 — one term per account. Sales cannot pick a different template."""
	approved = frappe.db.get_value("Customer", doc.customer, "custom_credit_terms_template")
	if approved and doc.payment_terms_template and doc.payment_terms_template != approved:
		return _(
			"{0} is approved for {1}, not {2}. One term per account — changing the term "
			"needs a new Credit Application."
		).format(doc.customer, approved, doc.payment_terms_template)
	return None


def _problem_terms_ceiling(doc, settings) -> str | None:
	ceiling = int(settings.max_terms_days or 0)
	if not ceiling or not doc.payment_terms_template:
		return None

	days = utils.template_credit_days(doc.payment_terms_template)
	if days > ceiling:
		return _("{0} runs {1} days. Nothing beyond Net {2}, ever.").format(
			doc.payment_terms_template, days, ceiling
		)
	return None


def _problem_workout(doc) -> str | None:
	"""§9 — workout accounts are prepaid only, no exceptions."""
	from cannabis_management.credit_and_ar import plan_workout

	status = frappe.db.get_value("Customer", doc.customer, "custom_credit_status")
	if status != utils.STATUS_WORKOUT and not plan_workout.get_active_workout(doc.customer):
		return None

	return _(
		"{0} is a workout account. Workout accounts are COD or prepaid only — zero new "
		"unsecured exposure, no exceptions."
	).format(doc.customer)


def _problem_payment_plan(doc) -> list[str]:
	"""§8 — a plan customer only gets terms on a healthy plan plus a fresh line."""
	from cannabis_management.credit_and_ar import plan_workout

	return plan_workout.plan_problems(doc.customer)


def _problem_hold(doc) -> str | None:
	"""A hard or immediate hold refuses. A warning only warns."""
	hold_type = frappe.db.get_value("Customer", doc.customer, "custom_hold_type")

	if hold_type in utils.BLOCKING_HOLDS:
		return _("{0} is on {1}. No new terms work until Finance releases the hold.").format(
			doc.customer, hold_type
		)

	if hold_type == utils.HOLD_WARNING:
		frappe.msgprint(
			_("{0} has a past-due balance and is on <b>Warning</b>.").format(
				frappe.bold(doc.customer)
			),
			title=_("Past Due"),
			indicator="orange",
			alert=True,
		)
	return None


def _problem_freeze() -> str | None:
	"""§11 — a freeze stops new unsecured exposure for everyone, good standing
	included. The order has to be re-typed COD or prepaid."""
	settings = utils.get_settings()
	if not settings.company_freeze_active:
		return None

	return _(
		"A company-wide credit freeze is in effect, so no account can add new exposure — "
		"good standing included. Reason: {0}. Re-type this order as COD or prepaid, or "
		"wait for Finance to lift the freeze."
	).format(settings.freeze_reason or _("not recorded"))


def _apply_workout_paydown(doc, order_type):
	"""§9 — every order for a workout account carries a paydown."""
	from cannabis_management.credit_and_ar import plan_workout

	if order_type == utils.ORDER_TYPE_SAMPLE:
		doc.custom_workout_paydown_required = 0
		return

	workout = plan_workout.get_active_workout(doc.customer)
	if not workout:
		doc.custom_workout_paydown_required = 0
		doc.custom_ar_case = None
		return

	doc.custom_ar_case = workout["name"]
	doc.custom_workout_paydown_required = plan_workout.required_paydown(
		workout, flt(doc.grand_total)
	)

	if doc.custom_workout_paydown_required:
		frappe.msgprint(
			_(
				"{0} is on a workout. A cleared paydown of <b>{1}</b> is required against "
				"this order before it can be submitted. No paydown, no product."
			).format(
				frappe.bold(doc.customer),
				utils.fmt_currency(doc.custom_workout_paydown_required, doc.currency),
			),
			title=_("Workout Paydown"),
			indicator="orange",
		)


def _check_workout_paydown(doc):
	from cannabis_management.credit_and_ar import plan_workout

	required = flt(doc.custom_workout_paydown_required)
	if required <= 0:
		return

	received = plan_workout.get_cleared_paydowns(doc.name)
	doc.db_set("custom_workout_paydown_received", received, update_modified=False)

	if received + 0.005 < required:
		frappe.throw(
			_(
				"<b>No paydown, no product.</b><br><br>A cleared paydown of {0} is required "
				"against this order; {1} has cleared.<br><br>Record a Payment Entry with "
				"Ledger = <b>Workout Paydown</b> against this Sales Order."
			).format(
				utils.fmt_currency(required, doc.currency),
				utils.fmt_currency(received, doc.currency),
			),
			title=_("Workout Paydown Outstanding"),
		)


def _compute_required_deposit(doc, summary):
	"""Total cleared deposit needed before this order can be submitted.

	One reason only: §4 over-limit — the amount by which the order's *credit*
	exposure exceeds the available line. No single-order exception at any amount.

	The template's own up-front leg is deliberately **not** a deposit
	requirement. A `50% down NETnn` term used to add its 50% here, which meant a
	$10,000 order could not be submitted until $5,000 had cleared — a hard block
	stock ERPNext does not have, where a due-immediately payment-schedule row is
	a *due date*, not a gate on submitting the order. The schedule ERPNext builds
	from the template still stands and the money is still owed on day zero; it is
	simply collected and chased like any other due amount rather than held over
	the order. See the decision log.

	Only the deferred portion of a 50%-down order is credit, so only that
	portion is measured against the line — that part is unchanged, because it is
	an exposure measurement rather than a deposit demand.
	"""
	grand_total = flt(doc.grand_total)
	credit_portion = utils.template_credit_portion(doc.payment_terms_template) / 100.0

	order_credit_exposure = grand_total * credit_portion
	available = flt(summary["available_line"])

	over_limit = max(0.0, order_credit_exposure - available)
	doc.custom_required_deposit = flt(over_limit)

	if over_limit > 0:
		frappe.msgprint(
			_describe_over_limit(doc, summary, order_credit_exposure, over_limit),
			title=_("Credit Limit Exceeded"),
			indicator="orange",
		)


def _describe_over_limit(doc, summary, order_credit_exposure, over_limit) -> str:
	"""The arithmetic, spelled out — approved limit, what is already committed,
	what is left, what this order asks for, and the shortfall.

	Sales' first question is always "over by how much?", so that figure leads and
	is repeated at the bottom. The same text backs the orange warning at save and
	the refusal at submit, so the two can never say different numbers.
	"""
	currency = doc.currency

	def money(amount):
		return utils.fmt_currency(amount, currency)

	return _(
		"This order exceeds {customer}'s credit limit by <b>{over}</b>."
		"<ul style='margin:8px 0 0 16px;padding:0'>"
		"<li>Approved credit limit: <b>{limit}</b></li>"
		"<li>Already committed (unpaid invoices + open Terms orders): <b>{used}</b></li>"
		"<li>Available line: <b>{available}</b></li>"
		"<li>This order: <b>{order}</b></li>"
		"</ul>"
		"<br>Reduce the order to <b>{available}</b> or less, or record a cleared "
		"deposit of <b>{over}</b> against it."
	).format(
		customer=doc.customer,
		over=money(over_limit),
		limit=money(summary["approved_limit"]),
		used=money(summary["total"]),
		available=money(max(0.0, flt(summary["available_line"]))),
		order=money(order_credit_exposure),
	)


# ── deposits ─────────────────────────────────────────────────────────────────


def get_cleared_deposits(sales_order: str) -> float:
	"""Submitted, cleared customer receipts earmarked against this order.

	"Cleared" means the bank has confirmed it: a clearance date, or an
	instant mode of payment such as cash. A deposit that has not cleared is a
	promise, not a payment.
	"""
	rows = frappe.get_all(
		"Payment Entry",
		filters={
			"docstatus": 1,
			"payment_type": "Receive",
			"custom_against_sales_order": sales_order,
			"custom_ledger": ("in", [utils.LEDGER_DEPOSIT, utils.LEDGER_WORKOUT_PAYDOWN]),
		},
		fields=["name", "paid_amount", "clearance_date", "mode_of_payment", "custom_ledger"],
	)

	total = 0.0
	for row in rows:
		if row.custom_ledger != utils.LEDGER_DEPOSIT:
			continue
		if _is_cleared(row):
			total += flt(row.paid_amount)
	return flt(total)


def _is_cleared(row) -> bool:
	if row.get("clearance_date"):
		return True
	if row.get("mode_of_payment"):
		return frappe.db.get_value("Mode of Payment", row["mode_of_payment"], "type") == "Cash"
	return False


def _check_deposit(doc):
	"""§4 — an order may not commit exposure past the approved line.

	Recomputed live rather than trusted from the save: another order for the same
	credit group may have been submitted, or an invoice paid, since this document
	was written down. The refusal leads with the limit breach — that is what
	actually stopped the order — and offers the cleared deposit as the way through
	rather than presenting itself as a paperwork problem.
	"""
	summary = credit_engine.get_line_summary(doc.customer, exclude_sales_order=doc.name)
	credit_portion = utils.template_credit_portion(doc.payment_terms_template) / 100.0
	order_credit_exposure = flt(doc.grand_total) * credit_portion

	required = max(0.0, order_credit_exposure - flt(summary["available_line"]))
	doc.custom_required_deposit = flt(required) if required > 0.005 else 0

	if required <= 0.005:
		return

	received = get_cleared_deposits(doc.name)
	doc.db_set("custom_deposit_received", received, update_modified=False)
	doc.db_set("custom_deposit_cleared", int(received + 0.005 >= required), update_modified=False)

	if received + 0.005 < required:
		frappe.throw(
			_describe_over_limit(doc, summary, order_credit_exposure, required)
			+ _(
				"<br><br>Cleared deposits so far: <b>{0}</b>. To deposit, record a Payment "
				"Entry against this Sales Order with Ledger = <b>Deposit</b>, reconciled or "
				"paid by an instant method."
			).format(utils.fmt_currency(received, doc.currency)),
			title=_("Credit Limit Exceeded"),
		)
