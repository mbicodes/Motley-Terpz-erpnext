# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Status options per tier.
#
# These read from our side of the ledger, not the supplier's: on a receivable
# the question is whether the customer will pay us, on a payable it is what we
# are going to do about a bill we owe. "Short On Funds" has no AR equivalent and
# is the one answer nobody volunteers, which is exactly why it is on the list --
# an unpaid bill with no status is indistinguishable from one nobody can fund.
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
		"""The client filters the dropdown, but the rule is enforced here too so an
		API call or a Data Import cannot file a status the tier does not allow."""
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
	"""Monday of the week that `date` (default today) falls in.

	Entries are always filed against a Monday so that one supplier+company has at
	most one entry per week no matter which day it was written.
	"""
	from frappe.utils import add_days, getdate, nowdate

	d = getdate(date or nowdate())
	return add_days(d, -d.weekday())
