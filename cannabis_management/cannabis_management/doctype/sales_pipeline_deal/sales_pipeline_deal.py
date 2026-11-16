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
		self._clean_co_owners()
		self._check_owner(s)
		self._prefill_from_customer()
		self._link_account()
		self._check_required(s, st)
		self.probability = st.probability
		self._apply_requirements(s)
		self.deal_value = flt(self.value_override) or self._calculated_value()
		self.weighted_value = flt(self.deal_value) * flt(self.probability) / 100.0
		self._log_stage()
		self._link_party()

	def _apply_requirements(self, s):
		"""Requirement lines drive the deal: first line = Product Line / Tier, totals = sum of all lines."""
		rows = [r for r in (self.get("requirements") or []) if r.product_line or flt(r.total_grams) or flt(r.price_per_gram)]
		if len(rows) != len(self.get("requirements") or []):
			self.set("requirements", rows)
		if not rows:
			return
		tiers = {}
		for r in s.product_lines:
			tiers.setdefault(r.product_line, [])
			if r.tier:
				tiers[r.product_line].append(r.tier)
		for i, r in enumerate(rows, start=1):
			r.product_line = (r.product_line or "").strip()
			r.tier = (r.tier or "").strip()
			if not r.product_line:
				frappe.throw(_("Requirement {0}: please choose a Product Line.").format(i))
			if r.product_line not in tiers and r.product_line != (self._before() and self._row_line(r.name)):
				frappe.throw(_("Requirement {0}: {1} is not a Product Line in Sales Pipeline Settings.").format(i, r.product_line))
			if r.tier and r.tier not in tiers.get(r.product_line, []) and r.tier != (self._before() and self._row_tier(r.name)):
				frappe.throw(_("Requirement {0}: Tier {1} is not mapped to {2} in Sales Pipeline Settings.").format(i, r.tier, r.product_line))
			if flt(r.total_grams) < 0 or flt(r.price_per_gram) < 0:
				frappe.throw(_("Requirement {0}: grams and price cannot be negative.").format(i))
			r.amount = flt(r.total_grams) * flt(r.price_per_gram)
		grams = sum(flt(r.total_grams) for r in rows)
		amount = sum(flt(r.amount) for r in rows)
		self.product_line = rows[0].product_line
		self.tier = rows[0].tier
		self.total_grams = grams
		self.price_per_gram = amount / grams if grams else 0

	def _row_line(self, name):
		before = self._before()
		row = next((r for r in (before.get("requirements") or []) if r.name == name), None) if before else None
		return row.product_line if row else None

	def _row_tier(self, name):
		before = self._before()
		row = next((r for r in (before.get("requirements") or []) if r.name == name), None) if before else None
		return row.tier if row else None

	def _calculated_value(self):
		rows = self.get("requirements") or []
		if rows:
			return sum(flt(r.amount) for r in rows)
		return flt(self.total_grams) * flt(self.price_per_gram)

	def _before(self):
		return None if self.is_new() else self.get_doc_before_save()

	def co_owner_list(self):
		return [r.user for r in (self.get("co_owners") or []) if r.user]

	def _clean_co_owners(self):
		"""One row per person; the primary owner is never also a co-owner."""
		seen = set()
		keep = []
		for r in self.get("co_owners") or []:
			if not r.user or r.user == self.deal_owner or r.user in seen:
				continue
			seen.add(r.user)
			keep.append(r)
		if len(keep) != len(self.get("co_owners") or []):
			self.set("co_owners", keep)

	def _check_owner(self, s):
		before = self._before()
		prev_owner = before.deal_owner if before else None
		prev_co = [r.user for r in (before.get("co_owners") or [])] if before else []
		co = self.co_owner_list()
		active = [o.user for o in s.owners if o.active]
		if self.deal_owner and self.deal_owner != prev_owner:
			if self.deal_owner not in active:
				frappe.throw(_("{0} is not an active owner in Sales Pipeline Settings.").format(self.deal_owner))
		for u in co:
			if u not in prev_co and u not in active:
				frappe.throw(_("{0} is not an active owner in Sales Pipeline Settings, so they cannot be a co-owner.").format(u))
		if self.flags.ignore_permissions or frappe.flags.in_patch or frappe.flags.in_migrate:
			return
		user = frappe.session.user
		if sales_ops.is_manager(user):
			return
		if self.is_new():
			if self.deal_owner and self.deal_owner != user:
				frappe.throw(_("You can only create deals for yourself. A pipeline manager can assign deals to others."))
			return
		is_co = user in prev_co
		if prev_owner and prev_owner != user and not is_co:
			frappe.throw(_("This deal belongs to {0}. Only a pipeline manager can change it.").format(sales_ops.owner_label(s, prev_owner)))
		if self.deal_owner != prev_owner:
			# a non-manager may only take an unassigned deal for themselves
			if prev_owner or self.deal_owner != user:
				frappe.throw(_("Only a pipeline manager can assign a deal to someone else."))
		if set(co) != set(prev_co) - {self.deal_owner}:
			if not (self.deal_owner == user and prev_owner in (None, "", user)):
				frappe.throw(_("Only the deal owner or a pipeline manager can change the co-owners."))

	def _prefill_from_customer(self):
		"""Buyer picked (new deal or a new Customer): fill the empty account and contact fields from the Customer."""
		if not self.customer:
			return
		before = self._before()
		if before and before.customer == self.customer:
			return
		info = sales_ops.customer_buyer_info(self.customer)
		for field in ("account", "contact_name", "phone", "email", "location_address"):
			if info.get(field) and not (self.get(field) or "").strip():
				self.set(field, info[field])

	def _link_account(self):
		"""Every deal belongs to an account on the Leads board: the chosen one, else the buyer's, else a new one.
		A deal without a buyer takes the account's Customer / Lead and contact details."""
		before = self._before()
		if not self.pipeline_account:
			self.pipeline_account = sales_ops.find_account(self.customer, self.lead, self.account)
			if not self.pipeline_account and (self.account or self.customer):
				acc = sales_ops.make_account({
					"account_name": self.account, "account_owner": self.deal_owner, "customer": self.customer, "lead": self.lead,
					"contact_name": self.contact_name, "phone": self.phone, "email": self.email,
					"location_address": self.location_address, "license_number": self.license_number, "lead_source": self.lead_source,
				})
				self.pipeline_account = acc.name
		if not self.pipeline_account or (before and before.pipeline_account == self.pipeline_account and self.account):
			return
		acc = frappe.db.get_value(sales_ops.ACCOUNT, self.pipeline_account,
			["account_name", "customer", "lead", "contact_name", "phone", "email", "location_address", "license_number"], as_dict=True)
		if not acc:
			return
		if not (self.account or "").strip():
			self.account = acc.account_name
		if not self.customer and not self.lead:
			self.customer, self.lead = acc.customer, acc.lead
		elif not self.customer and acc.customer:
			self.customer = acc.customer
		for f in ("contact_name", "phone", "email", "location_address", "license_number"):
			if acc.get(f) and not (self.get(f) or "").strip():
				self.set(f, acc[f])

	def _check_required(self, s, st):
		if not self.deal_owner:
			frappe.throw(_("Please choose an Owner for this deal."))
		before = self._before()
		moved = not before or before.stage != self.stage
		if moved and sales_ops.needs_followup(s, st) and not self.next_step_due:
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
		prev_co = [r.user for r in (before.get("co_owners") or [])] if before else []
		added = [u for u in self.co_owner_list() if u not in prev_co]
		if added:
			sales_ops.notify(added, _("{0} added you as a co-owner on the deal {1}").format(
				frappe.utils.get_fullname(frappe.session.user), self.account), deal=self.name)
		if before and before.stage != self.stage and s.notify_managers_on_stage:
			st = sales_ops.stage_info(s, self.stage)
			if st and st.notify_managers:
				sales_ops.notify(sales_ops.manager_users(s), _("{0} moved to {1} ({2})").format(
					self.account, self.stage, frappe.utils.fmt_money(self.deal_value, currency="USD")), deal=self.name)
		self._promote_account(s, before)
		sales_ops.publish_board_update(self.name)

	def _promote_account(self, s, before):
		"""A won deal makes its account a customer (Lead, Qualified Lead, Dormant or Lost -> Active Customer)."""
		won = sales_ops.won_stage(s)
		target = sales_ops.customer_status(s)
		if not (won and target and self.pipeline_account and self.stage == won.name and (not before or before.stage != won.name)):
			return
		current = frappe.db.get_value(sales_ops.ACCOUNT, self.pipeline_account, "lead_status")
		st = sales_ops.status_info(s, current)
		if st and st.is_active_customer:
			return
		acc = frappe.get_doc(sales_ops.ACCOUNT, self.pipeline_account)
		acc.lead_status = target.name
		if self.customer and not acc.customer:
			acc.customer = self.customer
		acc.flags.ignore_permissions = True
		acc.save()

	def on_trash(self):
		sales_ops.publish_board_update(self.name)
