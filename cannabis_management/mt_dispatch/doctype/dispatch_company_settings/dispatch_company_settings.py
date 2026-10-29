import frappe
from frappe import _
from frappe.model.document import Document


class DispatchCompanySettings(Document):
	def validate(self):
		self.validate_separation_of_duties()
		self.validate_unique_team()

	def validate_separation_of_duties(self):
		for row in self.team or []:
			if row.fulfillment and row.approver:
				frappe.throw(
					_("Row #{0}: {1} cannot be both Fulfillment and Approver on the same company.").format(
						row.idx, row.user
					),
					title=_("Separation of Duties"),
				)
			if row.can_override and not row.approver:
				frappe.throw(
					_("Row #{0}: Can Override is for approvers. Tick Approver for {1} or clear it.").format(
						row.idx, row.user
					),
					title=_("Separation of Duties"),
				)

	def validate_unique_team(self):
		seen = set()
		for row in self.team or []:
			if row.user in seen:
				frappe.throw(_("Row #{0}: {1} is listed twice.").format(row.idx, row.user))
			seen.add(row.user)
