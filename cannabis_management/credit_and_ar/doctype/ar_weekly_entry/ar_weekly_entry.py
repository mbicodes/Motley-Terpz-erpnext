# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Status options per tier — the mockup's set (spec §2a) plus the four added
# 2026-10-09 for the overdue tiers. The page's ARW_STATUS_* maps must list them too.
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

	Entries are always filed against a Monday so that one customer+ledger has at
	most one entry per week no matter which day it was written.
	"""
	from frappe.utils import add_days, getdate, nowdate

	d = getdate(date or nowdate())
	return add_days(d, -d.weekday())
