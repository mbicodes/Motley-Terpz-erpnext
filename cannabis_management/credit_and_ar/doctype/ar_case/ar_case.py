import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from cannabis_management.credit_and_ar import credit_engine, utils

STATUS_ACTIVE = "Active"
STATUS_CLOSED = "Closed"

INACTIVE_STATUSES = (STATUS_CLOSED,)

RESOLUTION_RELEASE = "Release"
RESOLUTION_PAYMENT_PLAN = "Payment Plan"
RESOLUTION_WORKOUT = "Workout"


class ARCase(Document):
	def validate(self):
		self._set_defaults()
		self._guard_workout_designation()
		self._guard_release()
		self._validate_payment_plan()
		self._refresh_figures()

	def on_update(self):
		from cannabis_management.credit_and_ar import plan_workout

		plan_workout.on_ar_case_update(self)
		sync_customer_from_cases(self.customer)

	def after_delete(self):
		sync_customer_from_cases(self.customer)

	def _set_defaults(self):
		if not self.opened_on:
			self.opened_on = now_datetime()
		if not self.opened_by:
			self.opened_by = frappe.session.user
		if not self.status:
			self.status = STATUS_ACTIVE
		if not self.assigned_to:
			self.assigned_to = utils.routed_user("collections_officer")

		if self.resolution == RESOLUTION_WORKOUT:
			settings = utils.get_settings()
			if not self.paydown_mode:
				self.paydown_mode = settings.default_paydown_mode
			if self.paydown_mode == "Percent of Order Value" and not self.paydown_percent:
				self.paydown_percent = settings.default_paydown_percent

	def _refresh_figures(self):
		if not self.customer:
			return
		snapshot = credit_engine.get_past_due_snapshot(self.customer)
		self.past_due_amount = snapshot["past_due_amount"]
		self.total_outstanding = snapshot["total_outstanding"]
		self.max_days_past_due = snapshot["max_days_past_due"]

	def _guard_workout_designation(self):
		if self.resolution != RESOLUTION_WORKOUT:
			return

		previous = self.get_doc_before_save()
		already_workout = previous and previous.resolution == RESOLUTION_WORKOUT
		if already_workout:
			return

		if not self.starting_balance:
			self.starting_balance = credit_engine.get_current_exposure(self.customer)
		if not self.current_balance:
			self.current_balance = self.starting_balance

		if self.flags.ignore_role_guards:
			return

		if not utils.has_any_role("Managing Director", "System Manager"):
			frappe.throw(
				_("Only the Managing Director can designate a workout account."),
				frappe.PermissionError,
				title=_("Not Authorised"),
			)

		self.workout_designated_by = frappe.session.user
		self.workout_designated_on = getdate()

	def _guard_plan_creation(self):
		previous = self.get_doc_before_save()
		if previous and previous.resolution == RESOLUTION_PAYMENT_PLAN:
			return
		if self.flags.ignore_role_guards:
			return

		if not utils.has_any_role("Credit Finance", "System Manager"):
			frappe.throw(
				_("Only Credit Finance can put an account on a payment plan."),
				frappe.PermissionError,
				title=_("Not Authorised"),
			)

		if not self.finance_approved_by:
			self.finance_approved_by = frappe.session.user
			self.finance_approved_on = now_datetime()

	def _guard_release(self):
		if self.resolution != RESOLUTION_RELEASE:
			return

		previous = self.get_doc_before_save()
		if previous and previous.resolution == RESOLUTION_RELEASE:
			return

		if self.flags.from_release_api:
			return

		frappe.throw(
			_(
				"A hold is not released by editing this field. Use the "
				"<b>Release Hold</b> button so the release basis is verified and recorded."
			),
			title=_("Use the Release Action"),
		)

	def _validate_payment_plan(self):
		if self.resolution != RESOLUTION_PAYMENT_PLAN:
			return

		self._guard_plan_creation()

		problems = []

		if not self.plan_signed_document:
			problems.append(_("The signed plan document must be attached."))
		if not self.plan_signed_on:
			problems.append(_("Plan Signed On is required."))

		if self.is_new():
			today = getdate()
			for row in self.schedule:
				if row.due_date and getdate(row.due_date) < today:
					problems.append(
						_("Installment {0} is dated in the past ({1}).").format(
							row.idx, frappe.format(row.due_date, {"fieldtype": "Date"})
						)
					)
					break

		utils.throw_consolidated(problems, "Payment Plan Incomplete")

		if self.md_ratified and not self.md_ratified_by:
			if not utils.has_any_role("Managing Director", "System Manager"):
				frappe.throw(
					_("Only the Managing Director can ratify a payment plan."),
					frappe.PermissionError,
					title=_("Not Authorised"),
				)
			self.md_ratified_by = frappe.session.user
			self.md_ratified_on = now_datetime()
		elif not self.md_ratified:
			self.md_ratified_by = None
			self.md_ratified_on = None

		today = getdate()
		for row in self.schedule:
			row.status = utils.installment_status(row.amount, row.paid_amount, row.due_date, today)

		self.missed_installments = len(
			[row for row in self.schedule if row.status == utils.INSTALLMENT_MISSED]
		)


def sync_customer_from_cases(customer: str):
	if not customer:
		return

	if utils.is_policy_exempt(customer):
		return

	case = get_active_case(customer)

	if case:
		credit_status = {
			RESOLUTION_PAYMENT_PLAN: utils.STATUS_PAYMENT_PLAN,
			RESOLUTION_WORKOUT: utils.STATUS_WORKOUT,
		}.get(case.resolution, utils.STATUS_HARD_HOLD)

		if case.resolution == RESOLUTION_PAYMENT_PLAN and int(case.get("missed_installments") or 0) > 0:
			credit_status = utils.STATUS_HARD_HOLD

		values = {
			"custom_hold_since": getdate(case.opened_on) if case.opened_on else None,
			"custom_active_ar_case": case.name,
			"custom_credit_status": credit_status,
		}
		if frappe.db.has_column("Customer", "custom_hold_reason"):
			values["custom_hold_reason"] = case.get("trigger_reason") or ""
	else:
		values = {
			"custom_hold_since": None,
			"custom_active_ar_case": None,
		}
		if frappe.db.has_column("Customer", "custom_hold_reason"):
			values["custom_hold_reason"] = ""

		current_status = frappe.db.get_value("Customer", customer, "custom_credit_status")
		if current_status != utils.STATUS_WARNING:
			has_line = credit_engine.get_active_credit_application(customer)
			values["custom_credit_status"] = (
				utils.STATUS_TERMS_APPROVED if has_line else utils.STATUS_COD
			)

	frappe.db.set_value("Customer", customer, values, update_modified=False)


def get_hold_type(customer: str) -> str:
	if not customer:
		return utils.HOLD_NONE
	if utils.is_policy_exempt(customer):
		return utils.HOLD_NONE
	if frappe.db.get_value("Customer", customer, "custom_active_ar_case"):
		return utils.HOLD_HARD
	if frappe.db.get_value("Customer", customer, "custom_credit_status") == utils.STATUS_WARNING:
		return utils.HOLD_WARNING
	return utils.HOLD_NONE


def get_active_case(customer: str, resolution: str | None = None) -> dict | None:
	filters = {"customer": customer, "status": STATUS_ACTIVE}
	if resolution is not None:
		filters["resolution"] = resolution

	rows = frappe.get_all(
		"AR Case",
		filters=filters,
		fields=[
			"name",
			"status",
			"resolution",
			"trigger_reason",
			"opened_on",
			"paydown_mode",
			"paydown_percent",
			"paydown_amount",
			"starting_balance",
			"current_balance",
			"md_ratified",
			"missed_installments",
			"new_line_credit_application",
		],
		order_by="opened_on desc",
		limit=1,
	)
	return rows[0] if rows else None
