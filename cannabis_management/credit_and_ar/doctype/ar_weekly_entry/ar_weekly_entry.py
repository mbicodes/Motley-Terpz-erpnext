import frappe
from frappe import _
from frappe.model.document import Document

STATUSES_BY_TIER = {
	"upcoming": ["Will Pay On Time"],
	"level1": ["Will Pay Immediately", "Client Is Dodging Us", "Need Reconciliation",
		"WIP At Lab", "Pending Pickup", "Payment Plan", "No Longer In Business"],
	"level2": ["Will Pay Immediately", "Client Is Dodging Us", "Need Reconciliation",
		"WIP At Lab", "Pending Pickup", "Payment Plan", "No Longer In Business"],
	"level3": ["Will Pay Immediately", "Client Is Dodging Us", "Need Reconciliation",
		"WIP At Lab", "Pending Pickup", "Payment Plan", "No Longer In Business"],
}


class ARWeeklyEntry(Document):
	def validate(self):
		self.week_of = week_start(self.week_of)
		self._validate_status_for_tier()

	def _validate_status_for_tier(self):
		if not self.tier_snapshot or not self.status:
			return
		allowed = STATUSES_BY_TIER.get(self.tier_snapshot)
		if allowed and self.status not in allowed:
			frappe.throw(
				_("{0} is not a valid status for {1}. Allowed: {2}").format(
					self.status, self.tier_snapshot, ", ".join(allowed)
				)
			)

	def on_update(self):
		from cannabis_management.credit_and_ar.doctype.private_ar_weekly_entry.private_ar_weekly_entry import (
			mirror_entry,
		)

		mirror_entry(self)

	def on_trash(self):
		from cannabis_management.credit_and_ar.doctype.private_ar_weekly_entry.private_ar_weekly_entry import (
			remove_mirror,
		)

		remove_mirror(self.name)


def week_start(date=None):
	from frappe.utils import add_days, getdate, nowdate

	d = getdate(date or nowdate())
	return add_days(d, -d.weekday())
