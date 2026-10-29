import frappe
from frappe import _
from frappe.model.document import Document

STATUSES_BY_TIER = {
	"upcoming": ["Scheduled On Time"],
	"level1": [
		"Paying Immediately", "Payment Scheduled", "Awaiting Approval",
		"Disputed - Need Reconciliation", "Short On Funds",
	],
	"level2": [
		"Paying Immediately", "Payment Scheduled", "Awaiting Approval",
		"Disputed - Need Reconciliation", "Short On Funds",
	],
	"level3": [
		"Paying Immediately", "Payment Scheduled", "Awaiting Approval",
		"Disputed - Need Reconciliation", "Short On Funds",
	],
}


class APWeeklyEntry(Document):
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


def week_start(date=None):
	from frappe.utils import add_days, getdate, nowdate

	d = getdate(date or nowdate())
	return add_days(d, -d.weekday())
