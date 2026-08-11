"""AR Case — one document for every stop-work state.

Warning, Hard Hold, Immediate Hold, Payment Plan and Workout are case *types*,
not separate DocTypes. The scheduler creates and updates these, so the document
is not submittable; `Version` carries the audit trail.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, nowdate

from cannabis_management.credit_and_ar import credit_engine, utils

TYPE_WARNING = "Warning"
TYPE_HARD_HOLD = "Hard Hold"
TYPE_IMMEDIATE_HOLD = "Immediate Hold"
TYPE_PAYMENT_PLAN = "Payment Plan"
TYPE_WORKOUT = "Workout"

HOLDING_TYPES = (TYPE_HARD_HOLD, TYPE_IMMEDIATE_HOLD)

STATUS_OPEN = "Open"
STATUS_ACTIVE = "Active"
STATUS_CURED = "Cured"
STATUS_RELEASED = "Released"
STATUS_DEFAULTED = "Defaulted"
STATUS_CLOSED = "Closed"

# A case in one of these no longer restrains the customer.
INACTIVE_STATUSES = (STATUS_CURED, STATUS_RELEASED, STATUS_CLOSED)

# Cases the daily engine may transition on its own. Anything a human released or
# defaulted stays put — the scheduler must never quietly undo a decision.
AUTO_MANAGED_STATUSES = (STATUS_OPEN, STATUS_ACTIVE)


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

	# ── defaults ─────────────────────────────────────────────────────────

	def _set_defaults(self):
		if not self.opened_on:
			self.opened_on = nowdate()
		if not self.opened_by:
			self.opened_by = frappe.session.user
		if not self.company:
			self.company = frappe.defaults.get_user_default("Company")
		if not self.assigned_to:
			self.assigned_to = utils.routed_user("collections_officer")

		if self.case_type == TYPE_WORKOUT:
			settings = utils.get_settings()
			if not self.paydown_mode:
				self.paydown_mode = settings.default_paydown_mode
			if self.paydown_mode == "Percent of Order Value" and not self.paydown_percent:
				self.paydown_percent = settings.default_paydown_percent

	def _refresh_figures(self):
		"""Past-due figures are always live, never trusted from the form."""
		if not self.customer:
			return
		snapshot = credit_engine.get_past_due_snapshot(self.customer)
		self.past_due_amount = snapshot["past_due_amount"]
		self.total_outstanding = snapshot["total_outstanding"]
		self.max_days_past_due = snapshot["max_days_past_due"]

	# ── guards ───────────────────────────────────────────────────────────

	def _guard_workout_designation(self):
		"""§9 — only the Managing Director designates a workout account."""
		if self.case_type != TYPE_WORKOUT:
			return

		previous = self.get_doc_before_save()
		already_workout = previous and previous.case_type == TYPE_WORKOUT
		if already_workout:
			return

		if self.flags.ignore_role_guards:
			return

		if not utils.has_any_role("Managing Director", "System Manager"):
			frappe.throw(
				_("Only the Managing Director can designate a workout account."),
				frappe.PermissionError,
				title=_("Not Authorised"),
			)

		self.workout_designated_by = frappe.session.user
		self.workout_designated_on = nowdate()

		if not self.starting_balance:
			self.starting_balance = credit_engine.get_current_exposure(self.customer)

	def _guard_plan_creation(self):
		"""§8 — a payment plan is Finance's instrument, not Sales'."""
		previous = self.get_doc_before_save()
		if previous and previous.case_type == TYPE_PAYMENT_PLAN:
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
		"""Release is a Credit Finance action, verified live — never a field edit."""
		if self.status != STATUS_RELEASED:
			return

		previous = self.get_doc_before_save()
		if previous and previous.status == STATUS_RELEASED:
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
		if self.case_type != TYPE_PAYMENT_PLAN:
			return

		self._guard_plan_creation()

		problems = []

		if not self.plan_signed_document:
			problems.append(_("The signed plan document must be attached."))
		if not self.plan_signed_on:
			problems.append(_("Plan Signed On is required."))
		if flt(self.plan_principal) <= 0:
			problems.append(_("Plan principal must be greater than zero."))
		if not self.schedule:
			problems.append(_("The plan needs an installment schedule."))

		scheduled = flt(sum(flt(row.amount) for row in self.schedule))
		if self.schedule and abs(scheduled - flt(self.plan_principal)) > 0.01:
			problems.append(
				_("The schedule totals {0} but the plan principal is {1}. They must match.").format(
					utils.fmt_currency(scheduled), utils.fmt_currency(self.plan_principal)
				)
			)

		if self.is_new():
			today = getdate(nowdate())
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

		# A child row appended without an explicit status comes through as NULL —
		# the DocType default is not applied by `append()`. Every downstream check
		# filters on status, so a blank one silently drops the row out of the
		# installment engine entirely.
		for row in self.schedule:
			if not row.status:
				row.status = "Pending"

		self.missed_installments = len(
			[row for row in self.schedule if row.status == "Missed"]
		)


# ── customer roll-up ─────────────────────────────────────────────────────────


def sync_customer_from_cases(customer: str):
	"""Recompute the customer's hold flags from whichever cases are live.

	One customer can carry several cases at once — a payment plan and a fresh
	warning, say. The strongest live case wins.
	"""
	if not customer:
		return

	cases = frappe.get_all(
		"AR Case",
		filters={"customer": customer, "status": ("not in", INACTIVE_STATUSES)},
		fields=["name", "case_type", "status", "opened_on"],
		order_by="opened_on asc",
	)

	hold_type = utils.HOLD_NONE
	active_case = None
	hold_since = None

	priority = {
		TYPE_WARNING: 1,
		TYPE_PAYMENT_PLAN: 2,
		TYPE_WORKOUT: 3,
		TYPE_HARD_HOLD: 4,
		TYPE_IMMEDIATE_HOLD: 5,
	}
	ranked = sorted(cases, key=lambda row: priority.get(row.case_type, 0), reverse=True)

	credit_status = None
	if ranked:
		top = ranked[0]
		active_case = top.name
		if top.case_type in HOLDING_TYPES:
			hold_type = top.case_type
			hold_since = top.opened_on
			credit_status = utils.STATUS_HARD_HOLD
		elif top.case_type == TYPE_WARNING:
			hold_type = utils.HOLD_WARNING
			credit_status = utils.STATUS_WARNING
		elif top.case_type == TYPE_PAYMENT_PLAN:
			credit_status = utils.STATUS_PAYMENT_PLAN
		elif top.case_type == TYPE_WORKOUT:
			credit_status = utils.STATUS_WORKOUT

	values = {
		"custom_on_hold": int(hold_type in utils.BLOCKING_HOLDS),
		"custom_hold_type": hold_type,
		"custom_hold_since": hold_since,
		"custom_active_ar_case": active_case,
	}

	if credit_status:
		values["custom_credit_status"] = credit_status
	else:
		# No live case — fall back to whether the account has approved terms.
		has_line = credit_engine.get_active_credit_application(customer)
		values["custom_credit_status"] = (
			utils.STATUS_TERMS_APPROVED if has_line else utils.STATUS_COD
		)

	frappe.db.set_value("Customer", customer, values, update_modified=False)


def get_active_case(customer: str, case_type: str | None = None) -> dict | None:
	filters = {"customer": customer, "status": ("not in", INACTIVE_STATUSES)}
	if case_type:
		filters["case_type"] = case_type

	rows = frappe.get_all(
		"AR Case",
		filters=filters,
		fields=["name", "case_type", "status", "paydown_mode", "paydown_percent", "paydown_amount"],
		order_by="opened_on desc",
		limit=1,
	)
	return rows[0] if rows else None
