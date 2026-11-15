# One account (relationship) on the Leads board of the Sales Operation Board (/app/sales-operation-board).
# Its lead status describes the relationship; its deals sit on the Deals board. The volume rows record how
# much the account procures or produces each week and how much it wants from us, which feeds the projection.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from cannabis_management import sales_ops


class SalesPipelineAccount(Document):
	def validate(self):
		s = sales_ops.get_settings()
		self.account_name = (self.account_name or "").strip()
		if not self.lead_status:
			self.lead_status = s.first_status
		if not sales_ops.status_info(s, self.lead_status):
			frappe.throw(_("Lead status {0} is not set up in Sales Pipeline Settings.").format(self.lead_status))
		self._check_owner(s)
		self._prefill_from_customer()
		self._apply_volume(s)
		self._status_since()
		self._link_party()

	def _before(self):
		return None if self.is_new() else self.get_doc_before_save()

	def _check_owner(self, s):
		if not self.account_owner:
			frappe.throw(_("Please choose a Relationship Manager for this account."))
		before = self._before()
		prev = before.account_owner if before else None
		if self.flags.ignore_permissions or frappe.flags.in_patch or frappe.flags.in_migrate:
			return
		if self.account_owner != prev and self.account_owner not in [o.user for o in s.owners if o.active]:
			frappe.throw(_("{0} is not an active owner in Sales Pipeline Settings.").format(self.account_owner))
		user = frappe.session.user
		if sales_ops.is_manager(user) or self.account_owner == prev:
			return
		if self.is_new():
			if self.account_owner != user:
				frappe.throw(_("You can only create accounts for yourself. A pipeline manager can assign them to others."))
			return
		# a non-manager may take an account only when it is theirs already or has no owner
		if prev and prev != user:
			frappe.throw(_("Only a pipeline manager can give this account to someone else."))
		if self.account_owner != user:
			frappe.throw(_("Only a pipeline manager can assign an account to someone else."))

	def _prefill_from_customer(self):
		if not self.customer:
			return
		before = self._before()
		if before and before.customer == self.customer:
			return
		info = sales_ops.customer_buyer_info(self.customer)
		if info.get("account") and not self.account_name:
			self.account_name = info["account"]
		for field in ("contact_name", "phone", "email", "location_address"):
			if info.get(field) and not (self.get(field) or "").strip():
				self.set(field, info[field])

	def _apply_volume(self, s):
		rows = [r for r in (self.get("volume") or []) if r.product_line or flt(r.weekly_volume) or flt(r.wants_qty)]
		if len(rows) != len(self.get("volume") or []):
			self.set("volume", rows)
		for i, r in enumerate(rows, start=1):
			r.product_line = (r.product_line or "").strip()
			r.tier = (r.tier or "").strip()
			if not r.product_line:
				frappe.throw(_("Volume row {0}: please choose a Product Line.").format(i))
			if r.product_line not in s.product_line_names and not self._had_line(r):
				frappe.throw(_("Volume row {0}: {1} is not a Product Line in Sales Pipeline Settings.").format(i, r.product_line))
			for f in ("weekly_volume", "wants_qty", "price_per_gram"):
				if flt(r.get(f)) < 0:
					frappe.throw(_("Volume row {0}: amounts cannot be negative.").format(i))
			r.uom = r.uom if r.uom in sales_ops.UNIT_GRAMS else "g"
			r.wants_per = r.wants_per if r.wants_per in ("Week", "Month") else "Month"
			r.activity = r.activity if r.activity in ("Procure", "Produce") else "Procure"
			if not flt(r.price_per_gram):
				r.price_per_gram = sales_ops.default_price(s, r.product_line, r.tier)
			sales_ops.volume_row(r)
		self.weekly_volume = sum(flt(r.weekly_grams) for r in rows)
		self.monthly_demand = sum(flt(r.monthly_grams) for r in rows)
		self.monthly_potential = sum(flt(r.monthly_value) for r in rows)

	def _had_line(self, row):
		"""A product line removed from Settings stays valid on rows that already had it."""
		before = self._before()
		old = next((r for r in (before.get("volume") or []) if r.name == row.name), None) if before else None
		return bool(old and old.product_line == row.product_line)

	def _status_since(self):
		before = self._before()
		if not before or before.lead_status != self.lead_status or not self.status_changed_on:
			self.status_changed_on = now_datetime()

	def _link_party(self):
		"""No Customer and no Lead yet: reuse a Lead with the same company name, else create one."""
		if self.customer or self.lead or not self.account_name or self.flags.skip_lead:
			return
		rows = frappe.db.sql(
			"select name from `tabLead` where lower(trim(company_name)) = lower(%s) order by creation limit 1", self.account_name
		)
		if rows:
			self.lead = rows[0][0]
			return
		lead = frappe.get_doc({"doctype": "Lead", "company_name": self.account_name, "lead_owner": self.account_owner})
		lead.flags.ignore_permissions = True
		lead.insert()
		self.lead = lead.name

	def on_update(self):
		s = sales_ops.get_settings()
		before = self.get_doc_before_save()
		if before:
			# deals keep showing the account's current name
			if before.account_name != self.account_name:
				frappe.db.sql(
					"update `tab{0}` set account = %s where pipeline_account = %s and account = %s".format(sales_ops.DEAL),
					(self.account_name, self.name, before.account_name),
				)
			# a Customer linked here reaches the deals that have none yet (needed to win them and to quote)
			if self.customer and before.customer != self.customer:
				frappe.db.sql(
					"update `tab{0}` set customer = %s where pipeline_account = %s and ifnull(customer, '') = ''".format(sales_ops.DEAL),
					(self.customer, self.name),
				)
		if self.account_owner and (not before or before.account_owner != self.account_owner) and s.notify_on_reassign:
			if before:
				sales_ops.notify([self.account_owner], _("{0} made you the relationship manager for {1}").format(
					frappe.utils.get_fullname(frappe.session.user), self.account_name))
		sales_ops.publish_board_update(self.name)

	def on_trash(self):
		sales_ops.publish_board_update(self.name)
