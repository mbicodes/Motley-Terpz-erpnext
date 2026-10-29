import frappe
from frappe import _
from frappe.model.document import Document


class AdditiveTemplate(Document):
	def validate(self):
		if not self.active_ingredients:
			frappe.throw(_("Add at least one Active Ingredient."))
