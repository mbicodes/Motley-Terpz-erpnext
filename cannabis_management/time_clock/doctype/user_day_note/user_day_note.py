import frappe
from frappe import _
from frappe.model.document import Document


class UserDayNote(Document):
	def validate(self):
		self.note = (self.note or "").strip()
		if not self.note:
			frappe.throw(_("Note cannot be empty."))

		if not self.logged_by:
			self.logged_by = frappe.session.user
