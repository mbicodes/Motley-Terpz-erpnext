import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.credit_and_ar import ar_cap, credit_engine, customer_contact_rules, utils


def validate(doc, method=None):
	if not doc.customer:
		return

	customer_contact_rules.validate_sales_order(doc)

	if utils.is_policy_exempt(doc.customer):
		_clear_credit_fields(doc)
		return

	_default_payment_mode(doc)

	order_type = utils.resolve_order_type(doc)

	if order_type == utils.ORDER_TYPE_COD:
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
	order_type = utils.resolve_order_type(doc)

	if order_type == utils.ORDER_TYPE_TERMS:
		ar_cap.assert_under_cap(doc, ar_cap.order_credit_amount(doc), noun="order")

	if utils.is_policy_exempt(doc.customer):
		return

	_assert_within_available_line(doc)

	if order_type == utils.ORDER_TYPE_SAMPLE:
		_assert_zero_value(doc)
		return

	if order_type == utils.ORDER_TYPE_COD:
		_check_workout_paydown(doc)
		return

	_assert_terms_allowed(doc)
	_check_workout_paydown(doc)

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
	if doc.docstatus == 1 and doc.customer:
		credit_engine.refresh_customer_exposure(doc.customer)

	if doc.docstatus != 0 or utils.is_policy_exempt(doc.customer):
		return

	should_block = int(
		utils.resolve_order_type(doc) == utils.ORDER_TYPE_TERMS
		and doc.custom_approval_status == utils.APPROVAL_PENDING
	)
	if int(doc.custom_print_blocked or 0) != should_block:
		doc.db_set("custom_print_blocked", should_block, update_modified=False)


def on_submit(doc, method=None):
	if doc.customer:
		credit_engine.refresh_customer_exposure(doc.customer)

	if doc.custom_ar_case:
		doc.db_set(
			"custom_workout_balance_at_order",
			credit_engine.get_current_exposure(doc.customer),
			update_modified=False,
		)


def on_cancel(doc, method=None):
	if doc.customer:
		credit_engine.refresh_customer_exposure(doc.customer)


def _clear_credit_fields(doc):
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
	doc.custom_approval_status = utils.APPROVAL_NOT_REQUIRED
	doc.custom_print_blocked = 0
	doc.custom_required_deposit = 0
	doc.custom_credit_application = None
	doc.custom_customer_available_line = 0
	doc.payment_schedule = []


def _apply_sample(doc):
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


def _assert_within_available_line(doc):
	status = frappe.db.get_value("Customer", doc.customer, "custom_credit_status")
	if status not in utils.LINE_ENFORCED_STATUSES:
		return

	available = flt(credit_engine.get_available_line(doc.customer, exclude_sales_order=doc.name))
	amount = flt(doc.grand_total)
	if amount <= available:
		return

	if utils.can_override_line():
		return

	frappe.throw(
		_(
			"This order is worth <b>{amount}</b> but {customer} has only <b>{available}</b> "
			"left on their credit line."
			"<ul style='margin:8px 0 0 16px;padding:0'>"
			"<li>Credit status: <b>{status}</b></li>"
			"<li>Available line: <b>{available}</b></li>"
			"<li>This order: <b>{amount}</b></li>"
			"</ul>"
			"<br>The limit applies to every payment mode, Cash on Delivery included. "
			"Reduce the order to <b>{available}</b> or less, collect against the "
			"outstanding balance, or ask an <b>{role}</b> to raise it."
		).format(
			amount=utils.fmt_currency(amount, doc.currency),
			customer=frappe.bold(doc.customer),
			available=utils.fmt_currency(max(0.0, available), doc.currency),
			status=status,
			role=utils.LINE_OVERRIDE_ROLE,
		),
		title=_("Over Available Line"),
	)


def _assert_zero_value(doc):
	if flt(doc.grand_total):
		frappe.throw(
			_(
				"A Sample order must be zero value, but this one totals {0}.<br><br>"
				"Remove the charge, or change the order type if this is a real sale."
			).format(utils.fmt_currency(doc.grand_total, doc.currency)),
			title=_("Sample Order"),
		)


def _validate_terms(doc, summary):
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
	doc.custom_approval_status = utils.APPROVAL_APPROVED
	doc.custom_terms_approved_by = "Administrator"
	doc.custom_terms_approved_on = frappe.utils.now_datetime()
	doc.custom_terms_rejection_reason = None

	if not doc.get("__islocal"):
		doc.add_comment(
			"Comment",
			_(
				"Terms auto-approved — order stays within {0}'s approved credit line, "
				"no Managing Director sign-off required."
			).format(doc.customer),
		)


def _warn_terms_problems(doc):
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
	problems = _terms_problems(doc)
	utils.throw_consolidated(problems, "Terms Order Cannot Be Submitted")


def _terms_problems(doc) -> list[str]:
	settings = utils.get_settings()

	checks = (
		_problem_cod_status(doc),
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


def _problem_cod_status(doc) -> str | None:
	status = frappe.db.get_value("Customer", doc.customer, "custom_credit_status")
	if status != utils.STATUS_COD:
		return None

	return _(
		"{0} is on <b>COD</b>. Orders with Mode of Payment = <b>{1}</b> cannot be "
		"submitted or printed. Use Cash On Delivery, or ask Finance to approve terms."
	).format(doc.customer, utils.MODE_TERMS)


def _problem_terms_template(doc) -> str | None:
	if not doc.payment_terms_template:
		return _("A Payment Terms Template is required on a Terms order.")
	return None


def _problem_line(doc) -> str | None:
	blocker = credit_engine.describe_line_blocker(doc.customer)
	return frappe.utils.strip_html(blocker).strip() if blocker else None


def _problem_one_term_per_account(doc) -> str | None:
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
	from cannabis_management.credit_and_ar import plan_workout

	status = frappe.db.get_value("Customer", doc.customer, "custom_credit_status")
	if status != utils.STATUS_WORKOUT and not plan_workout.get_active_workout(doc.customer):
		return None

	return _(
		"{0} is a workout account. Workout accounts are COD or prepaid only — zero new "
		"unsecured exposure, no exceptions."
	).format(doc.customer)


def _problem_payment_plan(doc) -> list[str]:
	from cannabis_management.credit_and_ar import plan_workout

	return plan_workout.plan_problems(doc.customer)


def _problem_hold(doc) -> str | None:
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import get_hold_type

	hold_type = get_hold_type(doc.customer)

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
	settings = utils.get_settings()
	if not settings.company_freeze_active:
		return None

	return _(
		"A company-wide credit freeze is in effect, so no account can add new exposure — "
		"good standing included. Reason: {0}. Re-type this order as COD or prepaid, or "
		"wait for Finance to lift the freeze."
	).format(settings.freeze_reason or _("not recorded"))


def _apply_workout_paydown(doc, order_type):
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
	doc.custom_workout_paydown_required = plan_workout.required_paydown(workout, flt(doc.net_total))

	previous_balance = plan_workout.get_previous_workout_balance(workout)
	current_balance = credit_engine.get_current_exposure(doc.customer)
	doc.custom_workout_paydown_received = max(0.0, flt(previous_balance) - current_balance)

	required = flt(doc.custom_workout_paydown_required)
	made = flt(doc.custom_workout_paydown_received)
	if required and made + 0.005 < required:
		frappe.msgprint(
			_(
				"{0} is a workout account.<br>Required paydown: {1}<br>Paid down: {2}"
				"<br>Remaining: {3}"
			).format(
				frappe.bold(doc.customer),
				utils.fmt_currency(required, doc.currency),
				utils.fmt_currency(made, doc.currency),
				utils.fmt_currency(required - made, doc.currency),
			),
			title=_("Workout Paydown Outstanding"),
			indicator="orange",
		)


def _check_workout_paydown(doc):
	from cannabis_management.credit_and_ar import plan_workout

	required = flt(doc.custom_workout_paydown_required)
	if required <= 0:
		return

	workout = plan_workout.get_active_workout(doc.customer)
	previous_balance = plan_workout.get_previous_workout_balance(workout)
	current_balance = credit_engine.get_current_exposure(doc.customer)
	made = max(0.0, flt(previous_balance) - current_balance)
	doc.db_set("custom_workout_paydown_received", made, update_modified=False)

	if made + 0.005 < required:
		frappe.throw(
			_("Required paydown: {0}<br>Paid down: {1}<br>Remaining: {2}").format(
				utils.fmt_currency(required, doc.currency),
				utils.fmt_currency(made, doc.currency),
				utils.fmt_currency(required - made, doc.currency),
			),
			title=_("Workout Paydown Outstanding"),
		)


def _compute_required_deposit(doc, summary):
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


def _ar_source_label() -> str:
	from cannabis_management.credit_and_ar import credit_engine

	if credit_engine.get_ar_source() == credit_engine.AR_SOURCE_INVOICES:
		return "unpaid invoices"
	return "ledger balance"


def _describe_over_limit(doc, summary, order_credit_exposure, over_limit, noun: str = "order") -> str:
	currency = doc.currency

	def money(amount):
		return utils.fmt_currency(amount, currency)

	return _(
		"This {noun} exceeds {customer}'s credit limit by <b>{over}</b>."
		"<ul style='margin:8px 0 0 16px;padding:0'>"
		"<li>Approved credit limit: <b>{limit}</b></li>"
		"<li>Already committed ({ar_source_label} + open Terms orders): <b>{used}</b></li>"
		"<li>Available line: <b>{available}</b></li>"
		"<li>This {noun}: <b>{order}</b></li>"
		"</ul>"
		"<br>Reduce the {noun} to <b>{available}</b> or less, or record a cleared "
		"deposit of <b>{over}</b> against it."
	).format(
		noun=noun,
		customer=doc.customer,
		ar_source_label=_ar_source_label(),
		over=money(over_limit),
		limit=money(summary["approved_limit"]),
		used=money(summary["total"]),
		available=money(max(0.0, flt(summary["available_line"]))),
		order=money(order_credit_exposure),
	)


def get_cleared_deposits(sales_order: str) -> float:
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
