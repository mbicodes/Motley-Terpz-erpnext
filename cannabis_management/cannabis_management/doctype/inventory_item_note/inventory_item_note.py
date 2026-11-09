import frappe
from frappe.model.document import Document


class InventoryItemNote(Document):
    def validate(self):
        self.note = (self.note or "").strip()
        if len(self.note) > 2000:
            frappe.throw(frappe._("Keep the note under 2,000 characters."))
