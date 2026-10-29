import frappe
from frappe import _
from frappe.model.document import Document

from cannabis_management.credit_and_ar.doctype.ar_weekly_entry.ar_weekly_entry import (
	STATUSES_BY_TIER,
	week_start,
)

DOCTYPE = "Private AR Weekly Entry"

MIRROR_FIELDS = (
	"customer", "ledger", "week_of", "status", "tier_snapshot", "amount_snapshot",
	"qa", "plan", "notes", "contact", "email", "need_three_way_call",
)


class PrivateARWeeklyEntry(Document):
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


def mirror_entry(src):
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
		frappe.db.set_value(DOCTYPE, doc.name, {"owner": src.owner, "creation": src.creation},
		                    update_modified=False)
	except Exception:
		frappe.db.rollback(save_point="private_ar_mirror")
		frappe.log_error(title="AR entry sync", message=frappe.get_traceback())


def remove_mirror(src_name):
	try:
		frappe.db.savepoint("private_ar_mirror")
		for name in frappe.get_all(DOCTYPE, filters={"mirrored_from": src_name}, pluck="name"):
			frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)
	except Exception:
		frappe.db.rollback(save_point="private_ar_mirror")
		frappe.log_error(title="AR entry sync", message=frappe.get_traceback())


def backfill():
	for name in frappe.db.get_all("AR Weekly Entry", pluck="name", order_by="creation asc"):
		mirror_entry(frappe.get_doc("AR Weekly Entry", name))
	frappe.db.commit()
