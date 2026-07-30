import frappe
from frappe.model.document import Document


class CreditReview(Document):
    def on_update(self):
        # Apply an approved line change to the Credit Profile.
        if self.decision in ("Increase", "Decrease", "Zero (revoke)") and self.md_approval:
            name = frappe.db.get_value("Credit Profile", {"customer": self.customer})
            if name:
                new_line = 0 if self.decision == "Zero (revoke)" else self.new_line
                frappe.db.set_value("Credit Profile", name, "approved_line", new_line)
                if self.decision == "Zero (revoke)":
                    frappe.db.set_value("Credit Profile", name, "status", "COD")
