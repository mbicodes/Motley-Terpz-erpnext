# Settings for the Sales Operation Board. Saving pushes stage / list options into the
# Sales Pipeline Deal and Account Select fields and refreshes stored probabilities on every deal.
# Stage rows with Board = Deal are deal stages; rows with Board = Lead are the lead statuses of accounts.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from cannabis_management import sales_ops, sales_ops_calendar


class SalesPipelineSettings(Document):
	def validate(self):
		seen = set()
		for i, row in enumerate(self.stages or [], start=1):
			row.stage = (row.stage or "").strip()
			row.board = row.board if row.board in sales_ops.BOARDS else "Deal"
			if row.stage in seen:
				frappe.throw(_("Stage {0} is listed more than once.").format(row.stage))
			seen.add(row.stage)
			if not cint(row.sort_order):
				row.sort_order = i * 10
			if not cint(row.is_closed) or row.board == "Lead":
				row.is_won = 0
			if row.board == "Deal":
				row.is_active_customer = 0
		deal_rows = [r for r in self.stages or [] if r.board == "Deal"]
		if not any(not cint(r.is_closed) for r in deal_rows):
			frappe.throw(_("At least one deal stage (Board = Deal) must be open (not closed)."))
		if not any(cint(r.is_closed) and cint(r.is_won) for r in deal_rows):
			frappe.throw(_("Mark one closed deal stage as Counts as Won."))
		if not any(r.board == "Lead" and not cint(r.is_closed) for r in self.stages or []):
			frappe.throw(_("Add at least one open lead status (Board = Lead) for the Leads board."))
		users = set()
		for row in self.owners or []:
			if row.user in users:
				frappe.throw(_("{0} is listed more than once in Owners.").format(row.user))
			users.add(row.user)
			if not (row.display_name or "").strip():
				row.display_name = (frappe.db.get_value("User", row.user, "first_name") or row.user).strip()

	def on_update(self):
		self._carry_renamed_stages()
		frappe.clear_document_cache(self.doctype, self.name)
		sales_ops.clear_settings_memo()
		s = sales_ops.get_settings()
		sales_ops.sync_deal_options(s)
		sales_ops.recompute_probabilities(s)
		sales_ops.publish_board_update()
		sales_ops_calendar.queue_all()  # watchers / date types may have changed

	def _carry_renamed_stages(self):
		"""A stage or lead status renamed in this table keeps its deals / accounts: move them to the new name."""
		before = self.get_doc_before_save()
		if not before:
			return
		old = {r.name: (r.stage or "").strip() for r in before.get("stages") or []}
		for row in self.stages or []:
			prev = old.get(row.name)
			if prev and prev != row.stage:
				if row.board == "Lead":
					frappe.db.sql(
						"update `tab{0}` set lead_status = %s where lead_status = %s".format(sales_ops.ACCOUNT), (row.stage, prev)
					)
				else:
					frappe.db.sql(
						"update `tab{0}` set stage = %s where stage = %s".format(sales_ops.DEAL), (row.stage, prev)
					)
