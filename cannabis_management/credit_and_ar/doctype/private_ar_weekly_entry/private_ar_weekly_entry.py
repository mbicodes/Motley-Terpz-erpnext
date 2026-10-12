# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Private AR Weekly Entry — the log behind Private AR Accountability.

Holds two kinds of entry:
  * private ones, filed on the Private AR Accountability page. These never
    leave this doctype; nothing writes them back to AR Weekly Entry.
  * copies of every AR Weekly Entry (the shared log Nikki files on),
    `mirrored_from` = the original's name. AR Weekly Entry's controller calls
    mirror_entry / remove_mirror, so the copy follows inserts, edits and deletes.

Only the "Private AR Accountability" role has any permission here. The mirror
runs inside Nikki's own save, so it writes with ignore_permissions and must
never raise: any failure is rolled back to a savepoint and logged, and her save
goes through untouched, with nothing on screen that hints this log exists.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from cannabis_management.credit_and_ar.doctype.ar_weekly_entry.ar_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)

DOCTYPE = "Private AR Weekly Entry"

# Everything an AR Weekly Entry carries, copied verbatim.
MIRROR_FIELDS = (
	"customer", "ledger", "week_of", "status", "tier_snapshot", "amount_snapshot",
	"qa", "plan", "notes", "contact", "email", "need_three_way_call",
)


class PrivateARWeeklyEntry(Document):
	def validate(self):
		self.week_of = week_start(self.week_of)
		self._validate_status_for_tier()

	def _validate_status_for_tier(self):
		"""Same rule as AR Weekly Entry: the status must suit the tier."""
		if not self.tier_snapshot or not self.status:
			return
		allowed = STATUSES_BY_TIER.get(self.tier_snapshot)
		if allowed and self.status not in allowed:
			frappe.throw(
				_("{0} is not a valid status for {1}. Allowed: {2}").format(
					self.status, self.tier_snapshot, ", ".join(allowed)
				)
			)


def mirror_entry(src):
	"""Insert or refresh the private copy of AR Weekly Entry `src`."""
	try:
		frappe.db.savepoint("private_ar_mirror")
		name = frappe.db.get_value(DOCTYPE, {"mirrored_from": src.name})
		if name:
			doc = frappe.get_doc(DOCTYPE, name)
		else:
			doc = frappe.new_doc(DOCTYPE)
			doc.mirrored_from = src.name
		for field in MIRROR_FIELDS:
			doc.set(field, src.get(field))
		doc.flags.ignore_permissions = True
		if doc.is_new():
			doc.insert()
		else:
			doc.save()
		# Keep who filed it and when, so the log reads like the original ("Filed
		# By", and the newest-first order). insert() stamps the current session
		# over anything set beforehand, so these are written after it.
		frappe.db.set_value(DOCTYPE, doc.name, {"owner": src.owner, "creation": src.creation},
		                    update_modified=False)
	except Exception:
		frappe.db.rollback(save_point="private_ar_mirror")
		frappe.log_error(title="AR entry sync", message=frappe.get_traceback())


def remove_mirror(src_name):
	"""Delete the private copy when its AR Weekly Entry is deleted."""
	try:
		frappe.db.savepoint("private_ar_mirror")
		# get_all does not apply permissions, which is what a mirror running in
		# someone else's session needs.
		for name in frappe.get_all(DOCTYPE, filters={"mirrored_from": src_name}, pluck="name"):
			frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)
	except Exception:
		frappe.db.rollback(save_point="private_ar_mirror")
		frappe.log_error(title="AR entry sync", message=frappe.get_traceback())


def backfill():
	"""Copy every existing AR Weekly Entry into the private log (idempotent)."""
	for name in frappe.db.get_all("AR Weekly Entry", pluck="name", order_by="creation asc"):
		mirror_entry(frappe.get_doc("AR Weekly Entry", name))
	frappe.db.commit()
