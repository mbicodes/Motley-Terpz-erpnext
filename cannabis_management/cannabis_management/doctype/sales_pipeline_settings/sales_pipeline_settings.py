# Settings for the Sales Operation Board. Saving pushes stage / list options into the
# Sales Pipeline Deal Select fields and refreshes stored probabilities on every deal.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from cannabis_management import sales_ops


class SalesPipelineSettings(Document):
	def validate(self):
		seen = set()
		for i, row in enumerate(self.stages or [], start=1):
			row.stage = (row.stage or "").strip()
			if row.stage in seen:
				frappe.throw(_("Stage {0} is listed more than once.").format(row.stage))
			seen.add(row.stage)
			if not cint(row.sort_order):
				row.sort_order = i * 10
			if not cint(row.is_closed):
				row.is_won = 0
		if not any(not cint(r.is_closed) for r in self.stages or []):
			frappe.throw(_("At least one stage must be open (not closed)."))
		if not any(cint(r.is_closed) and cint(r.is_won) for r in self.stages or []):
			frappe.throw(_("Mark one closed stage as Counts as Won."))
		users = set()
		for row in self.owners or []:
			if row.user in users:
				frappe.throw(_("{0} is listed more than once in Owners.").format(row.user))
			users.add(row.user)
			if not (row.display_name or "").strip():
				row.display_name = (frappe.db.get_value("User", row.user, "first_name") or row.user).strip()

	def on_update(self):
		sales_ops.clear_settings_memo()
		s = sales_ops.get_settings()
		sales_ops.sync_deal_options(s)
		sales_ops.recompute_probabilities(s)
		sales_ops.publish_board_update()
