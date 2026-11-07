import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate

from cannabis_management.credit_and_ar import collections_engine as engine


class ARCollection(Document):
	def before_insert(self):
		if not self.assigned_to:
			self.assigned_to = engine.settings().default_assignee
		if not self.contact and not self.contact_email:
			for k, v in engine.default_contact(self.customer).items():
				if v and not self.get(k):
					self.set(k, v)

	def validate(self):
		before = self.get_doc_before_save()
		old_stage = before.stage if before else None
		self.flags.from_stage = self.flags.from_stage or old_stage

		self._validate_one_open(old_stage)
		self._fill_contact(before)
		self._validate_installments()
		if self.is_new() or self.stage != old_stage:
			self._validate_stage(old_stage)
		elif self.write_off_journal_entry and (not before or before.write_off_journal_entry != self.write_off_journal_entry):
			# write-off JE linked on an open collection: close it when nothing is owed any more
			if self.stage != engine.COLLECTED and self._live_outstanding() <= engine.EPS:
				self.flags.move_note = _("balance written off")
				self.stage = engine.COLLECTED
				self._validate_stage(old_stage)
		self.written_off = 1 if self.stage == engine.COLLECTED and self.write_off_journal_entry else 0

	# ---------------------------------------------------------------- validation

	def _validate_one_open(self, old_stage):
		if self.stage == engine.COLLECTED:
			return
		if not (self.is_new() or old_stage == engine.COLLECTED):
			return
		if engine.open_collection(self.customer, self.ledger, exclude=None if self.is_new() else self.name):
			frappe.throw(_("This customer already has an open collection."), title=_("Open collection exists"))

	def _fill_contact(self, before):
		"""A new or changed contact fills email and phone, unless they were edited in the same save."""
		if not self.contact or (before and before.contact == self.contact):
			return
		details = engine.contact_details(self.contact)
		for field in ("contact_email", "contact_phone"):
			edited = before and self.get(field) != before.get(field)
			if details.get(field) and not edited:
				self.set(field, details[field])

	def _validate_installments(self):
		if not self.installments:
			return
		total = flt(sum(flt(r.amount, 2) for r in self.installments), 2)
		if abs(total - flt(self.plan_amount, 2)) > engine.EPS:
			frappe.throw(
				_("The installments must add up to the plan amount of {0}.").format(engine.fmt_money(self.plan_amount)),
				title=_("Installments do not match"),
			)
		for r in self.installments:
			if flt(r.amount, 2) <= 0:
				frappe.throw(_("Row {0}: the installment amount must be greater than zero.").format(r.idx))
			r.status = engine.installment_status(r.amount, r.paid_amount, r.due_date)
		if not self.plan_created_on:
			self.plan_created_on = getdate(nowdate())

	def _live_outstanding(self):
		if self.flags.live_outstanding is not None:
			return flt(self.flags.live_outstanding, 2)
		return engine.snapshot_for(self.customer, self.ledger)["outstanding"]

	def _validate_stage(self, old_stage):
		stage = self.stage
		if stage == engine.PROMISE:
			if not self.promise_date or flt(self.promise_amount) <= 0:
				frappe.throw(_("Enter a promise date and an amount greater than zero."), title=_("Promise to Pay"))
			self.promise_status = "Open"
			self.promise_made_on = getdate(nowdate())
		elif stage == engine.DISPUTED:
			if not self.dispute_reason:
				frappe.throw(_("Select a dispute reason before moving the card to Disputed."), title=_("Disputed"))
		elif stage == engine.ESCALATED:
			if not self.escalation_reason:
				frappe.throw(_("Select an escalation reason before moving the card to Escalated."), title=_("Escalated"))
		elif stage == engine.PLAN:
			if not self.installments:
				frappe.throw(_("Set up the payment plan before moving the card to Payment Plan."), title=_("Payment Plan"))
		elif stage == engine.COLLECTED:
			live = self._live_outstanding()
			if live > engine.EPS:
				frappe.throw(
					_("{0} still has an outstanding balance of {1}. Record the payment or write off the balance first.").format(
						self.customer_name or self.customer, engine.fmt_money(live)
					),
					title=_("Balance outstanding"),
				)
			self.collected_on = getdate(nowdate())
			self.outstanding_cached = 0
			self.consider_escalation = 0

		if old_stage == engine.COLLECTED and stage != engine.COLLECTED:
			self.collected_on = None
		if old_stage == engine.PROMISE and stage != engine.PROMISE and self.promise_status == "Open":
			self.promise_status = None

	# ---------------------------------------------------------------- after save

	def after_insert(self):
		engine.sync_assignment(self, notify=not self.flags.silent_assignment)

	def on_update(self):
		before = self.get_doc_before_save()
		if before and before.stage != self.stage:
			note = self.flags.move_note
			text = _("Moved from {0} to {1}").format(_(before.stage), _(self.stage))
			if note:
				text += ": " + note
			self.add_comment("Info", text)
		if self.flags.extra_note:
			self.add_comment("Info", self.flags.extra_note)
		if self.flags.plan_trim_note:
			self.add_comment("Info", self.flags.plan_trim_note)
		if before and before.assigned_to != self.assigned_to and self.stage != engine.COLLECTED:
			engine.sync_assignment(self, notify=not self.flags.silent_assignment)
		if self.stage == engine.COLLECTED and (not before or before.stage != engine.COLLECTED):
			engine.close_assignments(self)
		elif before and before.stage == engine.COLLECTED and self.stage != engine.COLLECTED:
			engine.sync_assignment(self, notify=not self.flags.silent_assignment)
		if not self.flags.no_realtime:
			engine.publish_refresh(self.customer)
		for k in ("move_note", "extra_note", "plan_trim_note", "from_stage", "live_outstanding", "promise_changed"):
			self.flags.pop(k, None)

	def on_trash(self):
		engine.close_assignments(self)
		engine.publish_refresh(self.customer)

	# ---------------------------------------------------------------- print

	def get_statement(self):
		"""Data for the AR Collection Statement print format (same calculation as the board)."""
		today = getdate(nowdate())
		s = engine.snapshot_for(self.customer, self.ledger)
		invoices = []
		for inv in s["invoices"]:
			days = (today - getdate(inv["due_date"])).days if inv.get("due_date") else 0
			invoices.append(
				{
					"name": inv["name"],
					"company": inv.get("company"),
					"posting_date": inv.get("posting_date"),
					"due_date": inv.get("due_date"),
					"days_past_due": max(0, days),
					"outstanding": flt(inv["outstanding"], 2),
				}
			)
		companies = sorted({i["company"] for i in invoices if i.get("company")})
		return {
			"statement_date": today,
			"companies": companies or [frappe.defaults.get_global_default("company")],
			"customer": self.customer,
			"customer_name": self.customer_name or self.customer,
			"ledger": self.ledger,
			"invoices": invoices,
			"total": s["outstanding"],
			"aging": [
				{"label": "0-30", "amount": s["aging"][0]},
				{"label": "31-60", "amount": s["aging"][1]},
				{"label": "61-90", "amount": s["aging"][2]},
				{"label": "90+", "amount": s["aging"][3]},
			],
			"plan": [
				{"due_date": r.due_date, "amount": r.amount, "paid": r.paid_amount, "status": r.status}
				for r in self.installments
				if r.status != engine.INST_PAID
			],
		}
