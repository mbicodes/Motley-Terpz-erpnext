# One deal on the Sales Operation Board (/app/sales-operation-board).
# Stages, probabilities, owners and lists come from Sales Pipeline Settings (see cannabis_management.sales_ops).
# Value, weighted value and the stage log are worked out here so the board, list view and reports agree.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, now_datetime

from cannabis_management import sales_ops


class SalesPipelineDeal(Document):
	def validate(self):
		s = sales_ops.get_settings()
		self.account = (self.account or "").strip()
		if not self.priority:
			self.priority = sales_ops.default_priority(s)
		st = sales_ops.stage_info(s, self.stage)
		if not st:
			frappe.throw(_("Stage {0} is not set up in Sales Pipeline Settings.").format(self.stage))
		self._check_owner(s)
		self._check_required(s, st)
		self.probability = st.probability
		self.deal_value = flt(self.value_override) or flt(self.total_grams) * flt(self.price_per_gram)
		self.weighted_value = flt(self.deal_value) * flt(self.probability) / 100.0
		self._log_stage()
		self._link_party()

	def _before(self):
		return None if self.is_new() else self.get_doc_before_save()

	def _check_owner(self, s):
		before = self._before()
		prev_owner = before.deal_owner if before else None
		if self.deal_owner and self.deal_owner != prev_owner:
			if self.deal_owner not in [o.user for o in s.owners if o.active]:
				frappe.throw(_("{0} is not an active owner in Sales Pipeline Settings.").format(self.deal_owner))
		if self.flags.ignore_permissions or frappe.flags.in_patch or frappe.flags.in_migrate:
			return
		user = frappe.session.user
		if sales_ops.is_manager(user):
			return
		if self.is_new():
			if self.deal_owner and self.deal_owner != user:
				frappe.throw(_("You can only create deals for yourself. A pipeline manager can assign deals to others."))
			return
		if prev_owner and prev_owner != user:
			frappe.throw(_("This deal belongs to {0}. Only a pipeline manager can change it.").format(sales_ops.owner_label(s, prev_owner)))
		if self.deal_owner != prev_owner and self.deal_owner != user:
			frappe.throw(_("Only a pipeline manager can assign a deal to someone else."))

	def _check_required(self, s, st):
		if not self.deal_owner:
			frappe.throw(_("Please choose an Owner for this deal."))
		if sales_ops.needs_followup(s, st) and not self.next_step_due:
			frappe.throw(_("Please set a Next Follow-up date. It is required for deals in {0}.").format(st.name))
		if st.is_closed and not st.is_won and not (self.lost_reason or "").strip():
			frappe.throw(_("Please enter a Lost Reason before moving this deal to {0}.").format(st.name))
		if st.is_closed and st.is_won and not self.customer:
			frappe.throw(_("Please link a Customer before moving this deal to {0}.").format(st.name))

	def _log_stage(self):
		now = now_datetime()
		before = self._before()
		if not before:
			if not self.get("stage_log"):
				self.append("stage_log", {"from_stage": "", "to_stage": self.stage, "changed_on": now,
					"changed_by": frappe.session.user, "days_in_previous": 0})
			self.stage_changed_on = self.stage_changed_on or now
			return
		if before.stage != self.stage:
			since = get_datetime(before.stage_changed_on or before.creation)
			self.append("stage_log", {
				"from_stage": before.stage, "to_stage": self.stage, "changed_on": now,
				"changed_by": frappe.session.user,
				"days_in_previous": round((now - since).total_seconds() / 86400.0, 1),
			})
			self.stage_changed_on = now
		elif not self.stage_changed_on:
			self.stage_changed_on = now

	def _link_party(self):
		"""No Customer and no Lead yet: reuse a Lead with the same company name, else create one."""
		if self.customer or self.lead or not self.account or self.flags.skip_lead:
			return
		existing = frappe.db.sql(
			"select name from `tabLead` where lower(trim(company_name)) = lower(%s) order by creation limit 1",
			self.account,
		)
		if existing:
			self.lead = existing[0][0]
			return
		lead = frappe.get_doc({
			"doctype": "Lead",
			"company_name": self.account,
			"lead_owner": self.deal_owner,
		})
		lead.flags.ignore_permissions = True
		lead.insert()
		self.lead = lead.name

	def on_update(self):
		s = sales_ops.get_settings()
		before = self.get_doc_before_save()
		prev_owner = before.deal_owner if before else None
		if self.deal_owner != prev_owner:
			if before:
				self.add_comment("Info", _("Owner changed from {0} to {1}").format(
					sales_ops.owner_label(s, prev_owner) if prev_owner else _("Unassigned"),
					sales_ops.owner_label(s, self.deal_owner) if self.deal_owner else _("Unassigned")))
			if self.deal_owner and s.notify_on_reassign:
				sales_ops.notify([self.deal_owner], _("{0} assigned the deal {1} to you").format(
					frappe.utils.get_fullname(frappe.session.user), self.account), deal=self.name)
		if before and before.stage != self.stage and s.notify_managers_on_stage:
			st = sales_ops.stage_info(s, self.stage)
			if st and st.notify_managers:
				sales_ops.notify(sales_ops.manager_users(s), _("{0} moved to {1} ({2})").format(
					self.account, self.stage, frappe.utils.fmt_money(self.deal_value, currency="USD")), deal=self.name)
		sales_ops.publish_board_update(self.name)

	def on_trash(self):
		sales_ops.publish_board_update(self.name)
